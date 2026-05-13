#!/usr/bin/env python3
"""Simule un cycle de détection complet sans Facebook.

Injecte de faux posts directement dans le pipeline :
  KeywordEngine → Supabase → Telegram

Permet de vérifier que tout fonctionne (Supabase accessible, bot Telegram
opérationnel, format des notifications) avant d'avoir les comptes Facebook.

Usage :
    python scripts/simulate.py                  # 5 posts variés
    python scripts/simulate.py --count 10       # 10 posts
    python scripts/simulate.py --dry-run        # sans écrire en DB ni Telegram
    python scripts/simulate.py --category kine  # forcer une catégorie
"""

import argparse
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Posts de simulation ───────────────────────────────────────────────────

FAKE_POSTS = [
    # Plomberie
    ("plomberie", "Bonjour ! Quelqu'un connaît un bon plombier dans le coin ? J'ai une fuite d'eau sous l'évier depuis ce matin, urgent 🙏"),
    ("plomberie", "Mon chauffe-eau vient de lâcher, besoin d'un plombier rapidement pour installation. Qui peut recommander quelqu'un de confiance ?"),
    ("plomberie", "Recherche plombier disponible ce week-end, robinet qui fuit dans la salle de bain. Zone Tel Aviv"),
    # Electricité
    ("electricite", "Mon disjoncteur saute en permanence depuis hier soir, besoin d'un électricien qualifié. Quelqu'un a un bon contact ?"),
    ("electricite", "Cherche electricien pour installation de prises supplémentaires dans mon appartement. Devis bienvenu"),
    # Serrurerie
    ("serrurerie", "URGENT — je me suis enfermé dehors, besoin d'un serrurier maintenant ! Quelqu'un a un numéro ?"),
    ("serrurerie", "Cherche serrurier pour changer les serrures de mon appartement suite à déménagement"),
    # Ostéopathie
    ("osteopathie", "Est-ce que quelqu'un connaît un bon ostéopathe francophone ? J'ai des douleurs au dos depuis 2 semaines"),
    ("osteopathie", "Mon fils de 8 ans a souvent des maux de dos, vous connaissez un ostéopathe pédiatrique ?"),
    # Kiné
    ("kine", "Besoin d'un kiné pour rééducation post-opératoire. Mon médecin m'a prescrit 10 séances. Recommandations ?"),
    # Peinture
    ("peinture", "On cherche un peintre pour refaire 2 chambres et le salon. Appartement 4 pièces à Tel Aviv. Qui connaît quelqu'un de sérieux ?"),
    # Bricolage
    ("bricolage", "Quelqu'un a un bon bricoleur à recommander ? J'ai du mobilier IKEA à assembler et quelques petites réparations"),
    # Traiteur
    ("traiteur", "Nous organisons un bar mitsvah pour 80 personnes en juin. Cherche traiteur francophone. Des recommandations ?"),
    # Déménagement
    ("demenagement", "On déménage de Tel Aviv à Jérusalem en août, besoin d'un déménageur sérieux. Budget raisonnable. Suggestions ?"),
    # Faux positif (doit être filtré)
    (None, "Je suis plombier et je cherche des clients dans la région de Tel Aviv, n'hésitez pas à me contacter !"),
    (None, "Offre d'emploi : nous recrutons un électricien qualifié pour rejoindre notre équipe"),
]

AUTHORS = [
    "Sarah K.", "David M.", "Rachel B.", "Yaël L.", "Moshe T.",
    "Nathalie C.", "Jonathan F.", "Miriam S.", "Aaron D.", "Chloé R.",
]

GROUPS = [
    ("sim_group_1", "Francophones Tel Aviv [SIMULATION]"),
    ("sim_group_2", "Entraide Francophone Israël [SIMULATION]"),
    ("sim_group_3", "Olim France Israël [SIMULATION]"),
]


