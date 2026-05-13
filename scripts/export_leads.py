#!/usr/bin/env python3
"""Exporte les leads détectés en CSV ou JSON.

Utile pour partager un rapport avec un client, analyser les faux positifs,
ou importer dans un CRM externe.

Usage :
    python scripts/export_leads.py                        # CSV dernières 24h
    python scripts/export_leads.py --days 7               # 7 derniers jours
    python scripts/export_leads.py --format json          # JSON
    python scripts/export_leads.py --category plomberie   # filtrer par métier
    python scripts/export_leads.py --status new           # seulement les non traités
    python scripts/export_leads.py --all                  # tout l'historique
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
from supabase import create_client

EXPORTS_DIR = ROOT / "exports"


def main():
    parser = argparse.ArgumentParser(description="Export des leads LeadHunt")
    parser.add_argument("--days",     type=int,   default=1,    help="Nombre de jours (défaut: 1)")
    parser.add_argument("--all",      action="store_true",      help="Tout l'historique")
    parser.add_argument("--format",   choices=["csv","json"],   default="csv")
    parser.add_argument("--category", default=None,             help="Filtrer par catégorie")
    parser.add_argument("--status",   default=None,             help="Filtrer par statut (new/contacted/false_positive)")
    parser.add_argument("--output",   default=None,             help="Chemin du fichier de sortie")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ .env manquant")
        sys.exit(1)

    client = create_client(url, key)

    # Construire la requête
    query = client.table("detected_leads").select("*").order("detected_at", desc=True)

    if not args.all:
        since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
        query = query.gte("detected_at", since)

    if args.category:
        query = query.eq("matched_category", args.category)

    if args.status:
        query = query.eq("status", args.status)

    leads = query.execute().data or []

    if not leads:
        print(f"Aucun lead trouvé avec ces critères.")
        return

    # Préparer l'export
    EXPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    suffix = f"_{args.category}" if args.category else ""
    default_name = f"leads_{timestamp}{suffix}.{args.format}"
    output_path = Path(args.output) if args.output else EXPORTS_DIR / default_name

    if args.format == "csv":
        _export_csv(leads, output_path)
    else:
        _export_json(leads, output_path)

    print(f"✅ {len(leads)} lead(s) exporté(s) → {output_path}")
    _print_summary(leads)


def _export_csv(leads: list, path: Path) -> None:
    fields = [
        "detected_at", "matched_category", "author_name", "group_name",
        "post_content", "post_url", "matched_keywords",
        "confidence", "status", "notified", "notified_at"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            row = dict(lead)
            # Convertir la liste en string pour CSV
            kws = row.get("matched_keywords") or []
            row["matched_keywords"] = ", ".join(kws) if isinstance(kws, list) else kws
            row["confidence"] = f"{int((row.get('confidence') or 1) * 100)}%"
            writer.writerow({k: row.get(k, "") for k in fields})


def _export_json(leads: list, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2, default=str)


def _print_summary(leads: list) -> None:
    from collections import Counter
    cats = Counter(l.get("matched_category", "?") for l in leads)
    statuses = Counter(l.get("status", "new") for l in leads)

    print(f"\n  Par catégorie :")
    for cat, n in cats.most_common():
        print(f"    {cat:<20} {n}")
    print(f"\n  Par statut :")
    for st, n in statuses.most_common():
        print(f"    {st:<20} {n}")


if __name__ == "__main__":
    main()
