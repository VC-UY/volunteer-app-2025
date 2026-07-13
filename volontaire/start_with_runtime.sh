#!/bin/bash
# Démarre le runtime d'exécution (compat local par défaut) puis Daphne.
# Pas de Docker. Usage: bash start_with_runtime.sh
#
# USE_RUST_BINARY=1 force le binaire vc-uyr (nécessite souvent sudo + auth shim).

set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VCUY_ROOT="$(cd "$APP_DIR/../../.." && pwd)"
RUNTIME_HOME="${RUNTIME_HOME:-$VCUY_ROOT/.vcuy/runtime}"
RUNTIME_BIN="${RUNTIME_BIN:-$RUNTIME_HOME/bin/vc-uyr}"
RUNTIME_CONFIG="${RUNTIME_CONFIG:-$RUNTIME_HOME/config/vc-uyr.toml}"
VOLUNTEER_PORT="${VOLUNTEER_PORT:-8003}"
AUTH_SHIM_PORT="${AUTH_SHIM_PORT:-18000}"
USE_RUST_BINARY="${USE_RUST_BINARY:-0}"
export RUNTIME_URL="${RUNTIME_URL:-http://127.0.0.1:7070}"

cd "$APP_DIR"
if [ -f .env ]; then set -a; # shellcheck disable=SC1091
  source .env; set +a; fi

PIDDIR="${PIDDIR:-$VCUY_ROOT/.vcuy/pids}"
LOGDIR="${LOGDIR:-$VCUY_ROOT/.vcuy/logs}"
DATADIR="${VCUYR_DATA_DIR:-$VCUY_ROOT/.vcuy/runtime-compat}"
mkdir -p "$PIDDIR" "$LOGDIR" "$DATADIR"

cleanup() {
  for f in vc-uyr.pid runtime-compat.pid runtime-auth-shim.pid; do
    if [ -f "$PIDDIR/$f" ]; then
      kill "$(cat "$PIDDIR/$f")" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

fuser -k 7070/tcp 2>/dev/null || true
pkill -x vc-uyr 2>/dev/null || true
sleep 1

if [ "$USE_RUST_BINARY" = "1" ] && [ -x "$RUNTIME_BIN" ]; then
  fuser -k "${AUTH_SHIM_PORT}/tcp" 2>/dev/null || true
  python3 "$APP_DIR/runtime_auth_shim.py" --port "$AUTH_SHIM_PORT" \
    >>"$LOGDIR/runtime-auth-shim.log" 2>&1 &
  echo $! > "$PIDDIR/runtime-auth-shim.pid"
  sleep 1
  if command -v sudo >/dev/null && sudo -n true 2>/dev/null; then
    sudo -n env RUST_LOG="${RUST_LOG:-info}" "$RUNTIME_BIN" "$RUNTIME_CONFIG" \
      >>"$LOGDIR/vc-uyr.log" 2>&1 &
  else
    env RUST_LOG="${RUST_LOG:-info}" "$RUNTIME_BIN" "$RUNTIME_CONFIG" \
      >>"$LOGDIR/vc-uyr.log" 2>&1 &
  fi
  echo $! > "$PIDDIR/vc-uyr.pid"
  echo "Runtime binaire PID=$(cat "$PIDDIR/vc-uyr.pid")"
else
  python3 "$APP_DIR/runtime_compat_server.py" --host 127.0.0.1 --port 7070 --data-dir "$DATADIR" \
    >>"$LOGDIR/vc-uyr-compat.log" 2>&1 &
  echo $! > "$PIDDIR/runtime-compat.pid"
  echo "Runtime compat PID=$(cat "$PIDDIR/runtime-compat.pid") (sans Docker, sans root)"
fi

sleep 2
if ! curl -sf "$RUNTIME_URL/api/health" >/dev/null; then
  echo "ERREUR: runtime non joignable sur $RUNTIME_URL"
  tail -40 "$LOGDIR/vc-uyr-compat.log" 2>/dev/null || tail -40 "$LOGDIR/vc-uyr.log" 2>/dev/null || true
  exit 1
fi
echo "Runtime OK"

if [ ! -d venv ]; then echo "ERREUR: venv manquant"; exit 1; fi
# shellcheck disable=SC1091
source venv/bin/activate
python manage.py migrate --noinput
exec daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 0.0.0.0
