"""WarmupSequencer — protocole automatisé de chauffe d'un compte Facebook.

Reproduit le comportement d'un nouvel utilisateur qui découvre les groupes
progressivement sur 3 semaines, pour éviter les flags anti-bot au démarrage.

Planning :
  Semaine 1 (J1-J7)   : Navigation feed + profil, 0 groupe
  Semaine 2 (J8-J14)  : Rejoindre 2-3 groupes/jour, lecture passive
  Semaine 3 (J15-J21) : Interactions légères, scraping light (5 groupes max)
  Jour 22+             : Compte promu 'active', scraping complet
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from scraper.facebook.interaction_bot import InteractionBot
from scraper.facebook.session import FacebookSession

logger = logging.getLogger(__name__)

# URLs de groupes francophones publics pour le warmup (rejoindre progressivement)
# Ces groupes sont utilisés uniquement pendant le warming — pas des groupes cibles
WARMUP_PUBLIC_GROUPS = [
    "https://m.facebook.com/groups/franceisrael",
    "https://m.facebook.com/groups/francophonesisrael",
    "https://m.facebook.com/groups/francophonestelaviv",
    "https://m.facebook.com/groups/israelfrancophone",
    "https://m.facebook.com/groups/expatfranceisrael",
]


class WarmupSequencer:
    def __init__(self, session: FacebookSession, account_id: str, warming_started_at: datetime):
        self.session = session
        self.account_id = account_id
        self.warming_started_at = warming_started_at
        self._interaction_bot = InteractionBot(session, account_id)

    def warming_day(self) -> int:
        delta = datetime.now(timezone.utc) - self.warming_started_at
        return max(1, delta.days + 1)

    def is_ready_for_production(self) -> bool:
        return self.warming_day() >= 22

    def current_phase(self) -> str:
        day = self.warming_day()
        if day <= 7:
            return "phase1_feed_only"
        if day <= 14:
            return "phase2_join_groups"
        if day <= 21:
            return "phase3_light_scraping"
        return "ready"

    async def run_daily_warming_session(self, target_groups: list[str]) -> None:
        """Exécute la session de warming adaptée au jour courant."""
        phase = self.current_phase()
        day = self.warming_day()
        logger.info(f"[{self.account_id}] Warming J{day} — {phase}")

        if phase == "phase1_feed_only":
            await self._phase1_session()

        elif phase == "phase2_join_groups":
            await self._phase1_session()  # Feed en premier
            await self._phase2_join_groups(day)

        elif phase == "phase3_light_scraping":
            await self._phase1_session()
            # Scraping léger sur les 5 premiers groupes cibles (lecture uniquement)
            light_groups = target_groups[:5]
            logger.info(f"[{self.account_id}] Scraping léger sur {len(light_groups)} groupes")
            # Le scraping réel est géré par main.py — ici on indique juste que c'est autorisé

    async def _phase1_session(self) -> None:
        """Phase 1 : navigation naturelle du fil d'actualité."""
        interactions = await self._interaction_bot.run_feed_warmup()
        logger.debug(f"[{self.account_id}] Phase 1 : {interactions} interactions sur le feed")

        # Visiter son propre profil (comportement humain courant)
        if random.random() < 0.3:
            try:
                await self.session.page.goto(
                    "https://m.facebook.com/me", wait_until="domcontentloaded", timeout=15_000
                )
                await self.session.random_human_pause(3, 8)
            except Exception:
                pass

    async def _phase2_join_groups(self, day: int) -> None:
        """Phase 2 : rejoindre 2-3 groupes warmup par jour."""
        # Nombre de groupes à rejoindre ce jour (2-3, aléatoire)
        nb_to_join = random.randint(2, 3)

        # Index basé sur le jour pour ne pas rejoindre les mêmes deux fois
        start_idx = ((day - 8) * 3) % len(WARMUP_PUBLIC_GROUPS)
        groups_today = WARMUP_PUBLIC_GROUPS[start_idx:start_idx + nb_to_join]

        for group_url in groups_today:
            try:
                await self.session.page.goto(group_url, wait_until="domcontentloaded", timeout=20_000)
                await self.session.random_human_pause(3, 6)

                # Chercher et cliquer le bouton "Rejoindre"
                join_btn = await self.session.page.query_selector(
                    '[data-sigil="join-group-button"], [aria-label*="Rejoindre"], [aria-label*="Join"]'
                )
                if join_btn:
                    await join_btn.scroll_into_view_if_needed()
                    await self.session.random_human_pause(1, 3)
                    await join_btn.click()
                    await self.session.random_human_pause(2, 5)
                    logger.info(f"[{self.account_id}] Demande d'adhésion envoyée : {group_url}")

                # Lire quelques posts dans ce groupe
                scroll_count = random.randint(2, 4)
                for _ in range(scroll_count):
                    await self.session.page.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
                    await self.session.random_human_pause(2, 5)

                # Pause entre groupes
                await self.session.random_human_pause(30, 90)

            except Exception as e:
                logger.debug(f"[{self.account_id}] Erreur phase2 groupe {group_url} : {e}")
