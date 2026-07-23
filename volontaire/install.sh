#!/bin/bash
# Install volontaire léger : app + runtime + deps de base.
# PAS de PyTorch / CIFAR ici — téléchargés uniquement à la 1ʳᵉ tâche DL.

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

echo "🔧 Installation volontaire VC-UY (léger, sans Docker, sans ML)..."

# --- Sudo si nécessaire (uniquement pour installer Python/venv) ---
need_sudo=false
if ! command -v python3 &>/dev/null || ! python3 -m venv --help &>/dev/null 2>&1; then
    need_sudo=true
fi
if $need_sudo; then
    if [[ $EUID -ne 0 ]] && ! sudo -v &>/dev/null; then
        echo "❌ Mot de passe sudo requis pour installer Python automatiquement."
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

# --- Environnement virtuel Python ---
echo "🐍 Création de l'environnement virtuel..."
rm -rf venv
python3 -m venv venv
# shellcheck disable=SC1091
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
    pip install django djangorestframework psutil redis requests PyJWT channels daphne
fi

if [[ ! -x venv/bin/daphne ]]; then
    echo "📦 Installation de daphne..."
    pip install daphne channels
fi

echo "🔧 Migrations..."
python manage.py migrate --noinput

echo "🎉 Installation terminée (app légère)."
echo "   Démarrage : ./run.sh"
echo "   PyTorch + datasets : installés automatiquement à la 1ʳᵉ tâche DISTRIBUTED_LEARNING."
echo "   Python : $(pwd)/venv/bin/python"
