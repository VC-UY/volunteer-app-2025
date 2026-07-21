#!/bin/bash
# Démarre le runtime d'exécution vc-uyr (compat, SANS Docker) puis le serveur volontaire.
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

# --- Runtime d'exécution vc-uyr (compat, sans Docker, sans root) ---
RUNTIME_HOST="${RUNTIME_HOST:-127.0.0.1}"
RUNTIME_PORT="${RUNTIME_PORT:-7070}"
RUNTIME_URL="${RUNTIME_URL:-http://${RUNTIME_HOST}:${RUNTIME_PORT}}"
RUNTIME_DATA="${VCUYR_DATA_DIR:-$(pwd)/.volunteer/runtime-compat}"
export RUNTIME_URL
mkdir -p "$RUNTIME_DATA" .volunteer/logs

if ! curl -sf --max-time 2 "$RUNTIME_URL/api/health" >/dev/null 2>&1; then
    echo "✅ Démarrage du runtime vc-uyr sur $RUNTIME_URL (sans Docker)..."
    nohup python runtime_compat_server.py \
        --host "$RUNTIME_HOST" --port "$RUNTIME_PORT" --data-dir "$RUNTIME_DATA" \
        >>.volunteer/logs/runtime-compat.log 2>&1 &
    echo "   runtime PID=$!"
    for _ in $(seq 1 20); do
        curl -sf --max-time 1 "$RUNTIME_URL/api/health" >/dev/null 2>&1 && break
        sleep 0.3
    done
fi
if curl -sf --max-time 2 "$RUNTIME_URL/api/health" >/dev/null 2>&1; then
    echo "✅ Runtime prêt ($RUNTIME_URL)."
else
    echo "⚠️  Runtime non joignable sur $RUNTIME_URL — voir .volunteer/logs/runtime-compat.log"
fi

VOLUNTEER_PORT="${VOLUNTEER_API_PORT:-8003}"

echo "✅ Lancement du serveur volontaire..."
echo "   Connexion coordinateur en arrière-plan (173.249.38.251:6380)..."
echo "   → http://localhost:${VOLUNTEER_PORT}"

exec venv/bin/daphne -b 0.0.0.0 -p "${VOLUNTEER_PORT}" backend.asgi:application
