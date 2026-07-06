#!/bin/bash

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

echo "🔧 Installation volontaire VC-UY (tout automatique)..."
echo "   Branche Git attendue : main"

# --- Sudo si nécessaire (apt, docker) ---
need_sudo=false
if ! command -v python3 &>/dev/null || ! python3 -m venv --help &>/dev/null 2>&1; then
    need_sudo=true
fi
if ! command -v docker &>/dev/null; then
    need_sudo=true
fi
if $need_sudo; then
    if [[ $EUID -ne 0 ]] && ! sudo -v &>/dev/null; then
        echo "❌ Mot de passe sudo requis pour installer Python/Docker automatiquement."
        exit 1
    fi
fi

# --- Python 3 + venv ---
if ! command -v python3 &>/dev/null; then
    echo "📦 Installation de Python 3..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-venv python3-pip
fi
if ! python3 -m venv --help &>/dev/null 2>&1; then
    echo "📦 Installation de python3-venv..."
    sudo apt-get update -qq
    sudo apt-get install -y python3-venv python3-pip
fi
echo "✅ Python 3 prêt."

# --- Docker ---
docker_cmd() {
    if docker info &>/dev/null 2>&1; then
        docker "$@"
    elif sg docker -c "docker $*" 2>/dev/null; then
        :
    else
        sudo docker "$@"
    fi
}

if ! command -v docker &>/dev/null; then
    echo "📦 Installation de Docker..."
    sudo apt-get update -qq
    sudo apt-get install -y docker.io
fi
sudo service docker start 2>/dev/null || sudo systemctl start docker 2>/dev/null || true
if [[ $EUID -ne 0 ]]; then
    sudo usermod -aG docker "$USER" 2>/dev/null || true
fi
echo "✅ Docker prêt."

# --- Image Docker malaria ---
if [[ -f task_docker_img/image-docker.tar ]]; then
    echo "📦 Chargement de l'image Docker..."
    docker_cmd image load -i task_docker_img/image-docker.tar
elif ! docker_cmd image inspect malaria-exp:latest &>/dev/null 2>&1; then
    echo "📦 Téléchargement de l'image malaria-exp:latest..."
    docker_cmd pull malaria-exp:latest 2>/dev/null || echo "⚠️ Image malaria : sera tirée à la première tâche."
fi

# --- Environnement virtuel Python ---
echo "🐍 Création de l'environnement virtuel..."
rm -rf venv
python3 -m venv venv
source venv/bin/activate

mkdir -p .volunteer/tasks .volunteer/temp_data

# --- Dépendances Python (requirements à la racine du repo ou local) ---
echo "📦 Installation des dépendances Python..."
pip install --upgrade pip -q
REQ="requirements.txt"
[[ -f "$REQ" ]] || REQ="../requirements.txt"
if [[ -f "$REQ" ]]; then
    pip install -r "$REQ"
else
    pip install django djangorestframework docker psutil redis requests PyJWT channels daphne
fi

if [[ ! -x venv/bin/daphne ]]; then
    echo "📦 Installation de daphne..."
    pip install daphne channels
fi

echo "🔧 Migrations..."
python manage.py migrate --noinput

echo "🎉 Installation terminée."
if ! docker info &>/dev/null 2>&1; then
    echo ""
    echo "⚠️  Docker est installé mais l'accès est refusé pour $USER."
    echo "    Exécutez : newgrp docker"
    echo "    Puis relancez : ./install-volontaire.sh"
fi
