#!/bin/bash

# Script d'installation et de lancement automatique pour l'application Volontaire
# Ce script installe toutes les dépendances et lance l'application automatiquement

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
COORDINATOR_IP="173.249.38.251"  # IP du serveur coordinator déployé
COORDINATOR_PORT="6380"
VOLUNTEER_PORT="8003"

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}    Application Volontaire - Installation Automatique${NC}"
echo -e "${GREEN}======================================================${NC}\n"

# Obtenir le répertoire du script (qui est maintenant dans volunteer-app-2025/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLUNTEER_DIR="$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/venv"

# Fonction pour afficher les erreurs
error_exit() {
    echo -e "\n${RED}ERREUR: $1${NC}" >&2
    exit 1
}

# Fonction pour vérifier si une commande existe
command_exists() {
    command -v "$1" &> /dev/null
}

# Fonction pour détecter le système d'exploitation
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/debian_version ]; then
            echo "debian"
        elif [ -f /etc/redhat-release ]; then
            echo "redhat"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

OS_TYPE=$(detect_os)
echo -e "${BLUE}Système d'exploitation détecté: $OS_TYPE${NC}\n"

# Vérifier si le script est exécuté avec sudo si nécessaire
if [ "$EUID" -ne 0 ] && [ "$OS_TYPE" != "macos" ]; then
    echo -e "${YELLOW}Ce script nécessite des privilèges administrateur pour installer les dépendances.${NC}"
    echo -e "${YELLOW}Relancement avec sudo...${NC}\n"
    exec sudo bash "$0" "$@"
fi

# Fonction d'installation pour Debian/Ubuntu
install_debian() {
    echo -e "${YELLOW}[1/6] Mise à jour des paquets système...${NC}"
    apt-get update

    echo -e "${YELLOW}[2/6] Installation de Python et pip...${NC}"
    apt-get install -y python3 python3-pip python3-venv python3-dev build-essential

    echo -e "${YELLOW}[3/6] Installation de Docker...${NC}"
    if ! command_exists docker; then
        apt-get install -y apt-transport-https ca-certificates curl software-properties-common
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
        add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io
        systemctl enable docker
        systemctl start docker

        # Ajouter l'utilisateur au groupe docker
        if [ -n "$SUDO_USER" ]; then
            usermod -aG docker "$SUDO_USER"
        fi
    else
        echo -e "${GREEN}Docker est déjà installé${NC}"
    fi

    echo -e "${YELLOW}[4/6] Installation de Redis...${NC}"
    if ! command_exists redis-server; then
        apt-get install -y redis-server
        systemctl enable redis-server
        systemctl start redis-server
    else
        echo -e "${GREEN}Redis est déjà installé${NC}"
    fi

    echo -e "${YELLOW}[5/6] Installation de Git et autres outils...${NC}"
    apt-get install -y git curl wget tmux

    echo -e "${YELLOW}[6/6] Installation de Node.js et npm...${NC}"
    if ! command_exists node; then
        curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
        apt-get install -y nodejs
    else
        echo -e "${GREEN}Node.js est déjà installé${NC}"
    fi
}

# Fonction d'installation pour RedHat/CentOS/Fedora
install_redhat() {
    echo -e "${YELLOW}[1/6] Installation de Python et pip...${NC}"
    yum install -y python3 python3-pip python3-devel gcc

    echo -e "${YELLOW}[2/6] Installation de Docker...${NC}"
    if ! command_exists docker; then
        yum install -y yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        yum install -y docker-ce docker-ce-cli containerd.io
        systemctl enable docker
        systemctl start docker

        if [ -n "$SUDO_USER" ]; then
            usermod -aG docker "$SUDO_USER"
        fi
    else
        echo -e "${GREEN}Docker est déjà installé${NC}"
    fi

    echo -e "${YELLOW}[3/6] Installation de Redis...${NC}"
    if ! command_exists redis-server; then
        yum install -y redis
        systemctl enable redis
        systemctl start redis
    else
        echo -e "${GREEN}Redis est déjà installé${NC}"
    fi

    echo -e "${YELLOW}[4/6] Installation de Git et autres outils...${NC}"
    yum install -y git curl wget tmux

    echo -e "${YELLOW}[5/6] Installation de Node.js et npm...${NC}"
    if ! command_exists node; then
        curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -
        yum install -y nodejs
    else
        echo -e "${GREEN}Node.js est déjà installé${NC}"
    fi
}

