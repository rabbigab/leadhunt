import asyncio
import logging
from datetime import datetime, timezone

import telegram
from telegram import Bot
from telegram.error import TelegramError

from scraper.config.settings import settings
from scraper.facebook.post_parser import FBPost
from scraper.detection.keyword_engine import MatchResult

logger = logging.getLogger(__name__)

CATEGORY_EMOJI = {
    "plomberie": "🔧",
    "electricite": "⚡",
    "serrurerie": "🔑",
    "peinture": "🖌️",
    "bricolage": "🪛",
    "osteopathie": "🦴",
    "kine": "💆",
    "traiteur": "🍽️",
    "demenagement": "📦",
}


class TelegramNotifier:
    def __init__(self):
        self._bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self._chat_id = settings.TELEGRAM_CHAT_ID

    def _format_message(self, post: FBPost, match: MatchResult) -> str:
        emoji = CATEGORY_EMOJI.get(match.category, "🔔")
        excerpt = post.content[:220] + "…" if len(post.content) > 220 else post.content
        keywords_str = ", ".join(match.keywords_found[:5])
        confidence_bar = "🟢" if match.confidence >= 0.8 else "🟡"

        return (
            f"{emoji} *NOUVEAU LEAD — {match.category.upper()}*\n"
            f"\n"
            f"📍 *Groupe :* {post.group_name}\n"
            f"👤 *Auteur :* {post.author_name}\n"
            f"{confidence_bar} *Confiance :* {int(match.confidence * 100)}%\n"
            f"\n"
            f'💬 _{excerpt}_\n'
            f"\n"
            f"🏷 Mots-clés : `{keywords_str}`\n"
            f"\n"
            f"🔗 [Voir le post]({post.post_url})"
        )

    async def send(self, post: FBPost, match: MatchResult) -> bool:
        message = self._format_message(post, match)

        for attempt in range(3):
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=message,
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
                logger.info(f"Notification Telegram envoyée : {post.fb_post_id}")
                return True
            except TelegramError as e:
                logger.warning(f"Erreur Telegram (tentative {attempt + 1}/3) : {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt * 2)

        logger.error(f"Échec notification Telegram pour {post.fb_post_id}")
        return False

    async def send_startup_message(self) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text="✅ *LeadHunt démarré* — surveillance des groupes Facebook active.",
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning(f"Impossible d'envoyer le message de démarrage : {e}")

    async def send_error_alert(self, message: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=f"⚠️ *LeadHunt — Alerte* :\n{message}",
                parse_mode="Markdown",
            )
        except TelegramError:
            pass
