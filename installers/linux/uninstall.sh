#!/bin/bash
#
# Script de désinstallation du service volontaire sur Linux
#

set -e

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Désinstallation du Service Volontaire - Computing Distribué  ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Vérifier les privilèges root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}✗ Ce script doit être exécuté avec les privilèges root (sudo)${NC}"
   exit 1
fi

# Variables
INSTALL_DIR="/opt/volunteer-app"
SERVICE_NAME="volunteer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
USER="volunteer"

# Confirmation
echo -e "${YELLOW}⚠ Cette action va supprimer complètement le service volontaire.${NC}"
read -p "Êtes-vous sûr de vouloir continuer? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Désinstallation annulée."
    exit 0
fi

# Arrêter le service
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "Arrêt du service..."
    systemctl stop $SERVICE_NAME
    echo -e "${GREEN}✓ Service arrêté${NC}"
fi

# Désactiver le service
if systemctl is-enabled --quiet $SERVICE_NAME 2>/dev/null; then
    echo "Désactivation du service..."
    systemctl disable $SERVICE_NAME
    echo -e "${GREEN}✓ Service désactivé${NC}"
fi

# Supprimer le fichier de service
if [ -f "$SERVICE_FILE" ]; then
    echo "Suppression du fichier de service..."
    rm -f "$SERVICE_FILE"
    echo -e "${GREEN}✓ Fichier de service supprimé${NC}"
fi

# Recharger systemd
echo "Rechargement de systemd..."
systemctl daemon-reload
systemctl reset-failed
echo -e "${GREEN}✓ Systemd rechargé${NC}"

# Supprimer le répertoire d'installation
if [ -d "$INSTALL_DIR" ]; then
    echo "Suppression du répertoire d'installation..."
    read -p "Voulez-vous aussi supprimer la base de données et les logs? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        echo -e "${GREEN}✓ Répertoire d'installation supprimé (avec données)${NC}"
    else
        # Garder db.sqlite3 et logs
        find "$INSTALL_DIR" -mindepth 1 ! -name "db.sqlite3" ! -path "*/logs/*" -delete
        echo -e "${GREEN}✓ Répertoire d'installation nettoyé (données préservées)${NC}"
    fi
fi

# Supprimer l'utilisateur système
if id "$USER" &>/dev/null; then
    read -p "Voulez-vous supprimer l'utilisateur système '$USER'? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        userdel $USER 2>/dev/null || true
        echo -e "${GREEN}✓ Utilisateur '$USER' supprimé${NC}"
    fi
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          ✅ DÉSINSTALLATION TERMINÉE                          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
