#!/usr/bin/env python3
"""Valide que toutes les variables d'environnement et dépendances sont prêtes.

Usage :
    python scripts/check_env.py

Retourne 0 si tout est OK, 1 si des problèmes sont détectés.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

OK    = "\033[92m✓\033[0m"
FAIL  = "\033[91m✗\033[0m"
WARN  = "\033[93m⚠\033[0m"
BOLD  = "\033[1m"
RESET = "\033[0m"

errors = []
warnings = []

def check(label: str, ok: bool, detail: str = "", warn_only: bool = False):
    symbol = OK if ok else (WARN if warn_only else FAIL)
    print(f"  {symbol}  {label}" + (f"  →  {detail}" if detail else ""))
    if not ok:
        (warnings if warn_only else errors).append(label)


# ── Variables d'environnement ──────────────────────────────────────────────

print(f"\n{BOLD}1. Variables d'environnement{RESET}")

REQUIRED = [
    ("SUPABASE_URL",              "URL du projet Supabase leadhunt"),
    ("SUPABASE_SERVICE_ROLE_KEY", "Clé service role Supabase"),
    ("FB_EMAIL",                  "Email du compte Facebook secondaire"),
    ("FB_PASSWORD",               "Mot de passe Facebook"),
    ("TELEGRAM_BOT_TOKEN",        "Token du bot Telegram (@BotFather)"),
    ("TELEGRAM_CHAT_ID",          "Ton chat_id Telegram personnel"),
]

for var, desc in REQUIRED:
    val = os.getenv(var, "")
    check(f"{var}", bool(val), "" if val else f"MANQUANT — {desc}")

OPTIONAL = [
    ("PROXY_ENABLED", "false"),
    ("PROXY_LIST",    ""),
    ("LOG_LEVEL",     "INFO"),
    ("HEADLESS",      "true"),
]
for var, default in OPTIONAL:
    val = os.getenv(var, "")
    check(f"{var}", True, f"{val or default} (défaut)" if not val else val, warn_only=True)


# ── Supabase ───────────────────────────────────────────────────────────────

print(f"\n{BOLD}2. Connexion Supabase{RESET}")
try:
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if url and key:
        client = create_client(url, key)

        # Vérifier les tables
        for table in ["detected_leads", "monitored_groups", "keyword_categories",
                       "scrape_sessions", "fb_accounts", "health_events", "fb_interactions"]:
            try:
                res = client.table(table).select("id").limit(1).execute()
                check(f"Table '{table}'", True)
            except Exception as e:
                check(f"Table '{table}'", False, "non trouvée — appliquer les migrations SQL")

        # Compter les catégories de mots-clés
        try:
            res = client.table("keyword_categories").select("name").eq("is_active", True).execute()
            n = len(res.data or [])
            check(f"Catégories de mots-clés", n >= 9, f"{n}/9 catégories actives")
        except Exception:
            check("Catégories de mots-clés", False, "erreur de lecture")

        # Compter les comptes FB
        try:
            res = client.table("fb_accounts").select("status").execute()
            rows = res.data or []
            active  = sum(1 for r in rows if r["status"] == "active")
            warming = sum(1 for r in rows if r["status"] == "warming")
            check(f"Comptes FB actifs",  active >= 1,  f"{active} actifs (min 1 requis)")
            check(f"Comptes FB warming", warming >= 1, f"{warming} en warming (recommandé 2)", warn_only=warming < 2)
        except Exception:
            check("Comptes FB", False, "erreur de lecture")

        # Vérifier les groupes assignés
        try:
            res = client.table("fb_accounts").select("groups_assigned").eq("status", "active").execute()
            total_groups = sum(len(r.get("groups_assigned") or []) for r in (res.data or []))
            check("Groupes assignés", total_groups >= 1, f"{total_groups} groupe(s) assigné(s)")
        except Exception:
            pass
    else:
        check("Connexion Supabase", False, "SUPABASE_URL ou SERVICE_ROLE_KEY manquant")
except ImportError:
    check("Package supabase", False, "pip install -r requirements.txt")


# ── Telegram ───────────────────────────────────────────────────────────────

print(f"\n{BOLD}3. Connexion Telegram{RESET}")
try:
    import telegram
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        async def test_telegram():
            bot = telegram.Bot(token=token)
            me = await bot.get_me()
            return me.username
        try:
            username = asyncio.run(test_telegram())
            check("Bot Telegram", True, f"@{username}")
        except Exception as e:
            check("Bot Telegram", False, f"token invalide : {e}")
    else:
        check("Bot Telegram", False, "token ou chat_id manquant")
except ImportError:
    check("Package telegram", False, "pip install -r requirements.txt")


# ── Camoufox ───────────────────────────────────────────────────────────────

print(f"\n{BOLD}4. Camoufox (navigateur){RESET}")
try:
    import camoufox
    check("Package camoufox", True, camoufox.__version__ if hasattr(camoufox, "__version__") else "installé")

    # Vérifier que le binaire Firefox est téléchargé
    try:
        from camoufox._utils import get_firefox_executable
        exe = get_firefox_executable()
        check("Binaire Firefox", exe is not None, str(exe) if exe else "manquant — lancer: python -m camoufox fetch")
    except Exception:
        check("Binaire Firefox", False, "lancer: python -m camoufox fetch", warn_only=True)
except ImportError:
    check("Package camoufox", False, "pip install -r requirements.txt")


# ── Fichiers de configuration ──────────────────────────────────────────────

print(f"\n{BOLD}5. Fichiers de configuration{RESET}")
check(".env",        (ROOT / ".env").exists(),        "copier .env.example → .env et remplir")
check("config.yaml", (ROOT / "config.yaml").exists(), "fichier de configuration principal")

# Vérifier que config.yaml a au moins 1 groupe actif
try:
    import yaml
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    groups = [g for g in cfg.get("groups", []) if g.get("active")]
    check("Groupes actifs dans config.yaml", len(groups) >= 1,
          f"{len(groups)} groupe(s) actif(s) — éditer config.yaml pour en ajouter")
except Exception:
    check("Lecture config.yaml", False, "fichier invalide ou manquant")


# ── Résumé ─────────────────────────────────────────────────────────────────

print(f"\n{'─'*50}")
if errors:
    print(f"{FAIL}  {len(error)}  erreur(s) à corriger avant de démarrer :\n")
    for e in errors:
        print(f"     • {e}")
    print()
    sys.exit(1)
elif warnings:
    print(f"{WARN}  Prêt avec {len(warnings)} avertissement(s) non bloquant(s)\n")
    sys.exit(0)
else:
    print(f"{OK}  Tout est prêt — lance : {BOLD}python main.py{RESET}\n")
    sys.exit(0)
