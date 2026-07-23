#!/usr/bin/env bash
# Installe et démarre la stack volontaire (systemd --user + runtime Ashley système).
# Runtime UNIQUE : binaire isolant vc-uyr (Ashley). Pas de compat Python.
# Le runtime tourne en service système root (namespaces). Prérequis :
#   sudo bash ./install_runtime_system.sh
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$BASE/.." && pwd)"
AGENT="$REPO/agent"
VENV="$BASE/venv"
PY="$VENV/bin/python"
DAPHNE="$VENV/bin/daphne"
PORT="${VOLUNTEER_API_PORT:-8003}"
RUNTIME_PORT="${RUNTIME_PORT:-7070}"
AGENT_PORT="${VC_AGENT_API_PORT:-7071}"
AUTH_SHIM_PORT="${AUTH_SHIM_PORT:-18000}"
LOG_DIR="$BASE/.volunteer/logs"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
RUNTIME_HOME="${VCUY_RUNTIME_HOME:-$HOME/.vcuy/runtime}"
RUNTIME_BIN="${RUNTIME_BIN:-$RUNTIME_HOME/bin/vc-uyr}"
RUNTIME_CFG="${RUNTIME_CONFIG:-$RUNTIME_HOME/config/vc-uyr.toml}"

mkdir -p "$LOG_DIR" "$UNIT_DIR"

if [[ ! -x "$PY" ]]; then
  echo "❌ venv introuvable. Lancez d'abord ./install.sh"
  exit 1
fi

mkdir -p "$BASE/.volunteer"
(cd "$BASE" && "$PY" -c "from preferences_payload import ensure_default_preferences; ensure_default_preferences()") || true
if [[ ! -x "$DAPHNE" ]]; then
  "$PY" -m pip install -q daphne channels
fi

chmod +x "$BASE/install_runtime.sh" "$BASE/install_runtime_system.sh" 2>/dev/null || true
"$BASE/install_runtime.sh"

if [[ ! -x "$RUNTIME_BIN" ]]; then
  if [[ -x "$HOME/.vcuy/runtime/bin/vc-uyr" ]]; then
    RUNTIME_HOME="$HOME/.vcuy/runtime"
  elif [[ -x "$REPO/runtime/dist/bin/vc-uyr" ]]; then
    RUNTIME_HOME="$REPO/runtime/dist"
  fi
  RUNTIME_BIN="$RUNTIME_HOME/bin/vc-uyr"
  RUNTIME_CFG="$RUNTIME_HOME/config/vc-uyr.toml"
fi
export VCUY_RUNTIME_HOME="$RUNTIME_HOME"

if [[ ! -x "$RUNTIME_BIN" || ! -f "$RUNTIME_CFG" ]]; then
  echo "❌ Runtime Ashley (vc-uyr) introuvable."
  echo "   Placez runtime/vc-uyr-runtime.tar.xz puis ./install_runtime.sh"
  exit 1
fi

AGENT_PY="$PY"
if [[ ! -f "$AGENT/main.py" ]]; then
  echo "❌ agent/main.py introuvable ($AGENT)"
  exit 1
fi

if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || true
fi

COORD_HOST="${COORDINATOR_HOST:-173.249.38.251}"
COORD_PORT="${COORDINATOR_PROXY_PORT:-6380}"
MGR_URL="${MANAGER_PUBLIC_URL:-https://manager-vc-uy.npe-techs.com}"
SITE_API="${VCUY_SITE_API:-https://vc-uy.npe-techs.com/api/agent}"
CACHE="${VCUY_DATASET_CACHE:-$HOME/.vcuy/datasets}"

# Couper compat + ancien service user (crash EPERM sans root)
pkill -f 'runtime_compat_server.py' 2>/dev/null || true
systemctl --user disable --now vc-uy-runtime.service >/dev/null 2>&1 || true
# Ne pas tuer un vc-uyr root déjà OK
if ! systemctl is-active --quiet vc-uy-runtime.service 2>/dev/null; then
  fuser -k "${RUNTIME_PORT}/tcp" 2>/dev/null || true
  pkill -x vc-uyr 2>/dev/null || true
fi
sleep 1

if ! systemctl is-active --quiet vc-uy-runtime.service 2>/dev/null; then
  echo
  echo "❌ Runtime Ashley doit tourner en root (namespaces / unshare)."
  echo "   Lance UNE fois dans ton terminal :"
  echo
  echo "     sudo bash $BASE/install_runtime_system.sh"
  echo
  echo "   Puis :"
  echo "     VCUY_RUNTIME_HOME=$RUNTIME_HOME $BASE/install_daemon.sh"
  echo
  exit 1
fi

