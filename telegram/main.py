"""
main.py — Userbot Telethon : écoute un groupe crypto, classe les messages via Claude API
et redistribue sur deux canaux (public + privé).

Types traités :
  signal   → reformaté en français avec structure signal standard (paire, entrée, targets, SL)
  analyse  → réécrit en français comme analyse originale, idées clés conservées
  autre    → ignoré (liens seuls, photos sans texte, pub)

Session : chargée depuis SESSION_STRING (StringSession Telethon).
          Générez-la avec convert_session.py après avoir exécuté auth.py en local.
"""

import asyncio
import logging
import os
import sys
from enum import Enum

import anthropic
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

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

API_ID: int = int(os.environ["API_ID"])
API_HASH: str = os.environ["API_HASH"]
BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
SESSION_STRING: str = os.environ["SESSION_STRING"]

SOURCE_GROUP: int = int(os.environ["SOURCE_GROUP_ID"])
CHANNEL_PRIVATE: int = int(os.environ["PRIVATE_CHANNEL_ID"])
CHANNEL_PUBLIC: int = int(os.environ["PUBLIC_CHANNEL_ID"])

CLAUDE_MODEL: str = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot = TelegramClient(StringSession(), API_ID, API_HASH)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Classification + traitement Claude API
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    SIGNAL = "signal"
    ANALYSE = "analyse"
    AUTRE = "autre"


CLASSIFICATION_SYSTEM = """\
Tu es un classificateur de messages Telegram dans un groupe crypto.
Réponds uniquement par un seul mot parmi : signal, analyse, autre.

- signal  : contient des zones d'entrée, targets (TP) et/ou stop-loss. C'est un appel à trader.
- analyse : commentaire de marché, vue macro, résultat de trade, opinion sur une crypto. Pas d'appel direct à trader.
- autre   : lien seul, image sans texte pertinent, publicité, message hors-sujet.\
"""

CLASSIFICATION_PROMPT = "Message :\n{text}"

SIGNAL_SYSTEM = """\
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
- Réécris complètement le style — pas de traduction mot-à-mot.
- Sois concis et lisible sur mobile.
- N'ajoute aucun avertissement ni commentaire personnel.\
"""

SIGNAL_PROMPT = "Signal à reformater :\n{text}"

ANALYSE_SYSTEM = """\
Tu es un analyste crypto francophone.
Réécris ce contenu en français comme si c'était une analyse originale que tu aurais rédigée toi-même.
Conserve les idées clés, les faits chiffrés et les cryptos mentionnées.
Ne traduis pas littéralement — reformule entièrement dans un style fluide, direct et professionnel.
Pas de bullet points forcés, pas d'avertissement, pas de titre inutile.
Longueur adaptée au contenu source : ni plus courte ni plus longue.\
"""

ANALYSE_PROMPT = "Contenu à réécrire :\n{text}"


def _call_claude(system: str, prompt: str) -> str:
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )
    return response.content[0].text.strip()


def classify(text: str) -> MessageType:
    raw = _call_claude(CLASSIFICATION_SYSTEM, CLASSIFICATION_PROMPT.format(text=text))
    word = raw.strip().lower().split()[0] if raw.strip() else "autre"
    try:
        return MessageType(word)
    except ValueError:
        return MessageType.AUTRE


def reformat_signal(text: str) -> str:
    return _call_claude(SIGNAL_SYSTEM, SIGNAL_PROMPT.format(text=text))


def rewrite_analysis(text: str) -> str:
    return _call_claude(ANALYSE_SYSTEM, ANALYSE_PROMPT.format(text=text))


# ---------------------------------------------------------------------------
# Gestionnaire d'événements
# ---------------------------------------------------------------------------

@userbot.on(events.NewMessage(chats=SOURCE_GROUP))
async def handle_new_message(event: events.NewMessage.Event) -> None:
    message: Message = event.message
    text: str = (message.text or "").strip()

    if not text:
        return

    log.info("Nouveau message reçu (%d caractères)", len(text))

    try:
        msg_type = classify(text)
        log.info("Classification : %s", msg_type.value)

        if msg_type is MessageType.AUTRE:
            log.info("Ignoré.")
            return

        if msg_type is MessageType.SIGNAL:
            formatted = reformat_signal(text)
        else:
            formatted = rewrite_analysis(text)

        await bot.send_message(CHANNEL_PRIVATE, formatted)
        await bot.send_message(CHANNEL_PUBLIC, formatted)
        log.info("Publié sur les deux canaux (%s).", msg_type.value)

    except anthropic.APIError as exc:
        log.error("Erreur Claude API : %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.error("Erreur inattendue : %s", exc)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

async def main() -> None:
    await userbot.start()
    await bot.start(bot_token=BOT_TOKEN)

    me = await userbot.get_me()
    log.info("Userbot connecté : %s (@%s)", me.first_name, me.username)
    log.info(
        "Écoute du groupe %d → privé %d / public %d",
        SOURCE_GROUP, CHANNEL_PRIVATE, CHANNEL_PUBLIC,
    )

    await userbot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
