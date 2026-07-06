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

# --- Docker : installation fiable + accès utilisateur ---
docker_accessible() {
    docker info &>/dev/null 2>&1
}

docker_cmd() {
    if docker_accessible; then
        docker "$@"
    elif command -v sg &>/dev/null && sg docker -c "docker $*" &>/dev/null; then
        sg docker -c "docker $*"
    elif sudo docker info &>/dev/null 2>&1; then
        sudo docker "$@"
    else
        return 1
    fi
}

install_docker_engine() {
    echo "📦 Installation de Docker..."
    sudo apt-get update -qq
    sudo apt-get install -y ca-certificates curl gnupg lsb-release

    # Script officiel Docker (fonctionne sur Ubuntu/Debian récents où docker.io échoue)
    if curl -fsSL https://get.docker.com | sudo sh; then
        echo "✅ Docker installé (get.docker.com)."
        return 0
    fi

    echo "⚠️  get.docker.com a échoué, tentative via dépôt Docker CE..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
    sudo chmod a+r /etc/apt/keyrings/docker.gpg 2>/dev/null || true
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME:-$UBUNTU_CODENAME}") stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -qq
    if sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
        echo "✅ Docker CE installé."
        return 0
    fi

    echo "⚠️  Dépôt Docker CE indisponible, tentative docker.io..."
    sudo apt-get install -y docker.io
    echo "✅ Docker installé (docker.io)."
}

setup_docker_service_and_access() {
    sudo systemctl enable docker 2>/dev/null || true
    sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true

    if [[ -S /var/run/docker.sock ]]; then
        sudo chown root:docker /var/run/docker.sock 2>/dev/null || true
        sudo chmod 660 /var/run/docker.sock 2>/dev/null || true
    fi

    if [[ $EUID -ne 0 ]] && [[ -n "$USER" ]]; then
        sudo usermod -aG docker "$USER" 2>/dev/null || true
    fi

    # sg fait partie du paquet login sur Debian/Ubuntu
    if ! command -v sg &>/dev/null; then
        sudo apt-get install -y login 2>/dev/null || true
    fi
}

if ! command -v docker &>/dev/null; then
    install_docker_engine
fi
setup_docker_service_and_access

if docker_cmd info &>/dev/null; then
    echo "✅ Docker prêt et accessible."
else
    echo "⚠️  Docker installé ; l'accès sera activé automatiquement au lancement."
fi

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