cat >"$UNIT_DIR/vc-uy-runtime-auth.service" <<EOF
[Unit]
Description=VC-UY runtime auth shim (vc-uyr boot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=PATH=$VENV/bin:/usr/bin:/bin
ExecStart=$PY $BASE/runtime_auth_shim.py --host 127.0.0.1 --port $AUTH_SHIM_PORT
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/runtime-auth-shim.log
StandardError=append:$LOG_DIR/runtime-auth-shim.log

[Install]
WantedBy=default.target
EOF

cat >"$UNIT_DIR/vc-uy-agent.service" <<EOF
[Unit]
Description=VC-UY research agent (ARX/GRU + sync)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$AGENT
Environment=VC_MANAGED_BY_SYSTEMD=1
Environment=VC_AGENT_API_HOST=127.0.0.1
Environment=VC_AGENT_API_PORT=$AGENT_PORT
Environment=VCUY_SITE_API=$SITE_API
Environment=VC_AGENT_SYNC_SECONDS=20
Environment=VCUY_DATASET_CACHE=$CACHE
Environment=PATH=$VENV/bin:/usr/bin:/bin
ExecStart=$AGENT_PY $AGENT/main.py --foreground
Restart=always
RestartSec=8
StandardOutput=append:$LOG_DIR/agent.log
StandardError=append:$LOG_DIR/agent.log

[Install]
WantedBy=default.target
EOF

cat >"$UNIT_DIR/vc-uy-volunteer.service" <<EOF
[Unit]
Description=VC-UY volunteer app (Daphne)
After=network-online.target vc-uy-agent.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=COORDINATOR_HOST=$COORD_HOST
Environment=COORDINATOR_PROXY_PORT=$COORD_PORT
Environment=MANAGER_PUBLIC_URL=$MGR_URL
Environment=RUNTIME_URL=http://127.0.0.1:$RUNTIME_PORT
Environment=VC_AGENT_API_URL=http://127.0.0.1:$AGENT_PORT
Environment=VCUY_PYTHON=$PY
Environment=VCUY_DATASET_CACHE=$CACHE
Environment=VCUY_RUNTIME_HOME=$RUNTIME_HOME
Environment=PATH=$VENV/bin:/usr/bin:/bin
ExecStart=$DAPHNE -b 0.0.0.0 -p $PORT backend.asgi:application
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/volunteer.log
StandardError=append:$LOG_DIR/volunteer.log

[Install]
WantedBy=default.target
EOF

systemctl --user disable --now vc-agent.service >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable vc-uy-runtime-auth.service vc-uy-agent.service vc-uy-volunteer.service
systemctl --user restart vc-uy-runtime-auth.service
sleep 1
systemctl --user restart vc-uy-agent.service
sleep 1
systemctl --user restart vc-uy-volunteer.service

ok_rt=0
for _ in $(seq 1 20); do
  if curl -sf --max-time 1 "http://127.0.0.1:${RUNTIME_PORT}/api/health" >/dev/null 2>&1; then
    ok_rt=1
    break
  fi
  sleep 1
done

HEALTH_BODY="$(curl -sf --max-time 2 "http://127.0.0.1:${RUNTIME_PORT}/api/health" || true)"
if [[ "$ok_rt" -ne 1 ]]; then
  echo "❌ Runtime Ashley ne répond pas sur :$RUNTIME_PORT"
  echo "   sudo systemctl status vc-uy-runtime"
  tail -40 "$LOG_DIR/runtime.log" 2>/dev/null || true
  exit 1
fi
if echo "$HEALTH_BODY" | grep -q 'vc-uyr-compat'; then
  echo "❌ Compat détecté — interdit. Seul Ashley est autorisé."
  exit 1
fi

ok_ag=0 ok_ui=0
for _ in $(seq 1 30); do
  curl -sf --max-time 1 "http://127.0.0.1:${AGENT_PORT}/health" >/dev/null 2>&1 && ok_ag=1
  curl -sf --max-time 1 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && ok_ui=1
  if [[ "$ok_ag" -eq 1 && "$ok_ui" -eq 1 ]]; then
    break
  fi
  sleep 1
done

echo
echo "═══════════════════════════════════════════════"
echo "  Volontaire VC-UY — runtime Ashley uniquement"
echo "═══════════════════════════════════════════════"
echo "  Interface : http://localhost:${PORT}"
echo "  Runtime   : vc-uyr (Ashley/root) OK"
echo "  Health    : $HEALTH_BODY"
echo "  Agent     : $([ "$ok_ag" -eq 1 ] && echo OK || echo démarrage…)"
echo "  UI        : $([ "$ok_ui" -eq 1 ] && echo OK || echo démarrage…)"
echo "  Bin       : $RUNTIME_BIN"
echo
echo "  Logs : $LOG_DIR/"
echo "═══════════════════════════════════════════════"
