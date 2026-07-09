#!/bin/bash
# Script de vérification du service system-monitor

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
echo -e "${BLUE}Vérification du service System Monitor${NC}"
echo -e "${BLUE}===========================================${NC}"

# Fonction pour afficher les messages
log_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Vérifications
echo -e "${BLUE}1. Vérification des fichiers...${NC}"
if [ -f "${SERVICE_FILE}" ]; then
    log_info "Fichier de service trouvé: ${SERVICE_FILE}"
else
    log_error "Fichier de service manquant: ${SERVICE_FILE}"
fi

if [ -d "${SERVICE_DIR}" ]; then
    log_info "Répertoire de service trouvé: ${SERVICE_DIR}"
else
    log_error "Répertoire de service manquant: ${SERVICE_DIR}"
fi

if [ -f "${SERVICE_DIR}/agent" ]; then
    log_info "Exécutable trouvé: ${SERVICE_DIR}/agent"
    if [ -x "${SERVICE_DIR}/agent" ]; then
        log_info "Exécutable a les permissions d'exécution"
    else
        log_error "Exécutable n'a pas les permissions d'exécution"
    fi
else
    log_error "Exécutable manquant: ${SERVICE_DIR}/agent"
fi

if [ -d "${SERVICE_DIR}/data" ]; then
    log_info "Répertoire de données trouvé: ${SERVICE_DIR}/data"
else
    log_error "Répertoire de données manquant: ${SERVICE_DIR}/data"
fi

echo
echo -e "${BLUE}2. Vérification du statut du service...${NC}"
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    log_info "Service actif et en cours d'exécution"
else
    log_error "Service non actif"
fi

if systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
    log_info "Service activé pour le démarrage automatique"
else
    log_error "Service non activé pour le démarrage automatique"
fi

echo
echo -e "${BLUE}3. Informations détaillées du service...${NC}"
echo -e "${YELLOW}Statut détaillé:${NC}"
systemctl status "${SERVICE_NAME}.service" --no-pager -l

echo
echo -e "${BLUE}4. Derniers logs du service...${NC}"
echo -e "${YELLOW}5 dernières entrées de log:${NC}"
journalctl -u "${SERVICE_NAME}.service" -n 5 --no-pager

echo
echo -e "${BLUE}5. Vérification des fichiers de données...${NC}"
data_files=$(find "${SERVICE_DIR}/data" -name "*.json" 2>/dev/null | wc -l)
if [ "$data_files" -gt 0 ]; then
    log_info "Nombre de fichiers de données: $data_files"
    echo -e "${YELLOW}Derniers fichiers créés:${NC}"
    ls -lt "${SERVICE_DIR}/data"/*.json 2>/dev/null | head -3 || echo "Aucun fichier JSON trouvé"
else
    log_warning "Aucun fichier de données trouvé (normal si le service vient d'être démarré)"
fi

echo
echo -e "${BLUE}6. Test de connectivité réseau...${NC}"
# Lire la configuration depuis le script pour obtenir l'adresse du serveur
if [ -f "${SERVICE_DIR}/system_monitor.py" ]; then
    SERVER_HOST=$(grep "SERVER_HOST = " "${SERVICE_DIR}/system_monitor.py" | head -1 | cut -d"'" -f2)
    SERVER_PORT=$(grep "SERVER_PORT = " "${SERVICE_DIR}/system_monitor.py" | head -1 | awk '{print $3}')
    
    if [ -n "$SERVER_HOST" ] && [ -n "$SERVER_PORT" ]; then
        echo -e "${YELLOW}Test de connectivité vers ${SERVER_HOST}:${SERVER_PORT}...${NC}"
        if timeout 3 bash -c "echo >/dev/tcp/${SERVER_HOST}/${SERVER_PORT}" 2>/dev/null; then
            log_info "Connexion au serveur réussie"
        else
            log_warning "Impossible de se connecter au serveur (normal si le serveur n'est pas démarré)"
        fi
    fi
fi

echo
echo -e "${BLUE}===========================================${NC}"
echo -e "${GREEN}Vérification terminée${NC}"
echo -e "${BLUE}===========================================${NC}"
echo
echo -e "${YELLOW}Commandes utiles:${NC}"
echo "Voir les logs en temps réel:    journalctl -u ${SERVICE_NAME} -f"
echo "Redémarrer le service:          sudo systemctl restart ${SERVICE_NAME}"
echo "Arrêter le service:             sudo systemctl stop ${SERVICE_NAME}"
echo "Démarrer le service:            sudo systemctl start ${SERVICE_NAME}"
