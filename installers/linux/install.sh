#!/bin/bash
#
# Script d'installation du service volontaire sur Linux
# Support: Ubuntu, Debian, CentOS, RHEL, Fedora
#

set -e

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   Installation du Service Volontaire - Computing Distribué    ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Vérifier les privilèges root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}✗ Ce script doit être exécuté avec les privilèges root (sudo)${NC}"
   exit 1
fi

echo -e "${GREEN}✓ Privilèges root détectés${NC}"

# Variables
INSTALL_DIR="/opt/volunteer-app"
SERVICE_NAME="volunteer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
USER="volunteer"
GROUP="volunteer"

# Détecter la distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    echo -e "${RED}✗ Impossible de détecter la distribution Linux${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Distribution détectée: $OS $VER${NC}"

# Créer l'utilisateur système si nécessaire
if ! id "$USER" &>/dev/null; then
    echo "Création de l'utilisateur système '$USER'..."
    useradd -r -s /bin/false -d $INSTALL_DIR $USER
    echo -e "${GREEN}✓ Utilisateur '$USER' créé${NC}"
else
    echo -e "${GREEN}✓ Utilisateur '$USER' existe déjà${NC}"
fi

# Créer le répertoire d'installation
echo "Création du répertoire d'installation..."
mkdir -p $INSTALL_DIR
echo -e "${GREEN}✓ Répertoire $INSTALL_DIR créé${NC}"

# Copier les fichiers de l'application
echo "Copie des fichiers de l'application..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
rsync -av --exclude='exp-env' --exclude='__pycache__' --exclude='*.pyc' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/"
echo -e "${GREEN}✓ Fichiers copiés${NC}"

# Installer Python 3 si nécessaire
echo "Vérification de Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "Installation de Python 3..."
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Fedora"* ]]; then
        yum install -y python3 python3-pip
    fi
    echo -e "${GREEN}✓ Python 3 installé${NC}"
else
    echo -e "${GREEN}✓ Python 3 détecté: $(python3 --version)${NC}"
fi

# Créer l'environnement virtuel
echo "Création de l'environnement virtuel..."
cd $INSTALL_DIR
python3 -m venv exp-env
echo -e "${GREEN}✓ Environnement virtuel créé${NC}"

# Installer les dépendances
echo "Installation des dépendances Python..."
$INSTALL_DIR/exp-env/bin/pip install --upgrade pip
$INSTALL_DIR/exp-env/bin/pip install -r $INSTALL_DIR/requirements.txt
echo -e "${GREEN}✓ Dépendances installées${NC}"

# Copier le fichier de service systemd
echo "Installation du service systemd..."
cp "$INSTALL_DIR/installers/linux/volunteer.service" "$SERVICE_FILE"

# Remplacer les chemins dans le fichier de service
sed -i "s|/opt/volunteer-app|$INSTALL_DIR|g" "$SERVICE_FILE"
sed -i "s|User=volunteer|User=$USER|g" "$SERVICE_FILE"
sed -i "s|Group=volunteer|Group=$GROUP|g" "$SERVICE_FILE"

echo -e "${GREEN}✓ Service systemd configuré${NC}"

# Ajuster les permissions
echo "Configuration des permissions..."
chown -R $USER:$GROUP $INSTALL_DIR
chmod +x $INSTALL_DIR/volunteer_daemon.py
echo -e "${GREEN}✓ Permissions configurées${NC}"

# Recharger systemd
echo "Rechargement de systemd..."
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd rechargé${NC}"

# Activer le service au démarrage
echo "Activation du service au démarrage..."
systemctl enable $SERVICE_NAME
echo -e "${GREEN}✓ Service activé${NC}"

# Démarrer le service
echo "Démarrage du service..."
systemctl start $SERVICE_NAME
echo -e "${GREEN}✓ Service démarré${NC}"

# Vérifier le statut
sleep 2
if systemctl is-active --quiet $SERVICE_NAME; then
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║             ✅ INSTALLATION RÉUSSIE                           ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Le service volontaire est maintenant installé et actif!"
    echo ""
    echo "Commandes utiles:"
    echo "  • Statut    : sudo systemctl status $SERVICE_NAME"
    echo "  • Arrêter   : sudo systemctl stop $SERVICE_NAME"
    echo "  • Démarrer  : sudo systemctl start $SERVICE_NAME"
    echo "  • Redémarrer: sudo systemctl restart $SERVICE_NAME"
    echo "  • Logs      : sudo journalctl -u $SERVICE_NAME -f"
    echo ""
else
    echo -e "${RED}✗ Le service n'a pas démarré correctement${NC}"
    echo "Vérifiez les logs: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
