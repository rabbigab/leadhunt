"""Lecture des posts récents dans un groupe Facebook.

Utilise m.facebook.com (version mobile) :
- DOM plus simple et stable (moins de changements que www)
- Moins de JavaScript de fingerprinting
- Chargement plus rapide = moins de temps exposé
"""

import asyncio
import logging
import random
from typing import List

from playwright.async_api import Page

from scraper.facebook.post_parser import FBPost, extract_post_id_from_url, clean_text
from scraper.facebook.session import FacebookSession

logger = logging.getLogger(__name__)

# URL mobile — plus stable et moins détectable que www.facebook.com
MOBILE_GROUP_URL = "https://m.facebook.com/groups/{group_id}"


class GroupReader:
    def __init__(self, session: FacebookSession):
        self.session = session

    async def fetch_recent_posts(
        self, group_id: str, group_name: str, group_url: str, limit: int = 25
    ) -> List[FBPost]:
        page = self.session.page
        posts: List[FBPost] = []

        # Toujours utiliser la version mobile
        mobile_url = MOBILE_GROUP_URL.format(group_id=group_id)

        try:
            await page.goto(mobile_url, wait_until="domcontentloaded", timeout=30_000)
            await self.session.random_human_pause(2, 4)

            if not await self.session.ensure_logged_in():
                logger.error(f"Non connecté, impossible de lire {group_name}")
                return []

            # Vérifier accès au groupe
            if await self._is_access_denied(page):
                logger.warning(f"Accès refusé au groupe {group_name} (membre requis ou groupe privé)")
                return []

            posts = await self._extract_posts(page, group_id, group_name, limit)
            logger.info(f"'{group_name}' : {len(posts)} posts extraits")

        except Exception as e:
            logger.error(f"Erreur lecture groupe {group_name} : {e}")

        return posts

    async def _is_access_denied(self, page: Page) -> bool:
        url = page.url
        if "login" in url or "checkpoint" in url:
            return True
        # Sur mobile, si le groupe requiert une adhésion non acceptée
        join_btn = await page.query_selector('[data-sigil="join-group-button"]')
        return join_btn is not None

    async def _extract_posts(
        self, page: Page, group_id: str, group_name: str, limit: int
    ) -> List[FBPost]:
        posts: List[FBPost] = []
        seen_ids: set = set()

        # Scroll progressif — comportement humain
        scroll_rounds = min(4, max(2, limit // 8))
        for _ in range(scroll_rounds):
            # Scroll avec vitesse variable (humain)
            scroll_amount = random.randint(600, 1200)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await self.session.random_human_pause(1.5, 3.5)

            new_posts = await self._parse_page_posts(page, group_id, group_name)
            for p in new_posts:
                if p.fb_post_id not in seen_ids and p.content:
                    posts.append(p)
                    seen_ids.add(p.fb_post_id)

            if len(posts) >= limit:
                break

        return posts[:limit]

    async def _parse_page_posts(
        self, page: Page, group_id: str, group_name: str
    ) -> List[FBPost]:
        posts = []

        # Sélecteurs mobile Facebook — plus stables que desktop
        # Les articles de feed sur m.facebook.com ont des data-sigil cohérents
        post_containers = await page.query_selector_all(
            "[data-sigil='m-feed-voice-subtitle'], article, [role='article']"
        )

        # Fallback : chercher les blocs de texte de post directement
        if not post_containers:
            post_containers = await page.query_selector_all("div[data-ft]")

        for container in post_containers:
            try:
                post = await self._parse_single_post(container, page, group_id, group_name)
                if post:
                    posts.append(post)
            except Exception as e:
                logger.debug(f"Erreur parsing container : {e}")

        return posts

    async def _parse_single_post(self, container, page: Page, group_id: str, group_name: str) -> FBPost | None:
        # --- Extraire le lien et l'ID du post ---
        post_id = ""
        post_url = ""

        link_selectors = [
            "a[href*='/groups/{}/posts/']".format(group_id),
            "a[href*='/permalink/']",
            "a[href*='story_fbid']",
            "a[href*='/posts/']",
        ]
        for selector in link_selectors:
            links = await container.query_selector_all(selector)
            for link in links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                pid = extract_post_id_from_url(href)
                if pid:
                    post_id = pid
                    post_url = href if href.startswith("http") else f"https://m.facebook.com{href}"
                    break
            if post_id:
                break

        if not post_id:
            return None

        # --- Extraire le contenu textuel ---
        content = ""
        text_selectors = [
            "[data-sigil='m-story-body-text']",
            "[data-content-len]",
            "div[dir='auto']",
            "p",
        ]
        for selector in text_selectors:
            elem = await container.query_selector(selector)
            if elem:
                text = clean_text(await elem.inner_text())
                if len(text) > 30:
                    content = text
                    break

        if not content:
            return None

        # --- Extraire le nom de l'auteur ---
        author_name = "Auteur inconnu"
        author_selectors = [
            "h3 strong a",
            "h3 a",
            "[data-sigil='m-profile-name'] a",
            "strong a",
        ]
        for selector in author_selectors:
            elem = await container.query_selector(selector)
            if elem:
                name = clean_text(await elem.inner_text())
                if name and len(name) > 1:
                    author_name = name
                    break

        return FBPost(
            fb_post_id=post_id,
            group_id=group_id,
            group_name=group_name,
            author_name=author_name,
            content=content,
            post_url=post_url,
        )
