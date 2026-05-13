#!/usr/bin/env python3
"""Ajoute des groupes Facebook à surveiller et les assigne à un compte.

Usage :
    python scripts/add_groups.py

Le script :
1. Demande l'URL ou l'ID du groupe
2. L'insère dans monitored_groups
3. Propose de l'assigner à un compte actif dans fb_accounts
4. Met à jour config.yaml automatiquement
"""

import re
import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
from supabase import create_client

CONFIG_PATH = ROOT / "config.yaml"


def extract_group_id(url_or_id: str) -> tuple[str, str]:
    """Retourne (group_id, clean_url)."""
    url_or_id = url_or_id.strip()
    # Si c'est juste un ID numérique
    if url_or_id.isdigit():
        return url_or_id, f"https://www.facebook.com/groups/{url_or_id}"
    # Extraire depuis une URL
    m = re.search(r"facebook\.com/groups/([^/?]+)", url_or_id)
    if m:
        gid = m.group(1)
        return gid, f"https://www.facebook.com/groups/{gid}"
    return url_or_id, f"https://www.facebook.com/groups/{url_or_id}"


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis dans .env")
        sys.exit(1)

    client = create_client(url, key)

    print("\n=== Ajout de groupes Facebook ===")
    print("Entre 'fin' pour terminer.\n")

    added_groups = []

    while True:
        raw = input("URL ou ID du groupe Facebook : ").strip()
        if raw.lower() in ("fin", "exit", "q", ""):
            break

        group_id, group_url = extract_group_id(raw)
        name = input(f"Nom du groupe : ").strip() or f"Groupe {group_id}"

        # Insérer dans Supabase
        try:
            client.table("monitored_groups").upsert({
                "fb_group_id": group_id,
                "group_name":  name,
                "group_url":   group_url,
                "is_active":   True,
            }, on_conflict="fb_group_id").execute()
            print(f"  ✅ '{name}' ajouté dans Supabase")
            added_groups.append({"id": group_id, "name": name, "url": group_url})
        except Exception as e:
            print(f"  ❌ Erreur Supabase : {e}")
            continue

        another = input("Ajouter un autre groupe ? [o/N] : ").strip().lower()
        if another != "o":
            break

    if not added_groups:
        print("Aucun groupe ajouté.")
        return

    # Assigner à un compte actif
    try:
        res = client.table("fb_accounts").select("id, label, groups_assigned").eq("status", "active").execute()
        accounts = res.data or []
    except Exception:
        accounts = []

    if accounts:
        print(f"\n=== Assigner les groupes à un compte actif ===")
        for i, acc in enumerate(accounts):
            nb = len(acc.get("groups_assigned") or [])
            print(f"  {i+1}. {acc['label']} ({nb} groupes assignés)")
        print(f"  0. Ne pas assigner maintenant")

        choice = input("Choix : ").strip()
        if choice.isdigit() and 0 < int(choice) <= len(accounts):
            acc = accounts[int(choice) - 1]
            existing = acc.get("groups_assigned") or []
            new_ids = [g["id"] for g in added_groups if g["id"] not in existing]
            updated = existing + new_ids
            client.table("fb_accounts").update(
                {"groups_assigned": updated}
            ).eq("id", acc["id"]).execute()
            print(f"  ✅ {len(new_ids)} groupe(s) assigné(s) à '{acc['label']}'")

    # Mettre à jour config.yaml
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)

        existing_ids = {g["id"] for g in cfg.get("groups", [])}
        for g in added_groups:
            if g["id"] not in existing_ids:
                cfg.setdefault("groups", []).append({
                    "id":    g["id"],
                    "name":  g["name"],
                    "url":   g["url"],
                    "active": True,
                })

        with open(CONFIG_PATH, "w") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        print(f"\n✅ config.yaml mis à jour avec {len(added_groups)} nouveau(x) groupe(s)")
    except Exception as e:
        print(f"⚠️  Impossible de mettre à jour config.yaml : {e}")
        print(f"   Ajouter manuellement dans config.yaml :")
        for g in added_groups:
            print(f"   - id: \"{g['id']}\"\n     name: \"{g['name']}\"\n     url: \"{g['url']}\"\n     active: true")

    print(f"\n✅ Terminé. Redémarre le scraper pour prendre en compte les nouveaux groupes.")

if __name__ == "__main__":
    main()
