#!/usr/bin/env bash
# Installe et démarre la stack volontaire en arrière-plan (systemd --user).
# - Pas de logs interminables dans le terminal
# - Survit à la fermeture du terminal
# - Relance automatique au reboot (linger)
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
LOG_DIR="$BASE/.volunteer/logs"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$LOG_DIR" "$UNIT_DIR" "$BASE/.volunteer/runtime-compat"

if [[ ! -x "$PY" ]]; then
  echo "❌ venv introuvable. Lancez d'abord ./install.sh"
  exit 1
fi

# Seed default prefs (24/7) so machines receive tasks without schedule setup
mkdir -p "$BASE/.volunteer"
(cd "$BASE" && "$PY" -c "from preferences_payload import ensure_default_preferences; ensure_default_preferences()") || true
if [[ ! -x "$DAPHNE" ]]; then
  "$PY" -m pip install -q daphne channels
fi

# Agent : utiliser le même Python du venv volontaire (numpy, psutil, requests)
AGENT_PY="$PY"
if [[ ! -f "$AGENT/main.py" ]]; then
  echo "❌ agent/main.py introuvable ($AGENT)"
  exit 1
fi

# Linger = démarrage au boot sans session graphique
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || true
fi

COORD_HOST="${COORDINATOR_HOST:-173.249.38.251}"
COORD_PORT="${COORDINATOR_PROXY_PORT:-6380}"
MGR_URL="${MANAGER_PUBLIC_URL:-https://manager-vc-uy.npe-techs.com}"
SITE_API="${VCUY_SITE_API:-https://vc-uy.npe-techs.com/api/agent}"
CACHE="${VCUY_DATASET_CACHE:-$HOME/.vcuy/datasets}"

cat >"$UNIT_DIR/vc-uy-runtime.service" <<EOF
[Unit]
Description=VC-UY volunteer runtime (vc-uyr-compat)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=VCUY_PYTHON=$PY
Environment=VCUY_DATASET_CACHE=$CACHE
Environment=PATH=$VENV/bin:/usr/bin:/bin
ExecStart=$PY $BASE/runtime_compat_server.py --host 127.0.0.1 --port $RUNTIME_PORT --data-dir $BASE/.volunteer/runtime-compat
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/runtime.log
StandardError=append:$LOG_DIR/runtime.log

[Install]
WantedBy=default.target
EOF

cat >"$UNIT_DIR/vc-uy-agent.service" <<EOF
[Unit]
Description=VC-UY research agent (ARX/GRU + sync)
After=network-online.target vc-uy-runtime.service
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
After=network-online.target vc-uy-runtime.service vc-uy-agent.service
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
Environment=PATH=$VENV/bin:/usr/bin:/bin
ExecStart=$DAPHNE -b 0.0.0.0 -p $PORT backend.asgi:application
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/volunteer.log
StandardError=append:$LOG_DIR/volunteer.log

[Install]
WantedBy=default.target
EOF

# Éviter le double service agent (ancien vc-agent.service)
systemctl --user disable --now vc-agent.service >/dev/null 2>&1 || true

systemctl --user daemon-reload
systemctl --user enable vc-uy-runtime.service vc-uy-agent.service vc-uy-volunteer.service
systemctl --user restart vc-uy-runtime.service
sleep 1
systemctl --user restart vc-uy-agent.service
sleep 1
systemctl --user restart vc-uy-volunteer.service

# Attente courte santé (sans spammer le terminal)
ok_rt=0 ok_ag=0 ok_ui=0
for _ in $(seq 1 30); do
  curl -sf --max-time 1 "http://127.0.0.1:${RUNTIME_PORT}/api/health" >/dev/null 2>&1 && ok_rt=1
  curl -sf --max-time 1 "http://127.0.0.1:${AGENT_PORT}/health" >/dev/null 2>&1 && ok_ag=1
  curl -sf --max-time 1 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && ok_ui=1
  if [[ "$ok_rt" -eq 1 && "$ok_ag" -eq 1 && "$ok_ui" -eq 1 ]]; then
    break
  fi
  sleep 1
done

echo
echo "═══════════════════════════════════════════════"
echo "  Volontaire VC-UY — démarré en arrière-plan"
echo "═══════════════════════════════════════════════"
echo "  Interface : http://localhost:${PORT}"
echo "  Runtime   : $([ "$ok_rt" -eq 1 ] && echo OK || echo démarrage…)"
echo "  Agent     : $([ "$ok_ag" -eq 1 ] && echo OK || echo démarrage…)"
echo "  UI        : $([ "$ok_ui" -eq 1 ] && echo OK || echo démarrage…)"
echo
echo "  Vous pouvez fermer ce terminal."
echo "  Au redémarrage de la machine, les services se relancent seuls."
echo
echo "  Logs (si besoin) : $LOG_DIR/"
echo "  Arrêt           : systemctl --user stop vc-uy-volunteer vc-uy-agent vc-uy-runtime"
echo "  Statut          : systemctl --user status vc-uy-volunteer"
echo "═══════════════════════════════════════════════"
