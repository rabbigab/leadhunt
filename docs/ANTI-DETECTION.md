# Stratégie Anti-Détection — LeadHunt

## Contexte

L'API Groups Meta a été fermée en avril 2024. Le scraping via Playwright est la seule option viable. Facebook investit massivement dans la détection de bots. Ce document décrit la stratégie de contournement par couche, du MVP jusqu'au SaaS à 100 clients.

---

## Les 5 couches de détection Facebook

| Couche | Mécanisme Facebook | Notre réponse |
|---|---|---|
| **Fingerprint navigateur** | `navigator.webdriver`, Canvas, WebGL, AudioContext | Camoufox (Firefox patché) |
| **Comportement** | Vitesse de scroll, timing entre clics, pattern régulier | `humanize=True` Camoufox + jitter cycle |
| **IP / géolocalisation** | IP datacenter connue = ban quasi-immédiat | Proxies résidentiels rotatifs |
| **Empreinte de session** | Nouveau profil à chaque connexion = suspect | Profil persistant par compte (user_data_dir) |
| **Fréquence** | Trop de requêtes sur un groupe = rate limiting | 15 min d'intervalle + pause nocturne |

---

## Choix technique : Camoufox vs alternatives

| Outil | Détectabilité | Maintenance | Notes |
|---|---|---|---|
| **Camoufox** ✅ | Très faible | Actif (2024-2025) | Firefox patché au niveau binaire — le meilleur actuellement |
| playwright-stealth | Faible-moyenne | Peu actif | JS patches uniquement — Facebook l'a repéré |
| undetected-playwright | Moyenne | Abandonné | Chromium, patches partiels |
| Selenium UC | Moyenne | Actif | Chromium, moins efficace que Camoufox |
| Puppeteer + stealth | Faible | Actif | Node.js uniquement |

**Camoufox = Firefox patché au niveau du code source** — pas juste des patches JS. Il modifie les APIs WebGL, Canvas, AudioContext, `navigator.*` directement dans le binaire Firefox. Facebook ne peut pas détecter le patch via JS.

---

## Proxies résidentiels : guide d'achat

### Pourquoi résidentiel et pas datacenter ?

Facebook maintient une blocklist des plages IP datacenter (AWS, GCP, Hetzner, OVH, DigitalOcean). Une IP datacenter = taux de ban ~80% sur les groupes FB actifs. Une IP résidentielle = taux de ban ~5-10% avec le reste de la stack.

### Fournisseurs recommandés (ordre prix/qualité)

| Fournisseur | Prix | Type | Notes |
|---|---|---|---|
| **Webshare Residential** | ~15€/10 GB | Résidentiel | Le moins cher, qualité correcte pour MVP |
| **Bright Data** | ~50€/10 GB | Résidentiel premium | Meilleure qualité, SLA, APIs |
| **Oxylabs** | ~40€/10 GB | Résidentiel premium | Alternative Bright Data |
| **Smartproxy** | ~20€/10 GB | Résidentiel | Bon rapport qualité/prix |
| **IPRoyal** | ~7€/10 GB | Résidentiel | Moins fiable mais pas cher |

### Consommation estimée

- 1 groupe × 1 cycle = ~500 KB (page mobile Facebook)
- 10 groupes × 96 cycles/jour = ~480 MB/jour
- **1 compte FB, 10 groupes = ~15 GB/mois**
- **10 comptes FB, 100 groupes = ~150 GB/mois** (production)

### Configuration dans `.env`

```bash
PROXY_ENABLED=true
# Pool de proxies — rotation aléatoire à chaque session
PROXY_LIST=http://user:pass@gate.smartproxy.com:7000,http://user:pass@gate.smartproxy.com:7001,http://user:pass@gate.smartproxy.com:7002
```

---

## Architecture scale : 100 clients, 500 groupes (V2)

### Problème

500 groupes × 1 cycle toutes les 15 min = **33 requêtes/min**. Un seul navigateur ne peut pas gérer ça. Il faut paralléliser.

### Solution : Worker Pool

```
┌─────────────────────────────────────────────────────────┐
│                   Task Queue (Redis)                     │
│  [groupe_1, groupe_2, ..., groupe_500] — FIFO           │
└──────────────────────────┬──────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  Worker 1   │ │  Worker 2   │ │  Worker N   │
    │ FB: compte1 │ │ FB: compte2 │ │ FB: compteN │
    │ Proxy: IP_1 │ │ Proxy: IP_2 │ │ Proxy: IP_N │
    │ Camoufox    │ │ Camoufox    │ │ Camoufox    │
    └─────────────┘ └─────────────┘ └─────────────┘
           │               │               │
           └───────────────┼───────────────┘
                           ▼
                  ┌────────────────┐
                  │    Supabase    │
                  │ detected_leads │
                  └────────────────┘
```

**Règles de dimensionnement :**
- 1 worker = 1 compte FB + 1 proxy dédié
- 1 worker = 15-20 groupes max (safe zone anti-ban)
- 500 groupes → 25-33 workers → 25-33 comptes FB secondaires

**Stack V2 :**
- `celery` + Redis pour la task queue
- `asyncio.Semaphore` pour limiter la concurrence par worker
- 1 VPS par tranche de 10 workers (Hetzner CX21 = 5€/mois)

### Budget infrastructure 100 clients / 500 groupes

| Poste | Coût/mois |
|---|---|
| 3 VPS Hetzner CX21 (30 workers) | ~15 € |
| 150 GB proxies résidentiels | ~220 € |
| Supabase Pro (DB) | 25 € |
| Redis (Upstash) | 10 € |
| **Total infra** | **~270 €/mois** |

À 29€/mois par client, 10 clients suffisent pour couvrir l'infra.

---

## Règles d'hygiène anti-ban (à ne jamais violer)

1. **Un compte FB = un VPS / worker** — jamais deux workers sur le même compte
2. **Pause nocturne** — pas de scraping entre 1h et 7h (heure locale)
3. **Intervalle minimum 15 min par groupe** — ne jamais descendre en dessous
4. **Délai 3-10s entre groupes** — randomisé, jamais fixe
5. **Jitter de cycle** — ±5 min sur l'intervalle pour éviter les patterns
6. **Pas de login depuis une nouvelle IP sans warmup** — utiliser les cookies du profil existant
7. **Si CAPTCHA** : arrêt du worker, alerte Telegram, résolution manuelle avant reprise
8. **Rotation des proxies à chaque redémarrage** — pas la même IP toujours

---

## Sélecteurs CSS m.facebook.com — maintenance

Facebook modifie régulièrement son DOM. Procédure quand les posts ne sont plus extraits :

1. Ouvrir `m.facebook.com/groups/[ID]` dans Chrome DevTools
2. Identifier le nouveau sélecteur des blocs de post
3. Mettre à jour `group_reader.py:_parse_page_posts()`
4. Ajouter un test unitaire avec le nouveau sélecteur
5. Pousser le fix (pas besoin de redéployer si le fichier est lu dynamiquement)

**Indicateur de régression :** si `posts_checked` tombe à 0 dans les logs alors que le scraper tourne.
