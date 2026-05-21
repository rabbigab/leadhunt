"""
main.py — Userbot Telethon + suivi de trades en temps réel via Binance klines.

Pipeline par message :
  1. Déduplication par message_id + hash texte (SQLite)
  2. Classification Claude → signal | analyse | autre
  3. signal  : reformatage FR + extraction JSON → suivi Binance si paire trouvée
     analyse : réécriture FR originale
     autre   : ignoré
  4. Publication sur canal privé ET canal public

Modules complémentaires :
  db.py         — persistance SQLite (Railway Volume /data ou local)
  binance_api.py — résolution symboles + klines
  tracker.py    — polling trades toutes les 5 min
  scheduler.py  — rapport hebdomadaire lundi 09:00 UTC

Session Telethon chargée depuis SESSION_STRING (StringSession).
Générer avec convert_session.py après auth.py en local.
"""

import asyncio
import json
import logging
import os
import re
import sys
from enum import Enum
from typing import Optional

import aiohttp
import anthropic
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message

# Modules locaux (sys.path[0] = telegram/ quand lancé via python telegram/main.py)
import binance_api
import db
import scheduler
import tracker

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_REQUIRED_ENV = (
    "API_ID", "API_HASH", "BOT_TOKEN", "ANTHROPIC_API_KEY", "SESSION_STRING",
    "SOURCE_GROUP_ID", "PRIVATE_CHANNEL_ID", "PUBLIC_CHANNEL_ID",
)
for _var in _REQUIRED_ENV:
    if not os.environ.get(_var):
        sys.exit(f"Erreur : variable d'environnement manquante : {_var}")

API_ID          = int(os.environ["API_ID"])
API_HASH        = os.environ["API_HASH"]
BOT_TOKEN       = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SESSION_STRING  = os.environ["SESSION_STRING"]

SOURCE_GROUP    = int(os.environ["SOURCE_GROUP_ID"])
CHANNEL_PRIVATE = int(os.environ["PRIVATE_CHANNEL_ID"])
CHANNEL_PUBLIC  = int(os.environ["PUBLIC_CHANNEL_ID"])
ALL_CHANNELS    = [CHANNEL_PRIVATE, CHANNEL_PUBLIC]

CLAUDE_MODEL = "claude-sonnet-4-6"

DISCLAIMER = (
    "📌 *Avis important*\n\n"
    "Les signaux et analyses publiés ici sont partagés à titre informatif uniquement.\n"
    "Ils ne constituent *pas* un conseil en investissement.\n\n"
    "*Faites vos propres recherches (DYOR) avant toute décision financière.*\n\n"
    "_Trading crypto = risque élevé de perte en capital._"
)

# ──────────────────────────────────────────────────────────────────────────────
# Clients
# ──────────────────────────────────────────────────────────────────────────────

userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot     = TelegramClient(StringSession(), API_ID, API_HASH)
claude  = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

_http_session: Optional[aiohttp.ClientSession] = None

# ──────────────────────────────────────────────────────────────────────────────
# Prompts Claude
# ──────────────────────────────────────────────────────────────────────────────

_CLASSIFICATION_SYS = """\
Tu es un classificateur de messages Telegram dans un groupe crypto.
Réponds uniquement par un seul mot parmi : signal, analyse, autre.

- signal  : contient des zones d'entrée, targets (TP) et/ou stop-loss. Appel direct à trader.
- analyse : commentaire de marché, vue macro, résultat de trade, opinion sur une crypto.
- autre   : lien seul, image sans texte pertinent, publicité, message hors-sujet.\
"""

_SIGNAL_SYS = """\
Tu es un expert en trading crypto francophone.
Reformate ce signal en français avec la structure suivante (adapte selon les infos disponibles) :
📌 Paire
📈 Direction
🎯 Entrée / Zone d'entrée
🎯 Targets (TP1, TP2, TP3…)
🛑 Stop-loss
⏱ Timeframe (si mentionné)
📝 Note (si info complémentaire utile)

Règles :
- Conserve TOUS les chiffres, pourcentages et paires.
- Réécris complètement le style — jamais de traduction mot-à-mot.
- Concis, lisible sur mobile.
- Aucun avertissement ni commentaire personnel.\
"""

_ANALYSE_SYS = """\
Tu es un analyste crypto francophone.
Réécris ce contenu en français comme si c'était une analyse originale rédigée par toi.
Conserve les idées clés, les faits chiffrés et les cryptos mentionnées.
Ne traduis pas littéralement — reformule entièrement : style fluide, direct, professionnel.
Pas de bullet points forcés, pas d'avertissement, pas de titre inutile.
Longueur proportionnelle au contenu source.\
"""

_EXTRACTION_SYS = """\
Tu es un extracteur de données structurées pour des signaux de trading crypto.
Retourne UNIQUEMENT un objet JSON valide, sans markdown ni explication.

Champs :
- asset     : ticker de la crypto en majuscules, sans quote (ex: "BTC", "JUP")
- direction : "long" ou "short"
- entry1    : premier prix d'entrée (float)
- entry2    : deuxième prix d'entrée ou null (float|null)
- targets   : take-profits ordonnés [TP1, TP2, …] (array of float)
- stop_loss : prix du stop-loss (float)

Si un champ requis (asset, direction, entry1, targets, stop_loss) est absent ou incertain,
retourne : {"uncertain": true}

Retourne UNIQUEMENT le JSON.\
"""

