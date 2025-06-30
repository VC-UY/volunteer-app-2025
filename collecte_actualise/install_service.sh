#!/bin/bash
# Script d'installation du service system-monitor
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
EXECUTABLE_NAME="agent"

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}Installation du service System Monitor${NC}"
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

# Vérifier la présence de l'exécutable
if [ ! -f "./${EXECUTABLE_NAME}" ]; then
    log_error "L'exécutable '${EXECUTABLE_NAME}' n'a pas été trouvé dans le répertoire courant"
    echo "Assurez-vous que l'exécutable soit présent avant d'exécuter ce script"
    exit 1
fi

# Créer le répertoire de service
log_info "Création du répertoire de service..."
mkdir -p "${SERVICE_DIR}"
mkdir -p "${SERVICE_DIR}/data"

# Copier l'exécutable
log_info "Copie de l'exécutable..."
cp "./${EXECUTABLE_NAME}" "${SERVICE_DIR}/"
chmod +x "${SERVICE_DIR}/${EXECUTABLE_NAME}"

# Vérifier que l'exécutable est bien exécutable
log_info "Vérification de l'exécutable..."
if [ ! -x "${SERVICE_DIR}/${EXECUTABLE_NAME}" ]; then
    log_error "L'exécutable n'a pas les bonnes permissions"
    exit 1
fi


# Copier le script Python original si présent (pour référence)
if [ -f "./paste.txt" ] || [ -f "./system_monitor.py" ]; then
    log_info "Copie du script Python original..."
    if [ -f "./paste.txt" ]; then
        cp "./paste.txt" "${SERVICE_DIR}/system_monitor.py"
    elif [ -f "./system_monitor.py" ]; then
        cp "./system_monitor.py" "${SERVICE_DIR}/"
    fi
fi

# Créer le fichier de service systemd
log_info "Création du fichier de service systemd..."
cat > "${SERVICE_FILE}" << 'EOF'
[Unit]
Description=Agent de surveillance système - Collecte de données
Documentation=Agent de surveillance pour collecter et envoyer les données système
After=network.target network-online.target
Wants=network-online.target
StartLimitInterval=300
StartLimitBurst=5

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/system-monitor
ExecStart=/opt/system-monitor/agent
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
Restart=always
RestartSec=10
TimeoutStartSec=60
TimeoutStopSec=30

# Variables d'environnement
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Sécurité et isolation (ajustée pour permettre l'exécution)
NoNewPrivileges=false
PrivateTmp=false
ProtectHome=false
ProtectSystem=false
ReadWritePaths=/opt/system-monitor


# Supprimer toute sortie (stdout + stderr)
StandardOutput=null
StandardError=null

# Redémarrage automatique en cas d'échec
RestartPreventExitStatus=0

[Install]
WantedBy=multi-user.target
EOF

# Définir les permissions appropriées
log_info "Configuration des permissions..."
chown -R root:root "${SERVICE_DIR}"
chmod 755 "${SERVICE_DIR}"
chmod 755 "${SERVICE_DIR}/data"
chmod +x "${SERVICE_DIR}/${EXECUTABLE_NAME}"

# Recharger systemd
log_info "Rechargement de systemd..."
systemctl daemon-reload

# Arrêter le service s'il existe déjà
if systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    log_info "Arrêt du service existant..."
    systemctl stop "${SERVICE_NAME}.service"
fi

# Activer le service
log_info "Activation du service..."
systemctl enable "${SERVICE_NAME}.service"

# Démarrer le service
log_info "Démarrage du service..."
if systemctl start "${SERVICE_NAME}.service"; then
    log_info "Service démarré avec succès!"
else
    log_error "Échec du démarrage du service"
    log_info "Vérification des logs d'erreur..."
    journalctl -u "${SERVICE_NAME}.service" --no-pager -n 10
    exit 1
fi

# Vérifier le statut avec plus de détails
sleep 3
log_info "Vérification du statut du service..."
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    log_info "Service actif et fonctionnel!"
    systemctl status "${SERVICE_NAME}.service" --no-pager -l
else
    log_error "Le service ne semble pas être actif"
    log_info "Affichage des logs récents:"
    journalctl -u "${SERVICE_NAME}.service" --no-pager -n 20
    exit 1
fi

echo
echo -e "${BLUE}===========================================${NC}"
echo -e "${GREEN}Installation terminée avec succès!${NC}"
echo -e "${BLUE}===========================================${NC}"
echo
echo "Commandes utiles pour gérer le service:"
echo -e "${YELLOW}Statut du service:${NC}        systemctl status ${SERVICE_NAME}"
echo -e "${YELLOW}Arrêter le service:${NC}       systemctl stop ${SERVICE_NAME}"
echo -e "${YELLOW}Démarrer le service:${NC}      systemctl start ${SERVICE_NAME}"
echo -e "${YELLOW}Redémarrer le service:${NC}    systemctl restart ${SERVICE_NAME}"
echo -e "${YELLOW}Voir les logs:${NC}            journalctl -u ${SERVICE_NAME} -f"
echo -e "${YELLOW}Voir les logs récents:${NC}    journalctl -u ${SERVICE_NAME} -n 50"
echo -e "${YELLOW}Désactiver le service:${NC}    systemctl disable ${SERVICE_NAME}"
echo
echo -e "${GREEN}Le service est maintenant configuré pour se lancer automatiquement au démarrage.${NC}"
echo
echo "Pour diagnostiquer les problèmes :"
echo -e "${YELLOW}Tester l'exécutable:${NC}      ${SERVICE_DIR}/${EXECUTABLE_NAME}"
echo -e "${YELLOW}Vérifier les permissions:${NC} ls -la ${SERVICE_DIR}/"
