#!/bin/bash
# Démarre la stack volontaire.
# Par défaut : arrière-plan via systemd (fermer le terminal = OK, reboot = relance).
# Debug : VCUY_FOREGROUND=1 ./run.sh  → logs dans le terminal (ancien comportement).
set -e

if [[ ! -f venv/bin/activate ]]; then
    echo "❌ Environnement virtuel introuvable. Relancez ./install.sh"
    exit 1
fi

if [[ ! -f manage.py ]]; then
    echo "❌ Lancez ce script depuis le dossier volontaire."
    exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate

if [[ ! -x venv/bin/daphne ]]; then
    echo "📦 Installation de daphne dans le venv..."
    pip install --quiet daphne channels
fi

export VCUY_PYTHON="$(pwd)/venv/bin/python"
export PATH="$(dirname "$VCUY_PYTHON"):$PATH"
export VCUY_DATASET_CACHE="${VCUY_DATASET_CACHE:-$HOME/.vcuy/datasets}"

mkdir -p .volunteer/tasks .volunteer/temp_data .volunteer/logs

echo "✅ Migrations Django..."
python manage.py migrate --noinput >/dev/null

# --- Mode normal : daemon systemd, terminal libre ---
if [[ "${VCUY_FOREGROUND:-0}" != "1" ]]; then
    chmod +x ./install_daemon.sh
    exec ./install_daemon.sh
fi

# --- Mode debug foreground (VCUY_FOREGROUND=1) ---
RUNTIME_HOST="${RUNTIME_HOST:-127.0.0.1}"
RUNTIME_PORT="${RUNTIME_PORT:-7070}"
RUNTIME_URL="${RUNTIME_URL:-http://${RUNTIME_HOST}:${RUNTIME_PORT}}"
RUNTIME_DATA="${VCUYR_DATA_DIR:-$(pwd)/.volunteer/runtime-compat}"
export RUNTIME_URL
mkdir -p "$RUNTIME_DATA"

if ! curl -sf --max-time 2 "$RUNTIME_URL/api/health" >/dev/null 2>&1; then
    echo "✅ Démarrage runtime (foreground debug)..."
    nohup env VCUY_PYTHON="$VCUY_PYTHON" VCUY_DATASET_CACHE="$VCUY_DATASET_CACHE" PATH="$PATH" \
        python runtime_compat_server.py \
        --host "$RUNTIME_HOST" --port "$RUNTIME_PORT" --data-dir "$RUNTIME_DATA" \
        >>.volunteer/logs/runtime-compat.log 2>&1 &
    for _ in $(seq 1 20); do
        curl -sf --max-time 1 "$RUNTIME_URL/api/health" >/dev/null 2>&1 && break
        sleep 0.3
    done
fi

VOLUNTEER_PORT="${VOLUNTEER_API_PORT:-8003}"
echo "✅ Daphne foreground → http://localhost:${VOLUNTEER_PORT}"
exec env VCUY_PYTHON="$VCUY_PYTHON" VCUY_DATASET_CACHE="$VCUY_DATASET_CACHE" \
    venv/bin/daphne -b 0.0.0.0 -p "${VOLUNTEER_PORT}" backend.asgi:application
