# PRD — FB Lead Hunter (LeadHunt MVP)

**Version** : 1.0  
**Date** : 2026-05-13  
**Statut** : Validé pour implémentation MVP  

---

## 1. Contexte et problème

Les entrepreneurs indépendants francophones en Israël (artisans, thérapeutes, coachs) ratent systématiquement des demandes de service postées dans des groupes Facebook locaux. Au moment où ils découvrent le post (2h+ après publication), la conversation est enterrée et un concurrent a déjà récupéré le client.

Un seul lead raté représente plusieurs centaines d'euros de manque à gagner (un chantier de plomberie, une consultation ostéopathique, un déménagement). Le problème n'est pas le volume de demandes sur Facebook — il est l'impossibilité humaine de surveiller 10-20 groupes en continu.

---

## 2. Objectif du MVP

Construire un scraper autonome qui :
1. Surveille en continu une liste de groupes Facebook francophones (Israël)
2. Détecte les posts contenant des demandes de prestataires
3. Notifie instantanément l'entrepreneur via Telegram
4. Tourne 7 jours/7 sans intervention humaine

**Périmètre** : usage personnel + 3-5 testeurs (entrepreneurs francophones en Israël).

---

## 3. Utilisateurs cibles

| Persona | Description | Cas d'usage |
|---|---|---|
| Propriétaire système (MVP) | Entrepreneur tech-savvy, pilote via Claude Code | Configure les groupes et mots-clés, reçoit toutes les notifications |
| Testeur entrepreneur | Plombier, ostéo, électricien, serrurier francophone en Israël | Reçoit des alertes sur son Telegram personnel |

---

## 4. Fonctionnalités MVP (scope strict)

### 4.1 Surveillance groupes Facebook

- Liste de groupes FB configurée dans `config.yaml`
- Support de groupes publics et privés (si compte FB membre)
- Scraping cyclique toutes les N minutes (configurable, défaut : 10 min)
- Délais randomisés entre actions pour éviter la détection anti-bot (2-8 secondes)
- Rotation des user-agents (pool de 5 UA desktop réalistes)
- Gestion du scroll pour charger les posts récents (max 20 posts par cycle)

### 4.2 Détection par mots-clés

Catégories de métiers pour le MVP (avec variantes FR/IL) :

| Catégorie | Mots-clés principaux |
|---|---|
| `plomberie` | plombier, plomberie, fuite d'eau, dégât des eaux, chauffe-eau, chauffe eau, robinet |
| `electricite` | électricien, electricien, prise électrique, disjoncteur, tableau électrique, court-circuit |
| `serrurerie` | serrurier, serrure, porte bloquée, clé perdue, verrou, blindage |
| `peinture` | peintre, peinture, enduit, tapisserie, papier peint |
| `bricolage` | bricoleur, bricolage, réparation, montage meuble, assemblage |
| `osteopathie` | ostéopathe, osteopathe, ostéopathie, osteopathie, manipulations, dos, vertèbres |
| `kine` | kiné, kinésithérapeute, kinesitherapeuthe, rééducation, physio |
| `traiteur` | traiteur, buffet, réception, cocktail, livraison repas, cuisine à domicile |
| `demenagement` | déménageur, demenageur, déménagement, demenagement, transport meubles |

Règles de détection :
- Matching insensible à la casse
- Matching insensible aux accents (normalisation Unicode NFD)
- Matching par sous-chaîne (détecte "plombier?" ou "plombièr")
- Score de confiance : 1 mot-clé = match simple, 2+ mots-clés = match fort
- Filtrage des posts négatifs ("je suis plombier" → à exclure si patron "je suis/cherche pas")

### 4.3 Déduplication

