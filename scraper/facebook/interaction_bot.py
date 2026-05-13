"""InteractionBot — simule un comportement humain naturel.

Exécuté à chaque session de scraping pour éviter le pattern "lecture pure"
qui déclenche les détecteurs de bots Facebook.

Stratégie :
- Scroller le fil principal (toujours, dès le début de session)
- Liker 2-5 posts aléatoires par session (non-leads)
- Commenter 1 post par semaine max (très conservateur)
- Jamais interagir sur les posts qu'on est en train de scraper
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from playwright.async_api import Page

from scraper.facebook.session import FacebookSession

logger = logging.getLogger(__name__)

# Pool de commentaires naturels en français — variés pour éviter la répétition
COMMENT_POOL = [
    "Merci pour l'info 👍",
    "Très utile, merci !",
    "Bonne chance à tous !",
    "Super groupe, toujours des bonnes infos ici",
    "Merci de partager 🙏",
    "Excellent, je transmets !",
    "Intéressant, merci",
    "Utile comme toujours 👌",
    "Merci pour le partage !",
    "Bonne continuation à tous",
]

# Probabilité de liker un post vu (10-20% = naturel)
LIKE_PROBABILITY = 0.15

# Probabilité de commenter (1% = très rare, environ 1x/semaine si 15 posts vus/jour)
COMMENT_PROBABILITY = 0.01


class InteractionBot:
    def __init__(self, session: FacebookSession, account_id: str):
        self.session = session
        self.account_id = account_id
        self._last_comment_date: Optional[datetime] = None

    async def run_feed_warmup(self) -> int:
        """Scroll le fil d'actualité principal au début de session. Retourne nb interactions."""
        page = self.session.page
        interactions = 0

        try:
            logger.debug(f"[{self.account_id}] Warmup fil principal")
            await page.goto("https://m.facebook.com/", wait_until="domcontentloaded", timeout=20_000)
            await self.session.random_human_pause(2, 4)

            # Scroll progressif sur le fil (30-60 secondes de lecture simulée)
            scroll_count = random.randint(4, 8)
            for _ in range(scroll_count):
                scroll_px = random.randint(400, 900)
                await page.evaluate(f"window.scrollBy(0, {scroll_px})")
                await self.session.random_human_pause(2, 6)

                # Tenter un like sur un post visible
                if random.random() < LIKE_PROBABILITY:
                    liked = await self._try_like_random_post(page)
                    if liked:
                        interactions += 1
                        logger.debug(f"[{self.account_id}] Like effectué sur le fil")

                # Commenter très rarement
                if random.random() < COMMENT_PROBABILITY and self._can_comment_today():
                    commented = await self._try_comment_random_post(page)
                    if commented:
                        interactions += 1
                        self._last_comment_date = datetime.now(timezone.utc)

        except Exception as e:
            logger.debug(f"[{self.account_id}] Erreur warmup feed : {e}")

        return interactions

    async def maybe_interact_in_group(self, page: Page, group_id: str) -> None:
        """Interaction occasionnelle DANS un groupe — sur un post non-lead aléatoire.

        Appelé après le scraping d'un groupe, de façon très aléatoire.
        Ne jamais interagir sur un post qu'on vient de détecter comme lead.
        """
        # Seulement 5% de chance d'interagir dans un groupe (très conservateur)
        if random.random() > 0.05:
            return

        try:
            # Remonter en haut du groupe et liker un post non-lead
            await page.evaluate("window.scrollTo(0, 0)")
            await self.session.random_human_pause(1, 3)
            await self._try_like_random_post(page)
        except Exception:
            pass

    async def _try_like_random_post(self, page: Page) -> bool:
        """Tente de liker un post aléatoire visible sur la page courante."""
        try:
            # Cherche les boutons "J'aime" non encore likés
            like_buttons = await page.query_selector_all(
                '[data-sigil="ufi-inline-like"], [aria-label="J\'aime"], [aria-label="Like"]'
            )
            if not like_buttons:
                return False

            # Prendre un bouton aléatoire (pas le premier — trop prévisible)
            btn = random.choice(like_buttons)

            # Vérifier que ce n'est pas déjà liké
            aria_pressed = await btn.get_attribute("aria-pressed")
            if aria_pressed == "true":
                return False

            # Scroll vers le bouton avant de cliquer (comportement humain)
            await btn.scroll_into_view_if_needed()
            await self.session.random_human_pause(0.5, 1.5)
            await btn.click()
            await self.session.random_human_pause(1, 3)
            return True

        except Exception as e:
            logger.debug(f"Erreur like : {e}")
            return False

    async def _try_comment_random_post(self, page: Page) -> bool:
        """Tente de poster un commentaire naturel sur un post visible."""
        try:
            # Cherche les zones de commentaire
            comment_boxes = await page.query_selector_all(
                '[data-sigil="comment-body"], [placeholder*="commentaire"], [aria-label*="commentaire"]'
            )
            if not comment_boxes:
                return False

            box = random.choice(comment_boxes)
            comment_text = random.choice(COMMENT_POOL)

            await box.scroll_into_view_if_needed()
            await self.session.random_human_pause(1, 3)
            await box.click()
            await self.session.random_human_pause(0.5, 1)

            # Frappe lettre par lettre avec délais variables (humain)
            for char in comment_text:
                await box.type(char, delay=random.randint(50, 180))
            await self.session.random_human_pause(1, 2)

            # Envoyer avec Entrée
            await box.press("Enter")
            await self.session.random_human_pause(2, 4)
            logger.info(f"[{self.account_id}] Commentaire posté : '{comment_text[:30]}...'")
            return True

        except Exception as e:
            logger.debug(f"Erreur commentaire : {e}")
            return False

    def _can_comment_today(self) -> bool:
        """Maximum 1 commentaire par semaine par compte."""
        if self._last_comment_date is None:
            return True
        return datetime.now(timezone.utc) - self._last_comment_date > timedelta(days=7)
