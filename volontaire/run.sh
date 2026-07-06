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