# Fonction d'installation pour macOS
install_macos() {
    if ! command_exists brew; then
        error_exit "Homebrew n'est pas installé. Installez-le depuis https://brew.sh"
    fi

    echo -e "${YELLOW}[1/5] Installation de Python...${NC}"
    brew install python3

    echo -e "${YELLOW}[2/5] Installation de Docker...${NC}"
    if ! command_exists docker; then
        brew install --cask docker
        echo -e "${YELLOW}Veuillez démarrer Docker Desktop manuellement${NC}"
    else
        echo -e "${GREEN}Docker est déjà installé${NC}"
    fi

    echo -e "${YELLOW}[3/5] Installation de Redis...${NC}"
    brew install redis
    brew services start redis

    echo -e "${YELLOW}[4/5] Installation de Git et autres outils...${NC}"
    brew install git tmux

    echo -e "${YELLOW}[5/5] Installation de Node.js...${NC}"
    brew install node
}

# Installer les dépendances système selon l'OS
echo -e "\n${GREEN}=== Installation des dépendances système ===${NC}\n"

case $OS_TYPE in
    debian)
        install_debian
        ;;
    redhat)
        install_redhat
        ;;
    macos)
        install_macos
        ;;
    *)
        error_exit "Système d'exploitation non supporté: $OS_TYPE"
        ;;
esac

echo -e "\n${GREEN}=== Installation des dépendances Python ===${NC}\n"

# Créer l'environnement virtuel si nécessaire
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Création de l'environnement virtuel...${NC}"
    python3 -m venv "$VENV_DIR"
else
    echo -e "${GREEN}L'environnement virtuel existe déjà${NC}"
fi

# Activer l'environnement virtuel
source "$VENV_DIR/bin/activate"

# Installer les dépendances Python du volontaire
echo -e "${YELLOW}Installation des dépendances Python...${NC}"
cd "$VOLUNTEER_DIR"
pip install --upgrade pip setuptools wheel
pip install --upgrade -r requirements.txt

echo -e "\n${GREEN}=== Configuration de l'application ===${NC}\n"

# Mettre à jour le fichier de configuration avec l'IP du coordinator
echo -e "${YELLOW}Configuration de la connexion au coordinator...${NC}"

# Créer un fichier .env s'il n'existe pas
ENV_FILE="$VOLUNTEER_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Création du fichier .env...${NC}"
    cat > "$ENV_FILE" << EOF
COORDINATOR_HOST=$COORDINATOR_IP
COORDINATOR_PROXY_PORT=$COORDINATOR_PORT
EOF
    echo -e "${GREEN}Fichier .env créé${NC}"
else
    echo -e "${GREEN}Fichier .env existe déjà${NC}"
fi

# Exporter les variables d'environnement
export COORDINATOR_HOST="$COORDINATOR_IP"
export COORDINATOR_PROXY_PORT="$COORDINATOR_PORT"

echo -e "${GREEN}Variables d'environnement configurées:${NC}"
echo -e "  COORDINATOR_HOST=$COORDINATOR_HOST"
echo -e "  COORDINATOR_PROXY_PORT=$COORDINATOR_PROXY_PORT"

# Créer le répertoire data si nécessaire
mkdir -p "$VOLUNTEER_DIR/backend/data"

# Appliquer les migrations
echo -e "${YELLOW}Application des migrations de base de données...${NC}"
cd "$VOLUNTEER_DIR"
python manage.py migrate

echo -e "\n${GREEN}=== Démarrage de l'application Volontaire ===${NC}\n"

echo -e "${BLUE}L'application va démarrer sur http://localhost:$VOLUNTEER_PORT${NC}"
echo -e "${BLUE}Elle se connectera au coordinator sur http://$COORDINATOR_IP${NC}\n"

echo -e "${YELLOW}Appuyez sur Ctrl+C pour arrêter l'application${NC}\n"

# Lancer l'application
cd "$VOLUNTEER_DIR"
daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 0.0.0.0
