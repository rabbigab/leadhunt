import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler
from telegram.error import TelegramError

from scraper.config.settings import settings
from scraper.facebook.post_parser import FBPost
from scraper.detection.keyword_engine import MatchResult

logger = logging.getLogger(__name__)

CATEGORY_EMOJI = {
    "plomberie":        "🔧",
    "electricite":      "⚡",
    "serrurerie":       "🔑",
    "peinture":         "🖌️",
    "bricolage":        "🪛",
    "osteopathie":      "🦴",
    "kine":             "💆",
    "traiteur":         "🍽️",
    "demenagement":     "📦",
    "garde_enfants":    "👶",
    "cours_particuliers": "📚",
    "avocat":           "⚖️",
    "comptable":        "🧾",
    "photographe":      "📸",
    "coach":            "💪",
    "medecin":          "🩺",
    "dentiste":         "🦷",
    "nettoyage":        "🧹",
    "jardinage":        "🌿",
    "traduction":       "🌐",
    "aide_domicile":    "🏠",
    "informatique":     "💻",
    "esthetique":       "💅",
    "animaux":          "🐾",
}

# Callbacks des boutons inline
CB_CONTACTED  = "contacted"   # Lead contacté avec succès
CB_NOT_RELEVANT = "not_relevant"  # Faux positif
CB_REMIND_1H  = "remind_1h"   # Rappel dans 1h


class TelegramNotifier:
    def __init__(self):
        self._bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self._chat_id = settings.TELEGRAM_CHAT_ID
        # Référence vers SupabaseClient injectée après init (évite l'import circulaire)
        self._db = None

    def set_db(self, db) -> None:
        """Injecte le client Supabase pour les callbacks inline."""
        self._db = db

    def _inline_keyboard(self, fb_post_id: str) -> InlineKeyboardMarkup:
        """Boutons d'action sous chaque lead."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Contacté",       callback_data=f"{CB_CONTACTED}:{fb_post_id}"),
                InlineKeyboardButton("❌ Faux positif",   callback_data=f"{CB_NOT_RELEVANT}:{fb_post_id}"),
            ],
            [
                InlineKeyboardButton("⏰ Rappel 1h",     callback_data=f"{CB_REMIND_1H}:{fb_post_id}"),
            ],
        ])

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
            f"💬 _{excerpt}_\n"
            f"\n"
            f"🏷 Mots-clés : `{keywords_str}`\n"
            f"\n"
            f"🔗 [Voir le post]({post.post_url})"
        )

    async def send(self, post: FBPost, match: MatchResult) -> bool:
        message = self._format_message(post, match)
        keyboard = self._inline_keyboard(post.fb_post_id)

        for attempt in range(3):
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
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

    async def handle_callback(self, update: Update, _context) -> None:
        """Gère les clics sur les boutons inline."""
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        if ":" not in data:
            return

        action, fb_post_id = data.split(":", 1)

        if action == CB_CONTACTED:
            await self._handle_contacted(query, fb_post_id)
        elif action == CB_NOT_RELEVANT:
            await self._handle_not_relevant(query, fb_post_id)
        elif action == CB_REMIND_1H:
            await self._handle_remind(query, fb_post_id)

    async def _handle_contacted(self, query, fb_post_id: str) -> None:
        if self._db:
            try:
                self._db._client.table("detected_leads").update(
                    {"status": "contacted"}
                ).eq("fb_post_id", fb_post_id).execute()
            except Exception:
                pass
        original = query.message.text or ""
        await query.edit_message_text(
            text=original + "\n\n✅ *Marqué comme contacté*",
            parse_mode="Markdown",
            reply_markup=None,
        )

    async def _handle_not_relevant(self, query, fb_post_id: str) -> None:
        if self._db:
            try:
                self._db._client.table("detected_leads").update(
                    {"status": "false_positive"}
                ).eq("fb_post_id", fb_post_id).execute()
            except Exception:
                pass
        await query.edit_message_text(
            text=query.message.text + "\n\n❌ *Marqué comme faux positif*",
            parse_mode="Markdown",
            reply_markup=None,
        )

    async def _handle_remind(self, query, fb_post_id: str) -> None:
        await query.answer("⏰ Rappel dans 1 heure !", show_alert=True)
        # Garder les boutons mais confirmer le rappel
        await asyncio.sleep(3600)
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=f"⏰ *Rappel* — Tu voulais recontacter ce lead :\n`{fb_post_id}`",
                parse_mode="Markdown",
            )
        except TelegramError:
            pass

    def start_callback_listener(self) -> None:
        """Démarre le listener de callbacks inline en arrière-plan (thread séparé)."""
        import threading

        def _run():
            app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
            app.add_handler(CallbackQueryHandler(self.handle_callback))
            logger.info("Listener Telegram inline démarré")
            app.run_polling(drop_pending_updates=True)

        thread = threading.Thread(target=_run, daemon=True, name="telegram-callbacks")
        thread.start()
