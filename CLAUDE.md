# CLAUDE.md — LeadHunt

Instructions pour Claude Code lors des sessions de travail sur ce projet.

---

## Le projet en une phrase

**LeadHunt** est un scraper Python qui surveille des groupes Facebook francophones, détecte les demandes de prestataires (plombier, ostéopathe, etc.) et notifie instantanément via Telegram.

---

## Commandes essentielles

```bash
make install        # Setup complet (venv + dépendances + Firefox Camoufox)
make check          # Valider env (.env, Supabase, Telegram, Camoufox)
make run-visible    # Premier login Facebook (navigateur visible)
make run            # Scraper en production (headless)
make status         # Dashboard comptes + leads
make add-account    # Ajouter un compte FB
make add-groups     # Ajouter des groupes à surveiller
make test           # Tests unitaires
```

---

## Architecture

```
main.py                        — Runner asyncio : 1 worker par compte FB actif
scraper/
  facebook/
    session.py                 — Camoufox + profil persistant + proxy optionnel
    group_reader.py            — Lecture m.facebook.com (version mobile)
    post_parser.py             — Extraction post_id, texte, auteur
    interaction_bot.py         — Likes automatiques + commentaires naturels
  accounts/
    manager.py                 — Multi-comptes, détection ban, basculement
    warmup.py                  — Protocole warming 3 semaines automatisé
    health_monitor.py          — Alertes Telegram ban/erreurs
  detection/
    keyword_engine.py          — Matching mots-clés, insensible aux accents
    deduplication.py           — Cache mémoire + vérification Supabase
  notifications/
    telegram.py                — Envoi Telegram avec retry x3
  database/
    client.py                  — Client Supabase (leads, comptes, sessions)
  config/
    settings.py                — Loader .env + variables
scripts/
  check_env.py                 — Valide toute la config avant de démarrer
  add_account.py               — Ajoute un compte FB dans Supabase
  add_groups.py                — Ajoute des groupes + met à jour config.yaml
  status.py                    — Dashboard terminal
  setup_vps.sh                 — Setup automatisé VPS Ubuntu 22.04
supabase/migrations/
  20260513_initial_schema.sql  — Tables leads, groupes, mots-clés, sessions
  20260513_accounts.sql        — Tables fb_accounts, health_events, interactions
```

---

## Stack technique

| Composant | Technologie |
|---|---|
| Langage | Python 3.11+ async |
| Navigateur | Camoufox (Firefox patché, anti-détection) |
| Base de données | Supabase (PostgreSQL) |
| Notifications | python-telegram-bot |
| Config | PyYAML + python-dotenv |
| Tests | pytest |
| Hébergement | Hetzner CX21 (4,99€/mois) |

---

## Variables d'environnement critiques

| Variable | Description |
|---|---|
| `SUPABASE_URL` | URL du projet Supabase leadhunt |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé service role (pas la clé anon) |
| `FB_EMAIL` | Email du compte Facebook secondaire |
| `FB_PASSWORD` | Mot de passe Facebook |
| `TELEGRAM_BOT_TOKEN` | Token du bot (@BotFather) |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram du propriétaire |
| `PROXY_ENABLED` | `true` / `false` |
| `PROXY_LIST` | URLs de proxies séparées par des virgules |
| `HEADLESS` | `true` en production, `false` pour déboguer |

---

## Gestion des comptes Facebook

Les comptes sont stockés dans la table `fb_accounts` de Supabase.

**Cycle de vie d'un compte :**
```
warming (21 jours) → active → [banni] → remplacé par prochain warming
```

**Ajouter un compte :**
```bash
make add-account
# ou directement dans Supabase : INSERT INTO fb_accounts (label, fb_email, status, warming_started_at) VALUES (...)
```

**Assigner des groupes à un compte actif :**
- Via `make add-groups` (interactif)
- Ou directement dans Supabase : `UPDATE fb_accounts SET groups_assigned = ARRAY['id1','id2'] WHERE label = 'Compte A'`

---

## Détection de ban

Le `HealthMonitor` détecte automatiquement les bans :
- **Seuil** : 3 cycles consécutifs avec 0 posts extraits
- **Action** : marque le compte `banned`, tente de promouvoir le compte de secours le plus avancé
- **Alerte** : notification Telegram immédiate

---

## Ajouter un nouveau métier/catégorie

1. Insérer dans Supabase :
   ```sql
   INSERT INTO keyword_categories (name, keywords)
   VALUES ('nouveau_metier', ARRAY['mot1', 'mot2', 'mot3']);
   ```
2. Ajouter dans `config.yaml` → `keywords.active_categories`
3. Redémarrer le scraper

---

## Anti-détection — règles à ne pas violer

1. Intervalle minimum : **15 min par groupe** (ne pas descendre)
2. Pause nocturne : **1h→7h** (configuré dans `config.yaml`)
3. Un compte FB = un worker = un profil browser persistant
4. Ne jamais créer de nouveau contexte browser sans raison
5. Toujours exécuter `interaction_bot.run_feed_warmup()` en début de session
6. Si CAPTCHA → arrêt immédiat, alerte, résolution manuelle

---

## Workflow de développement

1. Modifier le code
2. `make test` — vérifier que les tests passent
3. `make check` — valider l'env
4. Commit + push → la branche `main` est déployée automatiquement si systemd est configuré avec `git pull`

---

## Maintenance courante

**DOM Facebook cassé** (symptôme : `posts_checked = 0` sur tous les groupes) :
→ Inspecter `m.facebook.com/groups/[id]` dans Chrome DevTools
→ Mettre à jour les sélecteurs dans `scraper/facebook/group_reader.py`

**Compte banni** :
→ Le système bascule automatiquement si un compte warming est disponible
→ Créer un nouveau compte de remplacement : `make add-account`

**Ajouter un groupe** :
→ `make add-groups`