- Chaque post FB identifié par son `post_id` (extrait de l'URL ou du DOM)
- Stockage des post_ids détectés dans Supabase (`detected_leads.fb_post_id UNIQUE`)
- Avant notification : vérification en DB (+ cache mémoire en session pour perf)
- Fenêtre de déduplication : permanente (jamais notifier deux fois le même post)

### 4.4 Notifications Telegram

- Bot Telegram dédié (token via BotFather)
- Format de message :
  ```
  🔔 NOUVEAU LEAD — [Catégorie]
  
  📍 Groupe : [Nom du groupe]
  👤 Auteur : [Prénom Nom]
  🕐 Publié : [il y a X minutes]
  
  💬 "[Extrait du post, 200 chars max]"
  
  🔗 [Lien direct vers le post]
  
  🏷 Mots-clés détectés : plombier, fuite
  ```
- Envoi immédiat après détection (pas de batch)
- Retry automatique x3 si échec réseau Telegram

### 4.5 Persistance et logs

- Supabase PostgreSQL (nouveau projet dédié `leadhunt`)
- Tables : `detected_leads`, `monitored_groups`, `keyword_categories`, `scrape_sessions`
- Log structuré en console (niveau INFO/WARNING/ERROR)
- Rotation des logs : fichier `logs/scraper.log` (max 10 MB, 3 rotations)

### 4.6 Configuration

Fichier `config.yaml` — modifiable sans redémarrage du service :
```yaml
scraping:
  interval_minutes: 10
  posts_per_group: 20
  delay_min_seconds: 2
  delay_max_seconds: 8

groups:
  - id: "123456789"
    name: "Francophones Tel Aviv"
    url: "https://www.facebook.com/groups/123456789"
    active: true

keywords:
  # défini via DB (keyword_categories table)
  # config.yaml pointe vers les catégories actives
  active_categories:
    - plomberie
    - electricite
    - serrurerie
    - peinture
    - bricolage
    - osteopathie
    - kine
    - traiteur
    - demenagement
```

---

## 5. Hors scope V1 (explicite)

- Interface web ou dashboard
- Multi-tenant / multi-utilisateurs
- Auto-réponse dans les commentaires
- Gestion de plusieurs comptes Facebook
- Système de paiement
- Analytics
- Mobile app native
- WhatsApp / email / SMS
- Proxy rotatif (anti-détection avancée)

---

## 6. Critères de succès MVP

| Critère | Cible |
|---|---|
| Disponibilité continue | 7 jours sans crash bloquant |
| Taux de détection | ≥ 80 % des posts avec mot-clé |
| Délai post → notification | < 20 minutes |
| Zéro ban compte FB | Pendant toute la phase de test |
| Groupes simultanés | ≥ 10 groupes |
| Faux positifs | < 20 % des notifications |

---

## 7. Contraintes

### Légales / éthiques
- Zone grise CGU Meta : acceptable pour usage personnel/MVP, à reconsidérer si passage en SaaS
- Aucune donnée personnelle des auteurs stockée au-delà du prénom/nom public FB et du post public
- Compte FB secondaire dédié obligatoire (jamais le compte principal)

### Techniques
- L'API Graph FB ne permet pas l'accès aux groupes sans approbation Meta → scraping Playwright obligatoire
- Risque de détection anti-bot : délais randomisés + mimétisme comportemental
- Playwright headless détecté plus facilement → utiliser mode `headless=False` ou stealth plugin

### Infrastructure
- Budget MVP : < 50 €/mois (Hetzner CX11 = 3,49 €/mois + Supabase free tier + Telegram gratuit)

---

## 8. Évolution V2+ (hors scope V1, pour guider l'architecture)

- SaaS multi-tenant : plusieurs entrepreneurs avec leur propre compte FB + groupes + mots-clés
- Dashboard web (Next.js) : configuration, historique leads, CRM basique
- Stripe : abonnement mensuel par utilisateur
- Multi-notification : email, WhatsApp, in-app
- Scoring IA des leads (Claude API) : probabilité que c'est une vraie demande
- Réponse automatique (commentaire FB) au nom du client

---

## 9. Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Ban compte FB | Moyen | Élevé | Compte secondaire, délais humains, pas de scraping la nuit |
| Changement DOM Facebook | Élevé | Moyen | Sélecteurs CSS robustes + tests de régression |
| Faux positifs élevés | Moyen | Faible | Affinage progressif des mots-clés |
| Playwright détecté | Moyen | Élevé | playwright-stealth, user-agents réalistes |
| Panne Supabase | Faible | Moyen | Retry + cache mémoire local |
