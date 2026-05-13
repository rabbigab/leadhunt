.PHONY: install check status add-account add-groups test run run-visible logs clean

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

# ── Installation ──────────────────────────────────────────────────
install:
	python3.11 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PYTHON) -m camoufox fetch
	@echo "✅ Installation terminée. Copie .env.example → .env et remplis les variables."

# ── Validation ────────────────────────────────────────────────────
check:
	$(PYTHON) scripts/check_env.py

# ── Gestion des comptes et groupes ───────────────────────────────
add-account:
	$(PYTHON) scripts/add_account.py

add-groups:
	$(PYTHON) scripts/add_groups.py

export:
	$(PYTHON) scripts/export_leads.py

export-week:
	$(PYTHON) scripts/export_leads.py --days 7

test-selectors:
	@read -p "ID du groupe Facebook : " gid; \
	$(PYTHON) scripts/test_selectors.py --group $$gid --visible

simulate:
	$(PYTHON) scripts/simulate.py

simulate-dry:
	$(PYTHON) scripts/simulate.py --dry-run

# ── Dashboard ─────────────────────────────────────────────────────
status:
	$(PYTHON) scripts/status.py

status-leads:
	$(PYTHON) scripts/status.py --leads 20

# ── Tests ─────────────────────────────────────────────────────────
test:
	.venv/bin/pytest tests/ -v

test-fast:
	.venv/bin/pytest tests/ -q

# ── Lancement ─────────────────────────────────────────────────────
run:
	$(PYTHON) main.py

# Premier login : ouvre un vrai navigateur visible
run-visible:
	HEADLESS=false $(PYTHON) main.py

# ── Logs (si systemd) ─────────────────────────────────────────────
logs:
	journalctl -u leadhunt -f

logs-file:
	tail -f logs/scraper.log

# ── Nettoyage ─────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

help:
	@echo ""
	@echo "  make install       — Installer toutes les dépendances"
	@echo "  make check         — Valider l'environnement (.env, Supabase, Telegram)"
	@echo "  make add-account   — Ajouter un compte Facebook"
	@echo "  make add-groups    — Ajouter des groupes à surveiller"
	@echo "  make status        — Dashboard (comptes, leads, alertes)"
	@echo "  make test          — Lancer les tests unitaires"
	@echo "  make run           — Démarrer le scraper (headless)"
	@echo "  make run-visible   — Premier login (navigateur visible)"
	@echo "  make simulate      — Tester le pipeline sans Facebook"
	@echo "  make simulate-dry  — Tester sans écrire en DB"
	@echo "  make export        — Exporter les leads du jour (CSV)"
	@echo "  make export-week   — Exporter les leads des 7 derniers jours"
	@echo "  make test-selectors — Tester les sélecteurs Facebook (debug)"
	@echo "  make logs          — Suivre les logs systemd"
	@echo ""
