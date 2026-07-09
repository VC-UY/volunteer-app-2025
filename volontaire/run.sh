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

docker_accessible() {
    docker info &>/dev/null 2>&1
}

# Relancer tout le script sous le groupe docker si Docker est installé mais inaccessible
if command -v docker &>/dev/null && [[ -z "${VCUY_DOCKER_GROUP_READY:-}" ]]; then
    if ! docker_accessible; then
        if command -v sg &>/dev/null; then
            echo "🔄 Activation automatique de l'accès Docker (groupe docker)..."
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

VOLUNTEER_PORT="${VOLUNTEER_API_PORT:-8003}"
DAPHNE_ARGS=(-b 0.0.0.0 -p "${VOLUNTEER_PORT}" backend.asgi:application)

echo "✅ Lancement du serveur volontaire..."
echo "   Connexion coordinateur en arrière-plan (173.249.38.251:6380)..."
echo "   → http://localhost:${VOLUNTEER_PORT}"

# Vérifier que Docker est joignable avant de lancer daphne (les tâches en ont besoin)
if command -v docker &>/dev/null; then
    if docker_accessible; then
        echo "✅ Docker accessible."
    elif command -v sg &>/dev/null && sg docker -c "docker info" &>/dev/null; then
        echo "✅ Docker accessible via le groupe docker."
        echo "🔄 Lancement du serveur avec accès Docker..."
        RUN_DIR="$(pwd)"
        exec sg docker -c "cd \"$RUN_DIR\" && source venv/bin/activate && exec venv/bin/daphne -b 0.0.0.0 -p \"${VOLUNTEER_PORT}\" backend.asgi:application"
    else
        echo "⚠️  Docker installé mais inaccessible — vérifiez que le service tourne."
        echo "    Relancez : ./install-volontaire.sh"
    fi
fi

exec venv/bin/daphne "${DAPHNE_ARGS[@]}"
