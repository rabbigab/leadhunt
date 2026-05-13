#!/bin/bash
# Setup automatisé d'un VPS Ubuntu 22.04 pour LeadHunt
# Testé sur Hetzner CX21 (2 vCPU, 4 GB RAM, 40 GB SSD) — 4,99€/mois
#
# Usage (depuis ta machine locale) :
#   ssh root@IP_DU_VPS "bash <(curl -fsSL https://raw.githubusercontent.com/rabbigab/leadhunt/main/scripts/setup_vps.sh)"
#
# Ou depuis le VPS directement :
#   curl -fsSL https://raw.githubusercontent.com/rabbigab/leadhunt/main/scripts/setup_vps.sh | bash

set -euo pipefail

REPO_URL="https://github.com/rabbigab/leadhunt.git"
APP_USER="leadhunt"
APP_DIR="/home/${APP_USER}/leadhunt"
BRANCH="main"

echo "================================================"
echo "  LeadHunt VPS Setup — Ubuntu 22.04"
echo "================================================"

# ── 1. Mise à jour système ────────────────────────────────────────
echo "[1/8] Mise à jour du système..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq git curl wget unzip htop

# ── 2. Python 3.11 ───────────────────────────────────────────────
echo "[2/8] Installation Python 3.11..."
apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip

# ── 3. Dépendances système pour Playwright/Camoufox ──────────────
echo "[3/8] Dépendances système pour le navigateur headless..."
apt-get install -y -qq \
  libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libdbus-1-3 libxrandr2 libgbm1 libasound2 \
  libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
  libxshmfence1 libgtk-3-0 libpangocairo-1.0-0 \
  fonts-liberation fonts-noto-color-emoji

# ── 4. Créer l'utilisateur dédié ─────────────────────────────────
echo "[4/8] Création de l'utilisateur ${APP_USER}..."
if ! id "${APP_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${APP_USER}"
  echo "Utilisateur ${APP_USER} créé."
else
  echo "Utilisateur ${APP_USER} existe déjà."
fi

# ── 5. Cloner le repo ─────────────────────────────────────────────
echo "[5/8] Clonage du repo LeadHunt..."
sudo -u "${APP_USER}" bash -c "
  if [ -d '${APP_DIR}' ]; then
    cd '${APP_DIR}' && git pull origin ${BRANCH}
  else
    git clone --branch ${BRANCH} ${REPO_URL} ${APP_DIR}
  fi
"

# ── 6. Environnement Python + dépendances ────────────────────────
echo "[6/8] Installation des dépendances Python..."
sudo -u "${APP_USER}" bash -c "
  cd '${APP_DIR}'
  python3.11 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
"

# ── 7. Télécharger le binaire Firefox (Camoufox) ─────────────────
echo "[7/8] Téléchargement de Firefox (Camoufox) — peut prendre 2-3 min..."
sudo -u "${APP_USER}" bash -c "
  cd '${APP_DIR}'
  .venv/bin/python -m camoufox fetch
"

# ── 8. Service systemd ───────────────────────────────────────────
echo "[8/8] Configuration du service systemd..."
cat > /etc/systemd/system/leadhunt.service << EOF
[Unit]
Description=LeadHunt Facebook Scraper
After=network.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
# Variables d'environnement chargées depuis .env
EnvironmentFile=${APP_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
# Ne pas activer/démarrer ici — attendre que .env soit rempli

echo ""
echo "================================================"
echo "  Installation terminée !"
echo "================================================"
echo ""
echo "Prochaines étapes :"
echo ""
echo "  1. Copier et remplir le fichier .env :"
echo "     cp ${APP_DIR}/.env.example ${APP_DIR}/.env"
echo "     nano ${APP_DIR}/.env"
echo ""
echo "  2. Valider la configuration :"
echo "     sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python ${APP_DIR}/scripts/check_env.py"
echo ""
echo "  3. Ajouter les comptes Facebook :"
echo "     sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python ${APP_DIR}/scripts/add_account.py"
echo ""
echo "  4. Premier login Facebook (nécessite un écran ou VNC) :"
echo "     sudo -u ${APP_USER} HEADLESS=false ${APP_DIR}/.venv/bin/python ${APP_DIR}/main.py"
echo ""
echo "  5. Démarrer le service en production :"
echo "     systemctl enable leadhunt && systemctl start leadhunt"
echo "     journalctl -u leadhunt -f"
echo ""
