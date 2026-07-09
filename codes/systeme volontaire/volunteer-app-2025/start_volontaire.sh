#!/bin/bash
# Démarre UNIQUEMENT l'application volontaire (Django + Daphne = backend et
# "frontend" dans le même process ASGI). Ne touche pas au runtime vc-uyr.
#
# A utiliser dans un terminal séparé de celui où tourne le runtime vc-uyr,
# pour isoler facilement les logs de chacun en cas de problème :
#   - Terminal 1 (runtime)        : sudo ./vc-uyr vc-uyr.toml   (votre commande)
#   - Terminal 2 (app volontaire) : ./start_volontaire.sh   (ce script)
#
# Ce script attend que le runtime soit joignable sur RUNTIME_HOST:RUNTIME_PORT
# avant de démarrer Daphne (par défaut : attente indéfinie, avec un message
# de statut toutes les ~10s ; Ctrl+C pour annuler). Réglable via variables
# d'environnement, voir ci-dessous.
#
# Usage : sudo bash start_volontaire.sh
#
# Prérequis: l'installation classique a déjà été faite (venv/ créé et
# dépendances installées, cf. README_RUNTIME.md / volontaire-run.sh).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# Manuellement : cd /chemin/vers/volunteer-app-2025

VOLUNTEER_PORT="${VOLUNTEER_PORT:-8003}"
RUNTIME_HOST="${RUNTIME_HOST:-localhost}"
RUNTIME_PORT="${RUNTIME_PORT:-7070}"
# Timeout en secondes avant d'abandonner l'attente du runtime (0 = attendre
# indéfiniment, comportement par défaut demandé pour ce workflow).
RUNTIME_WAIT_TIMEOUT="${RUNTIME_WAIT_TIMEOUT:-0}"

# Charger les variables de .env si présent (RUNTIME_URL, COORDINATOR_HOST, ...)
# Manuellement : set -a && source .env && set +a
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "ERREUR : environnement virtuel introuvable. Lancez d'abord ./volontaire-run.sh (installation complète)."
    exit 1
fi

# === Attente du runtime vc-uyr (démarré séparément, dans un autre terminal) ===

# Vérifie si le port du runtime répond (bash uniquement, pas besoin de nc).
# Manuellement, pour tester vous-même en une commande :
#   (exec 3<>/dev/tcp/localhost/7070) 2>/dev/null && echo "runtime OK" || echo "runtime injoignable"
runtime_is_up() {
    (exec 3<>"/dev/tcp/${RUNTIME_HOST}/${RUNTIME_PORT}") 2>/dev/null
    local status=$?
    exec 3<&- 2>/dev/null
    exec 3>&- 2>/dev/null
    return $status
}

echo "En attente du runtime vc-uyr sur ${RUNTIME_HOST}:${RUNTIME_PORT}..."
echo "(démarrez-le dans un autre terminal si ce n'est pas déjà fait, ex: sudo ./vc-uyr vc-uyr.toml)"

elapsed=0
until runtime_is_up; do
    if [ "$RUNTIME_WAIT_TIMEOUT" -gt 0 ] && [ "$elapsed" -ge "$RUNTIME_WAIT_TIMEOUT" ]; then
        echo "AVERTISSEMENT : toujours injoignable après ${RUNTIME_WAIT_TIMEOUT}s, on continue quand même."
        echo "L'exécution de tâches échouera tant que le runtime n'est pas démarré."
        break
    fi
    if [ $((elapsed % 10)) -eq 0 ]; then
        echo "  ... toujours en attente (${elapsed}s écoulées)"
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if runtime_is_up; then
    echo "Runtime vc-uyr détecté sur ${RUNTIME_HOST}:${RUNTIME_PORT}."
fi

# === Application volontaire ===

# Manuellement : source venv/bin/activate
# shellcheck disable=SC1091
source "$SCRIPT_DIR/venv/bin/activate"

echo "Application des migrations Django..."
# Manuellement : python manage.py migrate
python manage.py migrate

echo "Lancement du serveur ASGI (Daphne) sur le port $VOLUNTEER_PORT..."
# Manuellement : daphne backend.asgi:application -p 8003 -b 0.0.0.0
daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 0.0.0.0
