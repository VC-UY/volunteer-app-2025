#!/bin/bash
# Démarre le runtime vc-uyr puis l'application volontaire (Daphne).
# Usage (depuis volontaire/) : bash ../scripts/start_with_runtime.sh
# ou : bash start_with_runtime.sh si ce fichier est dans volontaire/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Si lancé depuis volontaire/, remonter pour trouver .vcuy ; sinon utiliser VCUY_ROOT
if [ -d "$SCRIPT_DIR/backend" ] && [ -f "$SCRIPT_DIR/manage.py" ]; then
  APP_DIR="$SCRIPT_DIR"
  ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"  # VL/volunteer-app-2025 -> VC-UY? adjust
  # Layout: VC-UY/VL/volunteer-app-2025/volontaire
  ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
else
  APP_DIR="$SCRIPT_DIR/volontaire"
  ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

# Prefer workspace .vcuy/runtime
RUNTIME_HOME="${RUNTIME_HOME:-$ROOT_DIR/.vcuy/runtime}"
if [ ! -x "$RUNTIME_HOME/bin/vc-uyr" ]; then
  RUNTIME_HOME="/home/npe-tech/Projets/VC-UY/.vcuy/runtime"
fi

RUNTIME_BIN="${RUNTIME_BIN:-$RUNTIME_HOME/bin/vc-uyr}"
RUNTIME_CONFIG="${RUNTIME_CONFIG:-$RUNTIME_HOME/config/vc-uyr.toml}"
VOLUNTEER_PORT="${VOLUNTEER_PORT:-8003}"
export RUNTIME_URL="${RUNTIME_URL:-http://localhost:7070}"

cd "$APP_DIR"

if [ -f "$APP_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env"
  set +a
fi

pkill -x vc-uyr 2>/dev/null || true
fuser -k 7070/tcp 2>/dev/null || true
sleep 1

if [ -x "$RUNTIME_BIN" ]; then
  RUST_LOG="${RUST_LOG:-info}" "$RUNTIME_BIN" "$RUNTIME_CONFIG" &
  echo "Runtime vc-uyr démarré (PID=$!) config=$RUNTIME_CONFIG"
  sleep 2
else
  echo "AVERTISSEMENT: binaire vc-uyr introuvable ($RUNTIME_BIN)"
fi

if [ ! -d "$APP_DIR/venv" ]; then
  echo "ERREUR: venv introuvable dans $APP_DIR"
  exit 1
fi

# shellcheck disable=SC1091
source "$APP_DIR/venv/bin/activate"
python manage.py migrate --noinput
exec daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 0.0.0.0
