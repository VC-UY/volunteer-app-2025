#!/bin/bash
# ==============================================================================
# start.sh — Démarrage propre du runtime vc-uyr
# À placer dans le même répertoire que le binaire vc-uyr et vc-uyr.toml
#
# Usage : sudo bash start.sh
#
# Ce script :
#   1. Vérifie que les fichiers nécessaires sont présents
#   2. Tue toutes les instances précédentes du runtime
#   3. Vérifie que le port 7070 est libéré
#   4. Lance le runtime avec les logs
# ==============================================================================

# Couleurs terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Répertoire du script (là où sont aussi vc-uyr et vc-uyr.toml)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_BIN="$SCRIPT_DIR/vc-uyr"
RUNTIME_CFG="$SCRIPT_DIR/vc-uyr.toml"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  vc-uyr — Script de démarrage propre${NC}"
echo -e "${BLUE}============================================================${NC}"

# ==============================================================================
# ÉTAPE 1 — Vérifier les fichiers nécessaires
# ==============================================================================
echo -e "\n${YELLOW}[1/4] Vérification des fichiers...${NC}"

if [ ! -f "$RUNTIME_BIN" ]; then
    echo -e "${RED}ERREUR : Binaire introuvable : $RUNTIME_BIN${NC}"
    echo -e "${RED}Placez le binaire vc-uyr dans le même répertoire que start.sh${NC}"
    exit 1
fi

if [ ! -x "$RUNTIME_BIN" ]; then
    echo -e "${YELLOW}Binaire non exécutable — correction...${NC}"
    chmod +x "$RUNTIME_BIN"
fi

if [ ! -f "$RUNTIME_CFG" ]; then
    echo -e "${RED}ERREUR : Configuration introuvable : $RUNTIME_CFG${NC}"
    echo -e "${RED}Placez vc-uyr.toml dans le même répertoire que start.sh${NC}"
    exit 1
fi

# Extraire le port depuis la config (défaut 7070)
PORT=$(grep -E "volunteer_server_port" "$RUNTIME_CFG" 2>/dev/null \
    | grep -oE '[0-9]+' | head -1)
PORT=${PORT:-7070}

echo -e "${GREEN}  ✓ Binaire   : $RUNTIME_BIN${NC}"
echo -e "${GREEN}  ✓ Config    : $RUNTIME_CFG${NC}"
echo -e "${GREEN}  ✓ Port HTTP : $PORT${NC}"

# ==============================================================================
# ÉTAPE 2 — Tuer les anciennes instances du runtime
# ==============================================================================
echo -e "\n${YELLOW}[2/4] Nettoyage des instances précédentes...${NC}"

INSTANCES=$(pgrep -f "vc-uyr" 2>/dev/null | wc -l)
if [ "$INSTANCES" -gt 0 ]; then
    echo -e "${YELLOW}  $INSTANCES instance(s) détectée(s) — arrêt en cours...${NC}"
    sudo pkill -9 -f "vc-uyr" 2>/dev/null
    sleep 2

    REMAINING=$(pgrep -f "vc-uyr" 2>/dev/null | wc -l)
    if [ "$REMAINING" -gt 0 ]; then
        echo -e "${YELLOW}  Instances résistantes — tentative par PID...${NC}"
        for pid in $(pgrep -f "vc-uyr" 2>/dev/null); do
            sudo kill -9 "$pid" 2>/dev/null
        done
        sleep 1
    fi

    FINAL=$(pgrep -f "vc-uyr" 2>/dev/null | wc -l)
    if [ "$FINAL" -gt 0 ]; then
        echo -e "${RED}ERREUR : Impossible de tuer toutes les instances.${NC}"
        echo -e "${RED}Instances restantes :${NC}"
        pgrep -fa "vc-uyr"
        exit 1
    fi
    echo -e "${GREEN}  ✓ Toutes les instances arrêtées${NC}"
else
    echo -e "${GREEN}  ✓ Aucune instance précédente${NC}"
fi

# ==============================================================================
# ÉTAPE 3 — Vérifier que le port est libre
# ==============================================================================
echo -e "\n${YELLOW}[3/4] Vérification du port $PORT...${NC}"

# Attendre que le port soit réellement libéré
MAX_WAIT=10
WAITED=0
while sudo fuser "$PORT/tcp" > /dev/null 2>&1; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        OCCUPANT=$(sudo fuser -v "$PORT/tcp" 2>&1)
        echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ERREUR : Port $PORT toujours occupé après ${MAX_WAIT}s   ║${NC}"
        echo -e "${RED}║                                                  ║${NC}"
        echo -e "${RED}║  Processus occupant le port :                    ║${NC}"
        echo -e "${RED}║  $OCCUPANT${NC}"
        echo -e "${RED}║                                                  ║${NC}"
        echo -e "${RED}║  Libérez manuellement avec :                     ║${NC}"
        echo -e "${RED}║    sudo fuser -k $PORT/tcp                        ║${NC}"
        echo -e "${RED}║  puis relancez : sudo bash start.sh              ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
        exit 1
    fi
    echo -e "${YELLOW}  Port $PORT encore occupé — attente ($WAITED/${MAX_WAIT}s)...${NC}"
    sudo fuser -k "$PORT/tcp" 2>/dev/null
    sleep 1
    WAITED=$((WAITED + 1))
done

echo -e "${GREEN}  ✓ Port $PORT libre${NC}"

# ==============================================================================
# ÉTAPE 4 — Démarrage du runtime
# ==============================================================================
echo -e "\n${YELLOW}[4/4] Démarrage du runtime vc-uyr...${NC}"
echo -e "${BLUE}------------------------------------------------------------${NC}"

# Créer le répertoire de logs si nécessaire
sudo mkdir -p /vc/logs 2>/dev/null
sudo chown "$USER:$USER" /vc/logs 2>/dev/null

# Lancement
# Lancer le runtime en avant-plan avec gestion propre de Ctrl+C
sudo env RUST_LOG=info "$RUNTIME_BIN" "$RUNTIME_CFG" &
RUNTIME_PID=$!

echo -e "${GREEN}  ✓ Runtime démarré (PID=$RUNTIME_PID)${NC}"
echo -e "${BLUE}  Ctrl+C pour arrêter proprement${NC}"
echo -e "${BLUE}------------------------------------------------------------${NC}"

# Intercepter Ctrl+C et les signaux d'arrêt
cleanup() {
    echo -e "\n${YELLOW}[STOP] Arrêt du runtime en cours...${NC}"

    # Tuer le runtime et ses enfants
    sudo kill -TERM "$RUNTIME_PID" 2>/dev/null
    sleep 2

    # Si encore actif, forcer
    if kill -0 "$RUNTIME_PID" 2>/dev/null; then
        sudo kill -9 "$RUNTIME_PID" 2>/dev/null
    fi

    # Nettoyer les processus orphelins et le port
    sudo pkill -9 -f "vc-uyr" 2>/dev/null
    sleep 1
    sudo fuser -k "$PORT/tcp" 2>/dev/null

    echo -e "${GREEN}[STOP] Runtime arrêté — port $PORT libéré${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Attendre que le runtime se termine
wait "$RUNTIME_PID"
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo -e "${RED}[STOP] Runtime terminé avec code $EXIT_CODE${NC}"
fi