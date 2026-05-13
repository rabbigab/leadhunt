"""Gestion de la session Facebook.

Utilise Camoufox (Firefox patché, indétectable) avec :
- Profil persistant par compte FB (fingerprint stable entre sessions)
- Proxy résidentiel rotatif (optionnel, recommandé en production)
- Comportement humain simulé (délais, scroll, mouvements)
"""

import json
import logging
import random
import asyncio
from pathlib import Path
from typing import Optional

from camoufox.async_api import AsyncCamoufox

from scraper.config.settings import settings

logger = logging.getLogger(__name__)

# Locales réalistes pour un francophone en Israël
LOCALES = ["fr-IL", "fr-FR", "he-IL"]

# Viewports courants
VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
]


class FacebookSession:
    """Session FB persistante avec Camoufox + proxy optionnel."""

    def __init__(self, proxy_url: Optional[str] = None, account_id: str = "default"):
        self._proxy_url = proxy_url
        self._account_id = account_id
        self._camoufox: Optional[AsyncCamoufox] = None
        self._browser = None
        self.context = None
        self.page = None
        self._profile_dir = settings.SESSIONS_DIR / f"profile_{account_id}"
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._cookies_file = settings.SESSIONS_DIR / f"cookies_{account_id}.json"

    async def start(self) -> None:
        proxy = None
        if self._proxy_url:
            proxy = {"server": self._proxy_url}
            logger.info(f"Session avec proxy : {self._proxy_url.split('@')[-1]}")

        viewport = random.choice(VIEWPORTS)

        # Camoufox = Firefox patché : navigator.webdriver absent, fingerprints réalistes
        self._camoufox = AsyncCamoufox(
            headless=settings.HEADLESS,
            geoip=True,           # IP géolocalisation cohérente avec le proxy
            humanize=True,        # Mouvements souris + délais humains automatiques
            locale=random.choice(LOCALES),
            screen={"width": viewport["width"], "height": viewport["height"]},
            proxy=proxy,
        )
        self._browser = await self._camoufox.__aenter__()
        self.context = await self._browser.new_context(
            user_data_dir=str(self._profile_dir),  # Profil persistant = fingerprint stable
        )
        self.page = await self.context.new_page()

    async def login(self) -> bool:
        """Tente de restaurer la session depuis les cookies, sinon fait un login formulaire."""
        if await self._try_load_cookies():
            logger.info(f"[{self._account_id}] Session FB restaurée depuis les cookies")
            return True
        logger.info(f"[{self._account_id}] Connexion FB par formulaire")
        return await self._form_login()

    async def _try_load_cookies(self) -> bool:
        if not self._cookies_file.exists():
            return False
        try:
            with open(self._cookies_file, "r") as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            # Aller sur la version mobile (plus légère, moins de JS détection)
            await self.page.goto("https://m.facebook.com/", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(random.uniform(2, 4))
            if await self._is_logged_in():
                return True
            logger.warning(f"[{self._account_id}] Cookies expirés")
            return False
        except Exception as e:
            logger.warning(f"[{self._account_id}] Échec chargement cookies : {e}")
            return False

    async def _form_login(self) -> bool:
        try:
            await self.page.goto("https://m.facebook.com/login", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(random.uniform(1.5, 3.0))

            # Camoufox humanize gère les délais entre keystrokes automatiquement
            await self.page.fill("#m_login_email", settings.FB_EMAIL)
            await asyncio.sleep(random.uniform(0.8, 2.0))
            await self.page.fill("#m_login_password", settings.FB_PASSWORD)
            await asyncio.sleep(random.uniform(0.5, 1.2))
            await self.page.click('[name="login"]')
            await self.page.wait_for_load_state("domcontentloaded", timeout=15_000)
            await asyncio.sleep(random.uniform(3, 5))

            if await self._is_logged_in():
                await self._save_cookies()
                logger.info(f"[{self._account_id}] Connexion FB réussie")
                return True

            # Détecter CAPTCHA ou checkpoint
            url = self.page.url
            if "checkpoint" in url or "captcha" in url.lower():
                logger.error(f"[{self._account_id}] CAPTCHA ou checkpoint détecté — intervention manuelle requise")
            else:
                logger.error(f"[{self._account_id}] Échec connexion FB — vérifier credentials")
            return False

        except Exception as e:
            logger.error(f"[{self._account_id}] Erreur login : {e}")
            return False

    async def _is_logged_in(self) -> bool:
        url = self.page.url
        if any(x in url for x in ["login", "checkpoint", "captcha"]):
            return False
        try:
            # Sur m.facebook.com : la barre de nav mobile est présente si connecté
            elem = await self.page.query_selector('[data-sigil="m-home-icon"], #MComposer, [aria-label="Home"]')
            return elem is not None
        except Exception:
            return False

    async def _save_cookies(self) -> None:
        cookies = await self.context.cookies()
        with open(self._cookies_file, "w") as f:
            json.dump(cookies, f)

    async def ensure_logged_in(self) -> bool:
        if not await self._is_logged_in():
            logger.warning(f"[{self._account_id}] Session expirée, reconnexion")
            return await self._form_login()
        return True

    async def random_human_pause(self, min_s: float = 1.0, max_s: float = 4.0) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self._camoufox:
            await self._camoufox.__aexit__(None, None, None)