async def run_simulation(count: int, dry_run: bool, force_category: str | None):
    from scraper.database.client import SupabaseClient
    from scraper.detection.deduplication import Deduplicator
    from scraper.detection.keyword_engine import KeywordEngine
    from scraper.facebook.post_parser import FBPost
    from scraper.notifications.telegram import TelegramNotifier

    print(f"\n{'═'*55}")
    print(f"  LeadHunt — Simulation de pipeline")
    print(f"  {count} posts  │  dry_run={dry_run}")
    print(f"{'═'*55}\n")

    # Init composants
    db = SupabaseClient()
    dedup = Deduplicator()
    notifier = TelegramNotifier()

    keyword_rows = db.get_keyword_categories()
    keyword_engine = KeywordEngine.from_db_rows(keyword_rows, negative_patterns=[
        "je suis plombier", "offre d'emploi", "on recrute", "nous recrutons", "cherche emploi"
    ])
    print(f"✓ Moteur de mots-clés : {len(keyword_rows)} catégories chargées depuis Supabase\n")

    posts_to_test = random.sample(FAKE_POSTS, min(count, len(FAKE_POSTS)))
    if force_category:
        posts_to_test = [(c, t) for c, t in FAKE_POSTS if c == force_category][:count]

    detected = 0
    filtered = 0
    notified = 0

    for i, (expected_cat, content) in enumerate(posts_to_test, 1):
        group_id, group_name = random.choice(GROUPS)
        author = random.choice(AUTHORS)
        post_id = f"SIM_{datetime.now(timezone.utc).strftime('%H%M%S')}_{i:03d}"
        post_url = f"https://m.facebook.com/groups/{group_id}/posts/{post_id}"

        post = FBPost(
            fb_post_id=post_id,
            group_id=group_id,
            group_name=group_name,
            author_name=author,
            content=content,
            post_url=post_url,
        )

        print(f"[{i:02d}] {author[:15]:<15} │ \"{content[:65]}{'…' if len(content)>65 else ''}\"")

        match = keyword_engine.match(content)

        if match is None:
            if expected_cat is None:
                print(f"      \033[92m✓ Filtré correctement (faux positif évité)\033[0m\n")
            else:
                print(f"      \033[91m✗ Non détecté (attendu: {expected_cat})\033[0m\n")
            filtered += 1
            continue

        conf_color = "\033[92m" if match.confidence >= 0.8 else "\033[93m"
        print(f"      \033[1mDÉTECTÉ\033[0m → [{match.category}]  {conf_color}{int(match.confidence*100)}%\033[0m  mots: {', '.join(match.keywords_found[:3])}")
        detected += 1

        if not dry_run:
            db.save_lead(post, match)
            ok = await notifier.send(post, match)
            if ok:
                db.mark_notified(post.fb_post_id)
                notified += 1
                print(f"      \033[92m✓ Sauvegardé en DB + notification Telegram envoyée\033[0m")
            else:
                print(f"      \033[91m✗ Sauvegardé en DB mais notification Telegram échouée\033[0m")
        else:
            print(f"      \033[2m[dry-run] Pas d'écriture en DB ni Telegram\033[0m")
        print()

        await asyncio.sleep(0.5)

    print(f"{'─'*55}")
    print(f"  Résultats : {detected} détectés  │  {filtered} filtrés  │  {notified} notifiés Telegram")
    if dry_run:
        print(f"  [dry-run] Relance sans --dry-run pour tester Supabase + Telegram")
    print()


def main():
    parser = argparse.ArgumentParser(description="Simulation du pipeline LeadHunt")
    parser.add_argument("--count",    type=int, default=8,   help="Nombre de posts à simuler")
    parser.add_argument("--dry-run",  action="store_true",   help="Sans écriture DB ni Telegram")
    parser.add_argument("--category", default=None,          help="Forcer une catégorie")
    args = parser.parse_args()

    asyncio.run(run_simulation(args.count, args.dry_run, args.category))


if __name__ == "__main__":
    main()
