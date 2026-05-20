"""
main.py — Userbot Telethon : écoute un groupe crypto, détecte les signaux via Claude API,
reformate en français et redistribue sur deux canaux.

Session : chargée depuis la variable d'environnement SESSION_STRING (StringSession Telethon).
          Générez-la avec convert_session.py après avoir exécuté auth.py en local.
"""

import asyncio
import logging
import os
import sys
from itertools import count

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

# Compteur global pour la rotation 1-sur-3 vers le canal public
_signal_counter: count = count(1)
_public_modulo: int = 3

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot = TelegramClient(StringSession(), API_ID, API_HASH)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Helpers Claude API
# ---------------------------------------------------------------------------

DETECTION_SYSTEM = (
    "Tu es un analyste crypto. "
    "Réponds uniquement par 'oui' ou 'non', sans ponctuation ni explication."
)

DETECTION_PROMPT = (
    "Ce message est-il un signal de trading crypto (achat, vente, entrée, "
    "cible de prix, stop-loss, alerte de marché, analyse technique ou "
    "fondamentale sur une cryptomonnaie) ?\n\nMessage :\n{text}"
)

REFORMAT_SYSTEM = (
    "Tu es un expert en trading crypto francophone. "
    "Ton rôle est de reformater des signaux crypto en français clair et professionnel. "
    "Conserve TOUS les faits : paires, prix, cibles, stop-loss, timeframes, pourcentages. "
    "Réécris complètement le style et l'expression — jamais de traduction mot-à-mot. "
    "Sois concis, structuré, lisible sur mobile. "
    "N'ajoute aucun commentaire personnel ni avertissement."
)

REFORMAT_PROMPT = (
    "Reformate ce signal crypto en français :\n\n{text}"
)


def _call_claude(system: str, prompt: str) -> str:
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )
    return response.content[0].text.strip()


def is_crypto_signal(text: str) -> bool:
    answer = _call_claude(DETECTION_SYSTEM, DETECTION_PROMPT.format(text=text))
    return answer.lower().startswith("oui")


def reformat_signal(text: str) -> str:
    return _call_claude(REFORMAT_SYSTEM, REFORMAT_PROMPT.format(text=text))


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
        if not is_crypto_signal(text):
            log.info("Ignoré : pas un signal crypto.")
            return

        log.info("Signal détecté — reformatage en cours…")
        formatted = reformat_signal(text)

        # Envoi systématique sur le canal privé
        await bot.send_message(CHANNEL_PRIVATE, formatted)
        log.info("Publié sur canal privé.")

        # Envoi conditionnel : 1 signal sur 3 sur le canal public
        index = next(_signal_counter)
        if index % _public_modulo == 0:
            await bot.send_message(CHANNEL_PUBLIC, formatted)
            log.info("Publié sur canal public (signal n°%d).", index)

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
