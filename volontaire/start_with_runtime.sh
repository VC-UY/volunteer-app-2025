#!/bin/bash
# Démarre UNIQUEMENT le runtime isolant vc-uyr (Ashley), puis agent + Daphne.
# Pas de Docker, pas de runtime_compat.

set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VCUY_ROOT="$(cd "$APP_DIR/../../.." && pwd)"
AGENT_DIR="$(cd "$APP_DIR/../agent" && pwd)"
REPO="$(cd "$APP_DIR/.." && pwd)"
if [[ -n "${VCUY_RUNTIME_HOME:-}" ]]; then
  RUNTIME_HOME="$VCUY_RUNTIME_HOME"
elif [[ -x "$HOME/.vcuy/runtime/bin/vc-uyr" ]]; then
  RUNTIME_HOME="$HOME/.vcuy/runtime"
else
  RUNTIME_HOME="$REPO/runtime/dist"
fi
RUNTIME_BIN="${RUNTIME_BIN:-$RUNTIME_HOME/bin/vc-uyr}"
RUNTIME_CONFIG="${RUNTIME_CONFIG:-$RUNTIME_HOME/config/vc-uyr.toml}"
VOLUNTEER_PORT="${VOLUNTEER_PORT:-8003}"
AUTH_SHIM_PORT="${AUTH_SHIM_PORT:-18000}"
export RUNTIME_URL="${RUNTIME_URL:-http://127.0.0.1:7070}"
export VC_AGENT_API_URL="${VC_AGENT_API_URL:-http://127.0.0.1:7071}"
export VCUY_SITE_API="${VCUY_SITE_API:-https://vc-uy.npe-techs.com/api/agent}"

cd "$APP_DIR"
if [ -f .env ]; then set -a; # shellcheck disable=SC1091
  source .env; set +a; fi

PIDDIR="${PIDDIR:-$VCUY_ROOT/.vcuy/pids}"
LOGDIR="${LOGDIR:-$VCUY_ROOT/.vcuy/logs}"
mkdir -p "$PIDDIR" "$LOGDIR"

chmod +x "$APP_DIR/install_runtime.sh"
VCUY_RUNTIME_HOME="$RUNTIME_HOME" "$APP_DIR/install_runtime.sh"

if [ ! -x "$RUNTIME_BIN" ] || [ ! -f "$RUNTIME_CONFIG" ]; then
  echo "ERREUR: runtime Ashley manquant ($RUNTIME_BIN)"
  exit 1
fi

cleanup() {
  for f in vc-uyr.pid runtime-auth-shim.pid vc-agent.pid; do
    if [ -f "$PIDDIR/$f" ]; then
      kill "$(cat "$PIDDIR/$f")" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

fuser -k 7070/tcp 2>/dev/null || true
pkill -x vc-uyr 2>/dev/null || true
pkill -f 'runtime_compat_server.py' 2>/dev/null || true
sleep 1

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
echo "Runtime Ashley vc-uyr PID=$(cat "$PIDDIR/vc-uyr.pid")"

sleep 2
if ! curl -sf "$RUNTIME_URL/api/health" >/dev/null; then
  echo "ERREUR: vc-uyr non joignable sur $RUNTIME_URL"
  tail -40 "$LOGDIR/vc-uyr.log" 2>/dev/null || true
  exit 1
fi
HEALTH="$(curl -sf "$RUNTIME_URL/api/health" || true)"
if echo "$HEALTH" | grep -q 'vc-uyr-compat'; then
  echo "ERREUR: compat détecté — interdit"
  exit 1
fi
echo "Runtime Ashley OK: $HEALTH"

start_agent() {
  if curl -sf "${VC_AGENT_API_URL}/health" >/dev/null 2>&1; then
    echo "Agent déjà actif sur $VC_AGENT_API_URL"
    return 0
  fi
  if [ ! -d "$AGENT_DIR" ]; then
    echo "ATTENTION: dossier agent introuvable ($AGENT_DIR)"
    return 0
  fi
  if [ ! -d "$AGENT_DIR/.venv" ]; then
    python3 -m venv "$AGENT_DIR/.venv"
    # shellcheck disable=SC1091
    source "$AGENT_DIR/.venv/bin/activate"
    pip install -q -U pip
    pip install -q -r "$AGENT_DIR/requirements.txt"
    deactivate
  fi
  fuser -k 7071/tcp 2>/dev/null || true
  (
    cd "$AGENT_DIR"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    export VCUY_SITE_API VC_AGENT_API_HOST=127.0.0.1 VC_AGENT_API_PORT=7071
    if [ -f "$APP_DIR/.volunteer_id" ]; then
      export VCUY_VOLUNTEER_ID="$(tr -d '[:space:]' < "$APP_DIR/.volunteer_id")"
    fi
    exec python main.py --foreground
  ) >>"$LOGDIR/vc-agent.log" 2>&1 &
  echo $! > "$PIDDIR/vc-agent.pid"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "${VC_AGENT_API_URL}/health" >/dev/null 2>&1; then
      echo "Agent OK PID=$(cat "$PIDDIR/vc-agent.pid")"
      return 0
    fi
    sleep 2
  done
  echo "ATTENTION: agent non joignable — voir $LOGDIR/vc-agent.log"
}
start_agent

if [ ! -d venv ]; then echo "ERREUR: venv manquant"; exit 1; fi
# shellcheck disable=SC1091
source venv/bin/activate
pwd -P
python manage.py migrate --noinput
exec daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 127.0.0.1
