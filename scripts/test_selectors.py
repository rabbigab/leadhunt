#!/usr/bin/env python3
"""Teste les sélecteurs CSS Facebook sans lancer le scraper complet.

Ouvre m.facebook.com sur un groupe, tente d'extraire les posts avec les
sélecteurs actuels, et rapporte ce qui fonctionne ou ce qui est cassé.

Usage :
    python scripts/test_selectors.py --group ID_GROUPE
    python scripts/test_selectors.py --group ID_GROUPE --visible   # navigateur visible
    python scripts/test_selectors.py --url https://m.facebook.com/groups/ID
"""

import asyncio
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from scraper.config.settings import settings
from scraper.facebook.session import FacebookSession
from scraper.facebook.post_parser import extract_post_id_from_url, clean_text

OK   = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"


# Sélecteurs à tester — si l'un casse, les autres prennent le relai
SELECTOR_GROUPS = {
    "Conteneurs de posts": [
        "[role='article']",
        "div[data-ft]",
        "[data-sigil='m-feed-voice-subtitle']",
        "article",
    ],
    "Lien/ID du post": [
        "a[href*='/posts/']",
        "a[href*='story_fbid']",
        "a[href*='/permalink/']",
        "a[href*='pfbid']",
    ],
    "Contenu textuel": [
        "[data-sigil='m-story-body-text']",
        "div[dir='auto']",
        "[data-content-len]",
        "p",
    ],
    "Nom de l'auteur": [
        "h3 strong a",
        "h3 a",
        "[data-sigil='m-profile-name'] a",
        "strong a",
    ],
    "Boutons Like": [
        "[data-sigil='ufi-inline-like']",
        "[aria-label=\"J'aime\"]",
        "[aria-label='Like']",
    ],
}


async def test_selectors(group_id: str, visible: bool):
    settings_headless = not visible
    # Patch temporaire headless
    import scraper.config.settings as s_mod
    original_headless = s_mod.settings.HEADLESS
    s_mod.settings.HEADLESS = settings_headless

    session = FacebookSession(account_id="selector_test")
    await session.start()

    print(f"\n{'='*55}")
    print(f"  Test sélecteurs Facebook — groupe {group_id}")
    print(f"{'='*55}\n")

    # Login
    print("Connexion Facebook...")
    if not await session.login():
        print(f"{FAIL} Impossible de se connecter — vérifier .env")
        await session.close()
        return

    url = f"https://m.facebook.com/groups/{group_id}"
    print(f"Navigation vers {url}...")
    await session.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3)

    page = session.page

    print(f"\nURL actuelle : {page.url}")
    if "login" in page.url:
        print(f"{FAIL} Redirigé vers login — session expirée")
        await session.close()
        return

    # Scroll pour charger du contenu
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(1.5)

    # Tester chaque groupe de sélecteurs
    results = {}
    for group_name, selectors in SELECTOR_GROUPS.items():
        print(f"\n{group_name} :")
        found_any = False
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                n = len(elements)
                if n > 0:
                    print(f"  {OK} '{selector}' → {n} élément(s) trouvé(s)")
                    found_any = True
                else:
                    print(f"  {FAIL} '{selector}' → 0 éléments")
            except Exception as e:
                print(f"  {FAIL} '{selector}' → erreur: {e}")
        results[group_name] = found_any

    # Tentative d'extraction réelle d'un post
    print(f"\n{'─'*55}")
    print("Tentative d'extraction d'un post complet :")
    try:
        containers = await page.query_selector_all("[role='article'], div[data-ft]")
        extracted = 0
        for container in containers[:5]:
            # Chercher un lien de post
            for link_sel in ["a[href*='/posts/']", "a[href*='story_fbid']"]:
                links = await container.query_selector_all(link_sel)
                for link in links:
                    href = await link.get_attribute("href")
                    pid = extract_post_id_from_url(href or "")
                    if pid:
                        # Chercher le texte
                        for text_sel in ["[data-sigil='m-story-body-text']", "div[dir='auto']"]:
                            elem = await container.query_selector(text_sel)
                            if elem:
                                text = clean_text(await elem.inner_text())
                                if len(text) > 20:
                                    print(f"  {OK} Post extrait : ID={pid}")
                                    print(f"     Texte : \"{text[:80]}...\"")
                                    extracted += 1
                                    break
                    if extracted:
                        break
                if extracted:
                    break

        if not extracted:
            print(f"  {WARN} Aucun post extrait — les sélecteurs sont peut-être cassés")
        else:
            print(f"\n  {OK} {extracted} post(s) extrait(s) avec succès")
    except Exception as e:
        print(f"  {FAIL} Erreur lors de l'extraction : {e}")

    # Résumé
    print(f"\n{'='*55}")
    broken = [k for k, v in results.items() if not v]
    if broken:
        print(f"{WARN} Sélecteurs cassés : {', '.join(broken)}")
        print(f"   → Mettre à jour scraper/facebook/group_reader.py")
    else:
        print(f"{OK} Tous les sélecteurs fonctionnent !")
    print()

    s_mod.settings.HEADLESS = original_headless
    await session.close()


def main():
    parser = argparse.ArgumentParser(description="Teste les sélecteurs CSS Facebook")
    parser.add_argument("--group",   required=True, help="ID du groupe Facebook")
    parser.add_argument("--visible", action="store_true", help="Ouvrir le navigateur (debug)")
    args = parser.parse_args()

    asyncio.run(test_selectors(args.group, args.visible))


if __name__ == "__main__":
    main()
