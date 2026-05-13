#!/usr/bin/env python3
"""Dashboard de statut LeadHunt.

Usage :
    python scripts/status.py
    python scripts/status.py --leads 20    # affiche les 20 derniers leads
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os
from supabase import create_client

BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELL  = "\033[93m"
CYAN  = "\033[96m"
RESET = "\033[0m"
DIM   = "\033[2m"


def ago(iso_str: str) -> str:
    if not iso_str:
        return "jamais"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        s = int(diff.total_seconds())
        if s < 60:     return f"il y a {s}s"
        if s < 3600:   return f"il y a {s//60}min"
        if s < 86400:  return f"il y a {s//3600}h"
        return f"il y a {s//86400}j"
    except Exception:
        return iso_str[:16]


def status_color(status: str) -> str:
    colors = {"active": GREEN, "warming": YELL, "banned": RED, "retired": DIM}
    return colors.get(status, RESET) + status.upper() + RESET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads", type=int, default=10, help="Nombre de leads récents à afficher")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ .env manquant")
        sys.exit(1)

    client = create_client(url, key)

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  LeadHunt — Dashboard  {DIM}{datetime.now().strftime('%d/%m/%Y %H:%M')}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # ── Comptes FB ────────────────────────────────────────────────
    print(f"\n{BOLD}{CYAN}Comptes Facebook{RESET}")
    try:
        accounts = client.table("fb_accounts").select("*").order("created_at").execute().data or []
        if not accounts:
            print("  Aucun compte configuré — lance: python scripts/add_account.py")
        for acc in accounts:
            groups_n = len(acc.get("groups_assigned") or [])
            zero     = acc.get("consecutive_zero_cycles", 0)
            leads    = acc.get("total_leads_found", 0)
            scraped  = ago(acc.get("last_scrape_at", ""))
            interacted = ago(acc.get("last_interaction_at", ""))

            # Warming progress
            extra = ""
            if acc["status"] == "warming" and acc.get("warming_started_at"):
                try:
                    start = datetime.fromisoformat(acc["warming_started_at"].replace("Z", "+00:00"))
                    days  = (datetime.now(timezone.utc) - start).days
                    extra = f"  {DIM}J{days}/21{RESET}"
                except Exception:
                    pass

            warn = f"  {RED}⚠ {zero} cycles vides{RESET}" if zero >= 2 else ""
            print(f"  {status_color(acc['status']):<30} {BOLD}{acc['label']}{RESET}{extra}")
            print(f"    {DIM}{acc['fb_email']}{RESET}")
            print(f"    Groupes: {groups_n}  │  Leads trouvés: {leads}  │  Dernier scrape: {scraped}  │  Dernière interaction: {interacted}{warn}")
    except Exception as e:
        print(f"  ❌ Erreur : {e}")

    # ── Événements de santé récents ───────────────────────────────
    print(f"\n{BOLD}{CYAN}Alertes santé récentes{RESET}")
    try:
        events = (
            client.table("health_events")
            .select("*, fb_accounts(label)")
            .eq("resolved", False)
            .order("created_at", desc=True)
            .limit(5)
            .execute().data or []
        )
        if not events:
            print(f"  {GREEN}Aucune alerte active{RESET}")
        for ev in events:
            label = (ev.get("fb_accounts") or {}).get("label", "?")
            print(f"  {RED}●{RESET} [{ago(ev['created_at'])}] {label} — {ev['event_type']}  {DIM}{ev.get('details','')}{RESET}")
    except Exception as e:
        print(f"  ❌ Erreur : {e}")

    # ── Stats globales ────────────────────────────────────────────
    print(f"\n{BOLD}{CYAN}Statistiques{RESET}")
    try:
        total_leads = client.table("detected_leads").select("id", count="exact").execute().count or 0
        today_leads = (
            client.table("detected_leads")
            .select("id", count="exact")
            .gte("detected_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00"))
            .execute().count or 0
        )
        sessions = client.table("scrape_sessions").select("posts_checked, leads_found").order("started_at", desc=True).limit(10).execute().data or []
        avg_posts = int(sum(s["posts_checked"] for s in sessions) / len(sessions)) if sessions else 0
        print(f"  Leads détectés : {BOLD}{total_leads}{RESET} total  │  {BOLD}{today_leads}{RESET} aujourd'hui")
        print(f"  Moyenne posts/cycle (10 derniers) : {avg_posts}")
    except Exception as e:
        print(f"  ❌ Erreur : {e}")

    # ── Derniers leads ────────────────────────────────────────────
    print(f"\n{BOLD}{CYAN}Derniers leads détectés{RESET}")
    try:
        leads = (
            client.table("detected_leads")
            .select("*")
            .order("detected_at", desc=True)
            .limit(args.leads)
            .execute().data or []
        )
        if not leads:
            print("  Aucun lead pour l'instant")
        for lead in leads:
            conf   = int(lead.get("confidence", 1) * 100)
            cat    = lead.get("matched_category", "?")
            author = lead.get("author_name", "?")
            group  = lead.get("group_name", "?")
            kws    = ", ".join((lead.get("matched_keywords") or [])[:3])
            notif  = f"{GREEN}notifié{RESET}" if lead.get("notified") else f"{YELL}non notifié{RESET}"
            excerpt = (lead.get("post_content") or "")[:80].replace("\n", " ")
            print(f"\n  {BOLD}[{cat.upper()}]{RESET} {conf}% — {ago(lead['detected_at'])}  ({notif})")
            print(f"  {DIM}{author} dans {group}{RESET}")
            print(f"  {DIM}Mots-clés: {kws}{RESET}")
            print(f"  \"{excerpt}…\"")
    except Exception as e:
        print(f"  ❌ Erreur : {e}")

    print(f"\n{DIM}{'─'*60}{RESET}\n")

if __name__ == "__main__":
    main()
