# atelier-trader-bot

Userbot Telegram qui écoute un groupe crypto source, détecte les signaux et analyses via Claude API, les reformate en français et les redistribue sur deux canaux. Suivi de trades en temps réel via l'API publique Binance.

## Fonctionnement

1. Écoute le groupe source via Telethon (userbot)
2. Classification Claude → `signal` | `analyse` | `autre`
3. **Signal** : reformaté en français (structure TP/SL/entrée) + extraction JSON → suivi Binance actif si la paire existe
4. **Analyse** : réécrite en français comme analyse originale
5. **Autre** : ignoré (pub, liens seuls, auto-promo)
6. Publication sur canal privé **et** canal public
7. Polling Binance toutes les 5 min : détection TP/SL via High/Low des bougies 1m
8. Rapport hebdomadaire automatique (lundi 09:00 UTC)

## Setup local (première fois)

```bash
pip install -r requirements.txt
cp .env.example .env   # remplir toutes les variables
python auth.py          # génère userbot.session
python convert_session.py  # convertit en SESSION_STRING
```

## Déploiement Railway

1. Créer un service connecté à ce repo
2. Ajouter un **Volume** monté sur `/data` (persistance SQLite)
3. Renseigner toutes les variables d'environnement (voir `.env.example`)
4. Railway utilise `railway.toml` → `python main.py`

## Variables d'environnement

| Variable | Description |
|---|---|
| `API_ID` | ID API Telegram (my.telegram.org/apps) |
| `API_HASH` | Hash API Telegram |
| `SESSION_STRING` | Session Telethon (convert_session.py) |
| `BOT_TOKEN` | Token bot Telegram (@BotFather) |
| `ANTHROPIC_API_KEY` | Clé API Anthropic |
| `SOURCE_GROUP_ID` | ID du groupe Telegram source |
| `PRIVATE_CHANNEL_ID` | ID du canal privé (100% des signaux) |
| `PUBLIC_CHANNEL_ID` | ID du canal public (100% des signaux) |
| `SOURCE_BLOCKLIST` | Termes bloqués, séparés par virgules |

## Architecture

```
main.py         — handler principal, classification, reformatage
db.py           — SQLite persistant (/data sur Railway Volume)
binance_api.py  — résolution symboles + klines (cache exchangeInfo 1h)
tracker.py      — polling trades toutes les 5 min
scheduler.py    — rapport hebdomadaire
auth.py         — auth locale (une seule fois)
convert_session.py — convertit .session → SESSION_STRING
```

## Protection de la source

- **Layer 1** : blocklist sur le texte brut (avant tout appel API)
- **Layer 2** : classification LLM — auto-promo et vantardise classées `autre`
- **Layer 3** : scrub des termes bloqués sur la sortie reformatée
