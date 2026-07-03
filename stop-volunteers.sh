#!/bin/bash
# ============================================================================
# Script d'arrêt de toutes les instances de volontaires
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${RED}Arrêt de toutes les instances de volontaires...${NC}"

# Arrêter tous les processus Daphne liés au volontaire
pkill -f "daphne backend.asgi:application" 2>/dev/null && \
    echo -e "${GREEN}Tous les volontaires ont été arrêtés.${NC}" || \
    echo -e "${GREEN}Aucun volontaire en cours d'exécution.${NC}"

# Nettoyer les fichiers de PID temporaires
rm -f /tmp/volunteer_pids_*.txt 2>/dev/null

echo -e "${GREEN}Nettoyage terminé.${NC}"
