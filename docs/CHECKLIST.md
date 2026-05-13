# Checklist de lancement — LeadHunt MVP

Coche chaque étape dans l'ordre. Ne pas sauter d'étape.

---

## PHASE 1 — Infra (toi seul, ~1h)

### Supabase
- [ ] Créer un projet Supabase nommé "leadhunt" sur supabase.com (free tier)
- [ ] Dans **SQL Editor**, coller et exécuter `supabase/migrations/20260513_initial_schema.sql`
- [ ] Dans **SQL Editor**, coller et exécuter `supabase/migrations/20260513_accounts.sql`
- [ ] Vérifier que les 9 catégories sont bien insérées :
      `SELECT name FROM keyword_categories;`
- [ ] Copier **Project URL** et **service_role key** (Settings → API)

### Telegram
- [ ] Ouvrir Telegram → chercher **@BotFather** → `/newbot`
- [ ] Choisir un nom (ex: "LeadHunt Alertes") et un username (ex: `leadhunt_alerts_bot`)
- [ ] Copier le **token** affiché par BotFather
- [ ] Envoyer `/start` au bot depuis ton Telegram personnel
- [ ] Ouvrir dans le navigateur :
      `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`
- [ ] Copier la valeur `"id"` dans `"chat"` → c'est ton **TELEGRAM_CHAT_ID**

### VPS Hetzner (ou machine locale pour les tests)
- [ ] Créer un serveur CX21 sur hetzner.com (Ubuntu 22.04, 4,99€/mois)
- [ ] Se connecter en SSH : `ssh root@IP_DU_VPS`
- [ ] Lancer le script de setup :
      ```bash
      bash <(curl -fsSL https://raw.githubusercontent.com/rabbigab/leadhunt/main/scripts/setup_vps.sh)
      ```

---

## PHASE 2 — Comptes Facebook (toi seul, ~30 min par compte)

> ⚠️ Utilise des comptes **secondaires dédiés**, jamais ton compte principal.
> Chaque compte doit être créé depuis une IP/appareil différent.

### Pour chaque compte (créer 4 actifs + 2 de réserve) :
- [ ] Créer l'adresse email dédiée (Gmail ou Outlook)
- [ ] Acheter une SIM prépayée (~5€) ou utiliser un service SMS virtuel
- [ ] Créer le compte Facebook avec une vraie photo de profil
- [ ] Rejoindre 2-3 groupes publics francophones (pas les groupes cibles)
- [ ] Ne rien faire pendant 48h (laisser le compte "refroidir")

### Ajouter les comptes dans Supabase :
```bash
make add-account
# Répéter pour chaque compte
# Statut : 'warming' pour tous au départ
```

---

## PHASE 3 — Configuration (toi + Claude Code, ~20 min)

### Fichier .env
- [ ] Sur le VPS : `cp .env.example .env && nano .env`
- [ ] Remplir toutes les variables :
  ```
  SUPABASE_URL=https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...
  FB_EMAIL=compte1@email.com          ← compte principal pour les tests
  FB_PASSWORD=motdepasse
  TELEGRAM_BOT_TOKEN=123:ABC...
  TELEGRAM_CHAT_ID=123456789
  PROXY_ENABLED=false                 ← false pour commencer
  HEADLESS=false                      ← false pour le premier login
  ```

### Groupes à surveiller
- [ ] Identifier 5-10 groupes Facebook francophones (Israël)
      Exemples à chercher : "Francophones Israël", "Francophones Tel Aviv",
      "Entraide francophone Israel", "Olim France Israel"
- [ ] Ajouter les groupes :
      ```bash
      make add-groups
      ```
- [ ] Assigner les groupes au compte FB actif quand demandé

---

## PHASE 4 — Premier lancement (toi + Claude Code, ~15 min)

- [ ] Valider la configuration :
      ```bash
      make check
      ```
      → Corriger toute erreur avant de continuer

- [ ] **Premier login Facebook** (navigateur visible) :
      ```bash
      make run-visible
      ```
      → Le navigateur Firefox s'ouvre
      → Le scraper se connecte automatiquement avec FB_EMAIL + FB_PASSWORD
      → Si CAPTCHA : résoudre manuellement dans le navigateur
      → Une fois connecté, les cookies sont sauvegardés dans `sessions/`
      → Ctrl+C pour arrêter après le premier cycle réussi

- [ ] Vérifier que le message de démarrage est arrivé sur Telegram

- [ ] Vérifier dans le dashboard :
      ```bash
      make status
      ```
      → `posts_checked > 0` = ✅ le scraper lit les groupes
      → `leads_found > 0` = ✅ des mots-clés sont détectés (si posts pertinents)

---

## PHASE 5 — Production (toi seul, ~5 min)

- [ ] Passer en mode headless dans `.env` : `HEADLESS=true`
- [ ] Activer le service systemd :
      ```bash
      systemctl enable leadhunt
      systemctl start leadhunt
      systemctl status leadhunt  # doit afficher "active (running)"
      ```
- [ ] Surveiller les logs :
      ```bash
      make logs
      ```
- [ ] Laisser tourner 24h et vérifier :
      ```bash
      make status
      ```

---

## PHASE 6 — Warming des comptes de réserve (automatique, 21 jours)

Le scraper gère automatiquement le warming des comptes en statut `warming`.
Aucune action requise sauf :

- [ ] S'assurer que les comptes de réserve sont dans Supabase avec `status='warming'`
- [ ] Après 21 jours → Telegram t'alerte que le compte est prêt
- [ ] Mettre à jour le statut : `UPDATE fb_accounts SET status='active', groups_assigned=ARRAY['id1',...] WHERE label='Compte B'`

---

## PHASE 7 — Tests avec les premiers clients (semaine 2-3)

- [ ] Partager ton `TELEGRAM_CHAT_ID` avec 3-5 testeurs OU créer un groupe Telegram partagé
- [ ] Adapter les mots-clés selon leurs métiers :
      ```bash
      # Dans Supabase SQL Editor :
      INSERT INTO keyword_categories (name, keywords) VALUES ('nouveau_metier', ARRAY['mot1','mot2']);
      ```
- [ ] Collecter les retours sur les faux positifs → ajuster `negative_patterns` dans `config.yaml`
- [ ] Après 7 jours : vérifier le taux de détection (make status)

---

## Signaux d'alarme à surveiller

| Symptôme | Cause probable | Action |
|---|---|---|
| `posts_checked = 0` depuis 2+ cycles | DOM Facebook changé ou ban | Inspecter m.facebook.com manuellement |
| Alerte Telegram "BAN DÉTECTÉ" | Compte banni | Vérifier le compte FB, activer le backup |
| 0 notification depuis 24h | Pas de post pertinent OU groupes vides | Vérifier les groupes dans config.yaml |
| Erreur `login_fail` répétée | Mot de passe changé ou CAPTCHA | Connexion manuelle + mise à jour .env |
