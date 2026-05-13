#!/usr/bin/env python3
"""Ajoute un compte Facebook dans Supabase.

Usage :
    python scripts/add_account.py
    python scripts/add_account.py --label "Compte A" --email "user@mail.com" --status warming
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from supabase import create_client
import os

def main():
    parser = argparse.ArgumentParser(description="Ajoute un compte Facebook au système")
    parser.add_argument("--label",  help="Nom du compte (ex: 'Compte A')")
    parser.add_argument("--email",  help="Email Facebook du compte")
    parser.add_argument("--status", choices=["warming", "active"], default="warming",
                        help="Statut initial (défaut: warming)")
    parser.add_argument("--groups", nargs="*", default=[],
                        help="IDs des groupes FB à assigner (uniquement si status=active)")
    args = parser.parse_args()

    # Mode interactif si arguments manquants
    label = args.label or input("Label du compte (ex: 'Compte A') : ").strip()
    email = args.email or input("Email Facebook : ").strip()

    if not label or not email:
        print("❌ Label et email sont requis.")
        sys.exit(1)

    status = args.status
    if not args.label:  # mode interactif
        status_input = input("Statut [warming/active] (défaut: warming) : ").strip()
        if status_input in ("warming", "active"):
            status = status_input

    groups = args.groups
    if status == "active" and not groups and not args.label:
        groups_input = input("IDs des groupes à assigner (séparés par des virgules, ou vide) : ").strip()
        groups = [g.strip() for g in groups_input.split(",") if g.strip()]

    # Connexion Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans .env")
        sys.exit(1)

    client = create_client(url, key)

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "label":               label,
        "fb_email":            email,
        "status":              status,
        "groups_assigned":     groups,
        "warming_started_at":  now if status == "warming" else None,
        "activated_at":        now if status == "active"  else None,
    }

    try:
        res = client.table("fb_accounts").insert(row).execute()
        account_id = res.data[0]["id"]
        print(f"\n✅ Compte ajouté avec succès !")
        print(f"   ID      : {account_id}")
        print(f"   Label   : {label}")
        print(f"   Email   : {email}")
        print(f"   Statut  : {status}")
        if groups:
            print(f"   Groupes : {', '.join(groups)}")
        if status == "warming":
            print(f"\n⏳ Ce compte sera prêt pour la production dans ~21 jours.")
            print(f"   Lance le scraper pour démarrer le warming automatique.")
    except Exception as e:
        print(f"❌ Erreur lors de l'insertion : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
