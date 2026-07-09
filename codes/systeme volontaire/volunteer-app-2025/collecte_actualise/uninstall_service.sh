#!/bin/bash
# Script de désinstallation du service system-monitor
# À exécuter en tant que root

set -e

# Couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SERVICE_NAME="system-monitor"
SERVICE_DIR="/opt/system-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}Désinstallation du service System Monitor${NC}"
echo -e "${BLUE}===========================================${NC}"

# Vérifier si le script est exécuté en tant que root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Erreur: Ce script doit être exécuté en tant que root${NC}"
    echo "Utilisez: sudo $0"
    exit 1
fi

# Fonction pour afficher les messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Demander confirmation
echo -e "${YELLOW}Êtes-vous sûr de vouloir désinstaller complètement le service system-monitor ?${NC}"
echo -e "${YELLOW}Cette action supprimera tous les fichiers du service et les données collectées.${NC}"
read -p "Tapez 'oui' pour confirmer: " confirmation

if [ "$confirmation" != "oui" ]; then
    log_info "Désinstallation annulée."
    exit 0
fi

# Arrêter le service s'il est en cours d'exécution
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    log_info "Arrêt du service..."
    systemctl stop "${SERVICE_NAME}.service"
fi

# Désactiver le service
if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    log_info "Désactivation du service..."
    systemctl disable "${SERVICE_NAME}.service"
fi

# Supprimer le fichier de service
if [ -f "${SERVICE_FILE}" ]; then
    log_info "Suppression du fichier de service..."
    rm -f "${SERVICE_FILE}"
fi

# Recharger systemd
log_info "Rechargement de systemd..."
systemctl daemon-reload
systemctl reset-failed

# Supprimer le répertoire de service
if [ -d "${SERVICE_DIR}" ]; then
    log_info "Suppression du répertoire de service..."
    # Demander confirmation pour la suppression des données
    echo -e "${YELLOW}Voulez-vous également supprimer les données collectées ?${NC}"
    read -p "Tapez 'oui' pour supprimer les données: " delete_data
    
    if [ "$delete_data" = "oui" ]; then
        rm -rf "${SERVICE_DIR}"
        log_info "Répertoire de service et données supprimés."
    else
        # Supprimer seulement l'exécutable et garder les données
        rm -f "${SERVICE_DIR}/agent"
        rm -f "${SERVICE_DIR}/system_monitor.py"
        log_info "Exécutable supprimé, données conservées dans ${SERVICE_DIR}/data"
    fi
fi

echo
echo -e "${BLUE}===========================================${NC}"
echo -e "${GREEN}Désinstallation terminée avec succès!${NC}"
echo -e "${BLUE}===========================================${NC}"
echo
log_info "Le service system-monitor a été complètement désinstallé."
