#!/bin/bash
# ============================================================================
# Script de lancement de plusieurs instances de volontaires
# Usage: ./launch-volunteers.sh [nombre_d_instances] [port_de_depart]
# Exemple: ./launch-volunteers.sh 3 8003
#   Lance 3 volontaires sur les ports 8003, 8004, 8005
# ============================================================================

set -e

# Paramètres par défaut
NUM_INSTANCES=${1:-1}
START_PORT=${2:-8003}

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Répertoire du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Vérifier que l'environnement virtuel existe
if [ ! -d "venv" ]; then
    echo -e "${RED}Erreur: L'environnement virtuel 'venv' n'existe pas.${NC}"
    echo "Créez-le avec: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activer l'environnement virtuel
source venv/bin/activate

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Lancement de $NUM_INSTANCES instance(s) de volontaire${NC}"
echo -e "${BLUE}  Ports: $START_PORT - $((START_PORT + NUM_INSTANCES - 1))${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Fonction pour lancer une instance
launch_instance() {
    local port=$1
    local instance_id=$2

    echo -e "${YELLOW}[Instance $instance_id] Démarrage sur le port $port...${NC}"

    # Définir les variables d'environnement
    export VOLUNTEER_PORT=$port
    export VOLUNTEER_INSTANCE_ID=$instance_id

    # Créer le répertoire de données si nécessaire
    local data_dir="data_$instance_id"
    mkdir -p "$data_dir"

    # Appliquer les migrations si nécessaire
    echo -e "${BLUE}[Instance $instance_id] Application des migrations...${NC}"
    python manage.py migrate --run-syncdb 2>/dev/null || true

    # Lancer Daphne en arrière-plan
    echo -e "${GREEN}[Instance $instance_id] Lancement de Daphne sur le port $port...${NC}"
    VOLUNTEER_PORT=$port VOLUNTEER_INSTANCE_ID=$instance_id \
        daphne backend.asgi:application -p $port -b 0.0.0.0 &

    # Sauvegarder le PID
    echo $! >> /tmp/volunteer_pids_$$.txt

    echo -e "${GREEN}[Instance $instance_id] Volontaire démarré (PID: $!)${NC}"
    echo ""
}

# Nettoyer les anciens PIDs si nécessaire
rm -f /tmp/volunteer_pids_$$.txt

# Lancer les instances
for i in $(seq 1 $NUM_INSTANCES); do
    port=$((START_PORT + i - 1))
    instance_id=$port
    launch_instance $port $instance_id

    # Petite pause entre les lancements
    sleep 2
done

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Tous les volontaires sont démarrés!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${BLUE}Ports utilisés:${NC}"
for i in $(seq 1 $NUM_INSTANCES); do
    port=$((START_PORT + i - 1))
    echo -e "  - Volontaire $i: http://localhost:$port"
done
echo ""
echo -e "${YELLOW}Pour arrêter tous les volontaires:${NC}"
echo "  ./stop-volunteers.sh"
echo ""
echo -e "${YELLOW}Ou manuellement:${NC}"
echo "  kill \$(cat /tmp/volunteer_pids_$$.txt)"

# Attendre que l'utilisateur arrête
echo ""
echo -e "${BLUE}Appuyez sur Ctrl+C pour arrêter tous les volontaires...${NC}"
trap "echo -e '\n${RED}Arrêt des volontaires...${NC}'; kill \$(cat /tmp/volunteer_pids_$$.txt 2>/dev/null) 2>/dev/null; rm -f /tmp/volunteer_pids_$$.txt; exit 0" INT TERM

# Garder le script en vie
wait
