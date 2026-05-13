# LeadHunt — FB Lead Hunter

Surveillance automatique des groupes Facebook francophones pour détecter les demandes de prestataires et notifier instantanément via Telegram.

## Démarrage rapide

```bash
cp .env.example .env   # Remplir les variables
pip install -r requirements.txt
playwright install chromium
python main.py
```

Voir [docs/SETUP.md](docs/SETUP.md) pour le guide complet.

## Architecture

- **Scraper** : Playwright (Python async) avec playwright-stealth
- **Détection** : moteur de mots-clés multi-catégories, insensible aux accents
- **DB** : Supabase PostgreSQL (déduplication persistante)
- **Notifications** : Bot Telegram

## Structure

```
scraper/facebook/    # Session FB + lecture groupes
scraper/detection/   # Moteur mots-clés + déduplication
scraper/notifications/ # Telegram
scraper/database/    # Client Supabase
```

## Tests

```bash
pytest tests/ -v
```

## Docs

- [PRD](docs/PRD.md) — spécification produit
- [Architecture](docs/ARCHITECTURE.md) — décisions techniques
- [Setup](docs/SETUP.md) — guide d'installation
