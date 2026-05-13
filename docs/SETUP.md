# Guide de setup — LeadHunt MVP

## Prérequis

- Python 3.11+
- Un compte Facebook **secondaire dédié** (jamais ton compte principal)
- Un projet Supabase dédié "leadhunt" (créer sur supabase.com)
- Un bot Telegram (créer via @BotFather)
- Un VPS (recommandé : Hetzner CX11, 3,49 €/mois) ou machine locale pour les tests

---

## 1. Cloner et installer

```bash
git clone https://github.com/rabbigab/leadhunt.git
cd leadhunt
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## 2. Variables d'environnement

```bash
cp .env.example .env
# Editer .env avec tes vraies valeurs
```

Variables à renseigner dans `.env` :
- `SUPABASE_URL` : URL de ton projet Supabase leadhunt
- `SUPABASE_SERVICE_ROLE_KEY` : clé service role (Settings → API)
- `FB_EMAIL` + `FB_PASSWORD` : compte Facebook secondaire dédié
- `TELEGRAM_BOT_TOKEN` : token du bot (créé via @BotFather → /newbot)
- `TELEGRAM_CHAT_ID` : ton chat_id Telegram

### Trouver ton TELEGRAM_CHAT_ID

1. Envoie `/start` à ton bot Telegram
2. Ouvre dans le navigateur : `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`
3. Cherche `"chat": {"id": XXXXXXX}` — c'est ton chat_id

---

## 3. Base de données Supabase

Dans le SQL Editor de ton projet Supabase, colle et exécute :

```
supabase/migrations/20260513_initial_schema.sql
```

Vérifie que les 9 catégories de mots-clés sont bien insérées :
```sql
SELECT name, array_length(keywords, 1) AS nb_keywords FROM keyword_categories;
```

---

## 4. Configuration des groupes

Édite `config.yaml` et remplace les exemples :

```yaml
groups:
  - id: "VRAI_ID_GROUPE"
    name: "Francophones Tel Aviv"
    url: "https://www.facebook.com/groups/VRAI_ID_GROUPE"
    active: true
```

**Comment trouver l'ID d'un groupe FB ?**
- Va sur le groupe → regarde l'URL : `facebook.com/groups/XXXXXX` → XXXXXX est l'ID

---

## 5. Premier lancement (test local)

```bash
# Mode visible (recommandé pour le premier test)
HEADLESS=false python main.py
```

Au premier lancement :
1. Playwright ouvre Chrome
2. Se connecte à Facebook avec tes credentials
3. Sauvegarde les cookies dans `sessions/fb_cookies.json`
4. Envoie un message Telegram de confirmation
5. Lance la boucle de scraping

---

## 6. Lancement en production (VPS)

### Sur le VPS (Ubuntu 22.04)

```bash
# Installer Python et dépendances système
sudo apt update && sudo apt install -y python3.11 python3.11-venv
sudo apt install -y libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libdbus-1-3 libxrandr2 libgbm1 libasound2

# Créer l'utilisateur dédié
sudo useradd -m -s /bin/bash leadhunt
sudo su - leadhunt

# Cloner et installer
git clone https://github.com/rabbigab/leadhunt.git
cd leadhunt
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps
```

### Configurer le service systemd

```bash
sudo cp docs/leadhunt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable leadhunt
sudo systemctl start leadhunt
```

### Surveiller les logs

```bash
sudo journalctl -u leadhunt -f
# ou directement
tail -f /home/leadhunt/leadhunt/logs/scraper.log
```

---

## 7. Lancer les tests

```bash
pytest tests/ -v
```

---

## Dépannage courant

| Problème | Solution |
|---|---|
| `playwright._impl._errors.TimeoutError` | Facebook a changé le DOM — mettre à jour les sélecteurs dans `group_reader.py` |
| `KeyError: 'SUPABASE_URL'` | Le fichier `.env` n'est pas chargé — vérifier qu'il est dans le répertoire racine |
| Session expirée au bout de quelques jours | Normal — le re-login automatique devrait gérer, si non : supprimer `sessions/fb_cookies.json` et relancer |
| CAPTCHA FB au login | Utiliser `HEADLESS=false` pour résoudre manuellement, puis relancer en headless |
| Trop de faux positifs | Ajouter des patterns dans `negative_patterns` dans `config.yaml` |
