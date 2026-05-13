# Architecture Technique — FB Lead Hunter MVP

**Version** : 1.0 | **Date** : 2026-05-13

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                    VPS Hetzner CX11                         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  main.py (runner)                    │   │
│  │  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │   │
│  │  │ScheduleLoop│→ │GroupScraper  │→ │KeywordEngine│  │   │
│  │  └────────────┘  └──────────────┘  └──────┬──────┘  │   │
│  │                         ↑                  │         │   │
│  │               ┌─────────────────┐          ↓         │   │
│  │               │  FacebookSession│   ┌─────────────┐  │   │
│  │               └─────────────────┘   │Deduplicator │  │   │
│  │                                     └──────┬──────┘  │   │
│  │                                            │         │   │
│  │                              ┌─────────────▼──────┐  │   │
│  │                              │  TelegramNotifier  │  │   │
│  │                              └────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌─────────────┐  ┌──────────┐  ┌─────────────┐
   │  Supabase   │  │ Telegram │  │  logs/*.log │
   │ PostgreSQL  │  │   Bot    │  │   (local)   │
   └─────────────┘  └──────────┘  └─────────────┘
```

---

## Stack technique

| Composant | Technologie | Justification |
|---|---|---|
| Langage | Python 3.11+ | Écosystème scraping riche, async natif |
| Automation web | Playwright (async) | Meilleur support anti-détection vs Selenium |
| Anti-détection | playwright-stealth | Masque les fingerprints Playwright |
| Base de données | Supabase (PostgreSQL) | Déjà connu, free tier généreux, SDK Python |
| Notifications | python-telegram-bot | API simple, fiable, gratuite |
| Config | PyYAML + python-dotenv | Standard Python |
| Logs | Python logging + RotatingFileHandler | Zero dépendance externe |
| Planification | asyncio + schedule | Pas besoin de Celery pour MVP |
| Hébergement | Hetzner CX11 (3,49€/mois) | Playwright headless fonctionne, IP fixe |
| Tests | pytest + pytest-asyncio | Standard Python |

---

## Structure des fichiers

```
leadhunt/
├── scraper/
│   ├── __init__.py
│   ├── facebook/
│   │   ├── __init__.py
│   │   ├── session.py          # Login FB, gestion cookies, détection expiration
│   │   ├── group_reader.py     # Navigation groupes, extraction posts
│   │   └── post_parser.py      # Parsing DOM → objet Post structuré
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── keyword_engine.py   # Matching mots-clés, normalisation Unicode
│   │   └── deduplication.py   # Cache mémoire + vérif DB
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── telegram.py        # Formatage + envoi messages Telegram
│   ├── database/
│   │   ├── __init__.py
│   │   └── client.py          # Client Supabase, CRUD detected_leads
│   └── config/
│       ├── __init__.py
│       └── settings.py        # Loader config.yaml + .env
├── supabase/
│   └── migrations/
│       └── 20260513_initial_schema.sql
├── tests/
│   ├── test_keyword_engine.py
│   ├── test_deduplication.py
│   └── test_post_parser.py
├── logs/                      # Créé à l'exécution
├── sessions/                  # Cookies FB (créé à l'exécution, gitignored)
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── SETUP.md
├── main.py                    # Entry point
├── config.yaml                # Configuration groupes + mots-clés
├── requirements.txt
├── .env.example
├── .env                       # gitignored
├── .gitignore
└── README.md
```

---

## Modèle de données Supabase

### Table `detected_leads`
```sql
CREATE TABLE detected_leads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fb_post_id      TEXT UNIQUE NOT NULL,     -- ID unique du post FB
  group_id        TEXT NOT NULL,            -- ID du groupe FB
  group_name      TEXT,
  author_name     TEXT,
  post_content    TEXT NOT NULL,
  post_url        TEXT NOT NULL,
  matched_keywords TEXT[] NOT NULL,         -- ex: ['plombier', 'fuite']
  matched_category TEXT NOT NULL,           -- ex: 'plomberie'
  confidence      REAL DEFAULT 1.0,         -- 0.0-1.0
  detected_at     TIMESTAMPTZ DEFAULT NOW(),
  notified        BOOLEAN DEFAULT FALSE,
  notified_at     TIMESTAMPTZ
);
```

### Table `monitored_groups`
```sql
CREATE TABLE monitored_groups (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fb_group_id     TEXT UNIQUE NOT NULL,
  group_name      TEXT NOT NULL,
  group_url       TEXT NOT NULL,
  is_active       BOOLEAN DEFAULT TRUE,
  last_scraped_at TIMESTAMPTZ,
  posts_found     INTEGER DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### Table `keyword_categories`
```sql
CREATE TABLE keyword_categories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT UNIQUE NOT NULL,   -- 'plomberie', 'osteopathie', etc.
  keywords    TEXT[] NOT NULL,
  is_active   BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### Table `scrape_sessions`
```sql
CREATE TABLE scrape_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at      TIMESTAMPTZ DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  groups_scraped  INTEGER DEFAULT 0,
  posts_checked   INTEGER DEFAULT 0,
  leads_found     INTEGER DEFAULT 0,
  errors          TEXT[] DEFAULT '{}'
);
```

---

## Flux d'exécution

```
main.py démarre
    │
    ├─ Charge config.yaml + .env
    ├─ Initialise SupabaseClient
    ├─ Lance FacebookSession.login() (ou charge cookies)
    │
    └─ Boucle toutes les N minutes :
           │
           ├─ Pour chaque groupe actif :
           │       │
           │       ├─ GroupReader.fetch_recent_posts(group_url, limit=20)
           │       │       → Playwright scrolle la page, extrait les posts
           │       │
           │       └─ Pour chaque post :
           │               │
           │               ├─ Deduplicator.is_known(fb_post_id) ?
           │               │       → OUI : skip
           │               │       → NON : continuer
           │               │
           │               ├─ KeywordEngine.match(post_content)
           │               │       → aucun match : skip
           │               │       → match trouvé : continuer
           │               │
           │               ├─ SupabaseClient.save_lead(post_data)
           │               ├─ Deduplicator.mark_known(fb_post_id)
           │               └─ TelegramNotifier.send(lead_data)
           │
           └─ Sleep(interval - elapsed)
```

---

## Gestion de session Facebook

La session FB est le composant le plus fragile. Stratégie :

1. **Login initial** : Playwright remplit le formulaire login.facebook.com avec les credentials du `.env`
2. **Persistence cookies** : Sauvegarde dans `sessions/fb_cookies.json` après login réussi
3. **Réutilisation** : Au démarrage, tente de charger les cookies. Si session valide → pas de re-login
4. **Détection expiration** : Si redirect vers login ou CAPTCHA → re-login automatique
5. **Cooldown anti-ban** : 
   - Pause 2-8s entre chaque groupe (randomisée)
   - Pause 30-60s si 429 ou erreur détection bot
   - Pas de scraping entre 2h-7h (heure locale)

---

## Anti-détection (résumé)

- `playwright-stealth` : masque `navigator.webdriver`, fingerprints JS
- User-agent pool : 5 UA Chrome desktop récents, rotation par session
- Viewport aléatoire : 1366x768, 1440x900, 1920x1080
- Mouvements souris simulés avant interactions clés
- Délais randomisés exponentiels en cas d'erreur

---

## Hébergement recommandé : Hetzner CX11

- CPU : 2 vCPU AMD | RAM : 2 GB | Stockage : 40 GB NVMe
- OS : Ubuntu 22.04 LTS
- Prix : 3,49 €/mois
- Setup : Python 3.11 + Playwright + systemd service

Commande systemd pour faire tourner le scraper en continu :
```ini
[Unit]
Description=LeadHunt Scraper
After=network.target

[Service]
Type=simple
User=leadhunt
WorkingDirectory=/home/leadhunt/leadhunt
ExecStart=/home/leadhunt/leadhunt/.venv/bin/python main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

---

## Variables d'environnement (.env)

```bash
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...  # pour les writes

# Facebook (compte secondaire dédié !)
FB_EMAIL=moncompte@email.com
FB_PASSWORD=motdepasse

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789  # ton chat_id personnel

# Optionnel
LOG_LEVEL=INFO
HEADLESS=true  # false pour debug local
```

---

## Évolutivité vers V2 (SaaS)

L'architecture MVP est conçue pour évoluer :

- **Multi-tenant** : ajouter `user_id UUID REFERENCES auth.users` sur toutes les tables
- **API REST** : exposer une API FastAPI devant le scraper
- **Dashboard** : Next.js consommant Supabase directement (Realtime pour notifs in-app)
- **Queue** : remplacer asyncio par Celery + Redis pour scaling horizontal
- **Multi-comptes FB** : pool de sessions, assignation round-robin par utilisateur
