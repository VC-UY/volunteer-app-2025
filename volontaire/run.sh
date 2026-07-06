#!/bin/bash

set -e

if [[ ! -f venv/bin/activate ]]; then
    echo "❌ Environnement virtuel introuvable. Relancez ./install-volontaire.sh"
    exit 1
fi

if [[ ! -f manage.py ]]; then
    echo "❌ Lancez ce script depuis le dossier volontaire."
    exit 1
fi

# Si Docker est installé mais inaccessible dans ce shell, relancer automatiquement
# sous le groupe docker pour éviter les PermissionError sur /var/run/docker.sock.
if command -v docker >/dev/null 2>&1 && [[ -z "${VCUY_DOCKER_GROUP_READY:-}" ]]; then
    if ! docker info >/dev/null 2>&1; then
        if id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
            echo "🔄 Relance sous le groupe docker pour activer l'accès Docker..."
            export VCUY_RUN_DIR="$(pwd)"
            exec sg docker -c "cd \"$VCUY_RUN_DIR\" && export VCUY_DOCKER_GROUP_READY=1 && ./run.sh"
        fi
    fi
fi

echo "✅ Activation de l'environnement virtuel..."
source venv/bin/activate

# Daphne est installé dans le venv par install.sh — pas dans le PATH système
if [[ ! -x venv/bin/daphne ]]; then
    echo "📦 Installation de daphne dans le venv..."
    pip install --quiet daphne channels
fi

mkdir -p .volunteer/tasks .volunteer/temp_data

echo "✅ Migrations Django..."
python manage.py migrate --noinput

echo "✅ Lancement du serveur volontaire..."
echo "   Connexion coordinateur en arrière-plan (173.249.38.251:6380)..."
VOLUNTEER_PORT="${VOLUNTEER_API_PORT:-8003}"
echo "   → http://localhost:${VOLUNTEER_PORT}"
exec venv/bin/daphne -b 0.0.0.0 -p "${VOLUNTEER_PORT}" backend.asgi:application
