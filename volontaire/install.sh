#!/bin/bash

set -e  # Arrête le script en cas d'erreur

# === Fonctions de vérification ===

function check_command {
    if ! command -v "$1" &>/dev/null; then
        echo "❌ $1 n'est pas installé. Installation en cours..."
        return 1
    else
        echo "✅ $1 est déjà installé."
        return 0
    fi
}

function check_sudo {
    if [[ $EUID -ne 0 ]]; then
        if ! sudo -v &>/dev/null; then
            echo "❌ Les droits sudo sont requis pour continuer."
            exit 1
        fi
    fi
}

# === Préparation ===
BASE_DIR="$(pwd)"
echo "🔧 Préparation de l'environnement..."

# === Vérifications ===
check_sudo

check_command docker || {
    sudo apt update
    sudo apt install -y docker.io
}

check_command python3 || {
    echo "❌ Python3 est requis mais non trouvé. Veuillez l'installer manuellement."
    exit 1
}

check_command python3-venv || {
    sudo apt install -y python3-venv
}

# === Docker ===
echo "🚀 Démarrage du service Docker..."
sudo service docker start

echo "🧑‍💻 Ajout de l'utilisateur '$USER' au groupe docker (si nécessaire)..."
sudo usermod -aG docker "$USER"
echo "ℹ️ Veuillez vous déconnecter/reconnecter ou exécuter 'newgrp docker' pour que les droits prennent effet."

# === Chargement de l'image Docker ===
if [[ -f task_docker_img/image-docker.tar ]]; then
    echo "📦 Chargement de l'image Docker..."
    docker image load -i task_docker_img/image-docker.tar
else
    echo "⚠️ Fichier task_docker_img/image-docker.tar introuvable. Ignoré."
fi

# === Environnement virtuel ===
echo "🐍 Création de l'environnement virtuel Python..."
cd "$BASE_DIR"
rm -rf venv
python3 -m venv venv
source venv/bin/activate

# === Environnement volontaire ===
mkdir -p .volunteer/tasks .volunteer/temp_data

# === Installation des paquets Python ===
echo "📦 Installation des paquets Python requis..."
pip install --upgrade pip
if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
else
    pip install django djangorestframework docker psutil redis requests PyJWT channels daphne
fi

echo "🔧 Application des migrations..."
python3 manage.py migrate

echo "🎉 Tout est installé avec succès."
