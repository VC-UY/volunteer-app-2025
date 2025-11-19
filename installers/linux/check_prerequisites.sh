#!/bin/bash
#
# Script de vérification pré-installation pour le service volontaire
# Vérifie que tous les prérequis sont satisfaits
#

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║      Vérification Pré-Installation - Service Volontaire       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

ERRORS=0
WARNINGS=0

# Fonction de test
check_command() {
    local cmd=$1
    local name=$2
    local install_hint=$3
    
    if command -v $cmd &> /dev/null; then
        local version=$($cmd --version 2>&1 | head -n1)
        echo -e "${GREEN}✓${NC} $name: $version"
        return 0
    else
        echo -e "${RED}✗${NC} $name: Non installé"
        if [ ! -z "$install_hint" ]; then
            echo -e "  ${YELLOW}→${NC} $install_hint"
        fi
        ((ERRORS++))
        return 1
    fi
}

# Fonction de test de port
check_port() {
    local host=$1
    local port=$2
    local name=$3
    
    if timeout 3 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $name: Accessible ($host:$port)"
        return 0
    else
        echo -e "${RED}✗${NC} $name: Non accessible ($host:$port)"
        ((ERRORS++))
        return 1
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Vérification des Dépendances Système"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_command "python3" "Python 3" "sudo apt install python3 python3-pip python3-venv"
check_command "pip3" "pip (gestionnaire de paquets Python)" "sudo apt install python3-pip"

# Vérifier la version de Python
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 8 ]; then
        echo -e "  ${GREEN}→${NC} Python $PY_VERSION >= 3.8 (OK)"
    else
        echo -e "  ${RED}→${NC} Python $PY_VERSION < 3.8 (Trop ancien!)"
        ((ERRORS++))
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Vérification des Fichiers de Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Vérifier requirements.txt
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo -e "${GREEN}✓${NC} requirements.txt: Présent"
else
    echo -e "${RED}✗${NC} requirements.txt: Manquant"
    ((ERRORS++))
fi

# Vérifier redis_communication/config.py
if [ -f "$SCRIPT_DIR/redis_communication/config.py" ]; then
    echo -e "${GREEN}✓${NC} redis_communication/config.py: Présent"
    
    # Vérifier la configuration Redis
    REDIS_HOST=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); from redis_communication.config import REDIS_PROXY_HOST; print(REDIS_PROXY_HOST)" 2>/dev/null)
    REDIS_PORT=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); from redis_communication.config import REDIS_PROXY_PORT; print(REDIS_PROXY_PORT)" 2>/dev/null)
    
    if [ ! -z "$REDIS_HOST" ] && [ ! -z "$REDIS_PORT" ]; then
        echo -e "  ${BLUE}→${NC} Redis Proxy configuré: $REDIS_HOST:$REDIS_PORT"
        
        # Vérifier si c'est localhost (warning)
        if [ "$REDIS_HOST" = "localhost" ] || [ "$REDIS_HOST" = "127.0.0.1" ]; then
            echo -e "  ${YELLOW}⚠${NC} ATTENTION: Redis configuré en localhost"
            echo -e "  ${YELLOW}→${NC} Pensez à le changer pour pointer vers le Coordinateur!"
            ((WARNINGS++))
        fi
    else
        echo -e "  ${RED}✗${NC} Impossible de lire la configuration Redis"
        ((ERRORS++))
    fi
else
    echo -e "${RED}✗${NC} redis_communication/config.py: Manquant"
    ((ERRORS++))
fi

# Vérifier volunteer_daemon.py
if [ -f "$SCRIPT_DIR/volunteer_daemon.py" ]; then
    echo -e "${GREEN}✓${NC} volunteer_daemon.py: Présent"
else
    echo -e "${RED}✗${NC} volunteer_daemon.py: Manquant"
    ((ERRORS++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Test de Connectivité au Coordinateur"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -z "$REDIS_HOST" ] && [ ! -z "$REDIS_PORT" ] && [ "$REDIS_HOST" != "localhost" ] && [ "$REDIS_HOST" != "127.0.0.1" ]; then
    # Test de ping
    if ping -c 1 -W 3 "$REDIS_HOST" &> /dev/null; then
        echo -e "${GREEN}✓${NC} Ping: $REDIS_HOST est accessible"
    else
        echo -e "${YELLOW}⚠${NC} Ping: $REDIS_HOST ne répond pas (peut être normal si ICMP bloqué)"
        ((WARNINGS++))
    fi
    
    # Test du port Redis
    check_port "$REDIS_HOST" "$REDIS_PORT" "Redis Proxy"
    
    # Test du port File Proxy
    check_port "$REDIS_HOST" "8410" "File Proxy"
else
    echo -e "${YELLOW}⚠${NC} Tests de connectivité ignorés (localhost configuré)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Vérification des Privilèges"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ $EUID -eq 0 ]]; then
    echo -e "${GREEN}✓${NC} Privilèges root: Présents"
else
    echo -e "${YELLOW}⚠${NC} Privilèges root: Absents"
    echo -e "  ${YELLOW}→${NC} L'installation nécessitera 'sudo'"
    ((WARNINGS++))
fi

# Vérifier systemd
if command -v systemctl &> /dev/null; then
    echo -e "${GREEN}✓${NC} systemd: Disponible"
else
    echo -e "${RED}✗${NC} systemd: Non disponible"
    echo -e "  ${RED}→${NC} Ce système n'utilise pas systemd"
    ((ERRORS++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Vérification de l'Espace Disque"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

AVAILABLE_SPACE=$(df /opt 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
AVAILABLE_GB=$((AVAILABLE_SPACE / 1024 / 1024))

if [ $AVAILABLE_GB -ge 5 ]; then
    echo -e "${GREEN}✓${NC} Espace disque: ${AVAILABLE_GB} GB disponibles (OK)"
elif [ $AVAILABLE_GB -ge 2 ]; then
    echo -e "${YELLOW}⚠${NC} Espace disque: ${AVAILABLE_GB} GB disponibles (limite)"
    ((WARNINGS++))
else
    echo -e "${RED}✗${NC} Espace disque: ${AVAILABLE_GB} GB disponibles (insuffisant)"
    ((ERRORS++))
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                      RÉSUMÉ                                    ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Tous les prérequis sont satisfaits!${NC}"
    echo ""
    echo "Vous pouvez procéder à l'installation:"
    echo "  sudo installers/linux/install.sh"
    echo ""
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS avertissement(s) détecté(s)${NC}"
    echo ""
    echo "L'installation devrait fonctionner, mais vérifiez les avertissements."
    echo ""
    exit 0
else
    echo -e "${RED}✗ $ERRORS erreur(s) et $WARNINGS avertissement(s) détecté(s)${NC}"
    echo ""
    echo "Corrigez les erreurs avant de procéder à l'installation."
    echo ""
    exit 1
fi