# ──────────────────────────────────────────────────────────────────────────────
# Helpers Claude (async)
# ──────────────────────────────────────────────────────────────────────────────

class MessageType(str, Enum):
    SIGNAL  = "signal"
    ANALYSE = "analyse"
    AUTRE   = "autre"


async def _claude(system: str, prompt: str, max_tokens: int = 1024) -> str:
    resp = await claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


async def classify(text: str) -> MessageType:
    raw  = await _claude(_CLASSIFICATION_SYS, f"Message :\n{text}", max_tokens=10)
    word = raw.strip().lower().split()[0] if raw.strip() else "autre"
    try:
        return MessageType(word)
    except ValueError:
        return MessageType.AUTRE


async def reformat_signal(text: str) -> str:
    return await _claude(_SIGNAL_SYS, f"Signal à reformater :\n{text}")


async def rewrite_analysis(text: str) -> str:
    return await _claude(_ANALYSE_SYS, f"Contenu à réécrire :\n{text}")


async def extract_signal(text: str) -> Optional[dict]:
    raw = await _claude(_EXTRACTION_SYS, f"Signal :\n{text}")
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if data.get("uncertain"):
        return None
    required = ("asset", "direction", "entry1", "targets", "stop_loss")
    if not all(data.get(k) is not None for k in required):
        return None
    if data["direction"] not in ("long", "short"):
        return None
    if not isinstance(data["targets"], list) or not data["targets"]:
        return None
    return data

# ──────────────────────────────────────────────────────────────────────────────
# Message handler
# ──────────────────────────────────────────────────────────────────────────────

@userbot.on(events.NewMessage(chats=SOURCE_GROUP))
async def handle_new_message(event: events.NewMessage.Event) -> None:
    message: Message = event.message
    text:       str  = (message.text or "").strip()
    message_id: int  = message.id

    if not text:
        return

    # Déduplication
    if await db.is_processed(message_id, text):
        log.info("Message #%d déjà traité — ignoré.", message_id)
        return
    await db.mark_processed(message_id, text)

    log.info("Message #%d reçu (%d car.)", message_id, len(text))

    try:
        msg_type = await classify(text)
        log.info("Classification : %s", msg_type.value)

        if msg_type is MessageType.AUTRE:
            log.info("Ignoré.")
            return

        if msg_type is MessageType.SIGNAL:
            formatted = await reformat_signal(text)
            suffix    = ""

            signal_data = await extract_signal(text)
            if signal_data and _http_session:
                symbol = await binance_api.resolve_symbol(
                    signal_data["asset"], _http_session
                )
                if symbol:
                    trade_id = await db.add_trade(
                        source_message_id=message_id,
                        asset=signal_data["asset"].upper(),
                        symbol=symbol,
                        direction=signal_data["direction"],
                        entry1=float(signal_data["entry1"]),
                        entry2=float(signal_data["entry2"]) if signal_data.get("entry2") else None,
                        targets=[float(t) for t in signal_data["targets"]],
                        stop_loss=float(signal_data["stop_loss"]),
                    )
                    suffix = f"\n\n📡 _Suivi actif sur {symbol} (trade #{trade_id})_"
                    log.info("Trade #%d créé — %s %s.", trade_id, signal_data["direction"].upper(), symbol)
                else:
                    suffix = f"\n\n📡 _Suivi non disponible ({signal_data['asset']} introuvable sur Binance)_"
                    log.info("Symbole %s introuvable sur Binance.", signal_data["asset"])
            elif not signal_data:
                log.info("Extraction incertaine — signal posté sans suivi.")

            formatted += suffix

        else:  # ANALYSE
            formatted = await rewrite_analysis(text)

        for ch in ALL_CHANNELS:
            await bot.send_message(ch, formatted)
        log.info("Publié sur %d canaux (%s).", len(ALL_CHANNELS), msg_type.value)

    except anthropic.APIError as exc:
        log.error("Erreur Claude API : %s", exc)
    except Exception as exc:
        log.error("Erreur inattendue : %s", exc, exc_info=True)

# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _http_session

    await db.init_db()

    _http_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=20))

    await userbot.start()
    await bot.start(bot_token=BOT_TOKEN)

    me = await userbot.get_me()
    log.info("Userbot connecté : %s (@%s)", me.first_name, me.username)
    log.info(
        "Écoute du groupe %d → privé %d / public %d",
        SOURCE_GROUP, CHANNEL_PRIVATE, CHANNEL_PUBLIC,
    )

    # Disclaimer épinglé — posté une seule fois
    if not await db.get_app_state("disclaimer_sent"):
        for ch in ALL_CHANNELS:
            try:
                await bot.send_message(ch, DISCLAIMER, parse_mode="md")
            except Exception as exc:
                log.warning("Disclaimer canal %d : %s", ch, exc)
        await db.set_app_state("disclaimer_sent", "1")
        log.info("Disclaimer posté — épinglez-le manuellement dans chaque canal.")

    # Tâches de fond
    asyncio.create_task(tracker.run_polling_loop(bot, ALL_CHANNELS, _http_session))
    asyncio.create_task(scheduler.run_weekly_scheduler(bot, ALL_CHANNELS, _http_session))

    try:
        await userbot.run_until_disconnected()
    finally:
        await _http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
