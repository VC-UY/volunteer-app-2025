#!/usr/bin/env bash
# Installe le runtime Ashley (vc-uyr) en service système root.
# Requis : namespaces (unshare) — sans root le binaire crash (EPERM).
# Usage : sudo bash install_runtime_system.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "❌ Relancez avec sudo : sudo bash $0"
  exit 1
fi

REAL_USER="${SUDO_USER:-${USER}}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
BASE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$BASE/.." && pwd)"

# Préférer l'install utilisateur déjà faite, sinon dist repo
if [[ -x "$REAL_HOME/.vcuy/runtime/bin/vc-uyr" ]]; then
  RUNTIME_HOME="$REAL_HOME/.vcuy/runtime"
elif [[ -x "$REPO/runtime/dist/bin/vc-uyr" ]]; then
  RUNTIME_HOME="$REPO/runtime/dist"
else
  echo "❌ Binaire absent. En tant que $REAL_USER : cd $BASE && ./install_runtime.sh"
  exit 1
fi

BIN="$RUNTIME_HOME/bin/vc-uyr"
CFG="$RUNTIME_HOME/config/vc-uyr.toml"
LOG_DIR="$BASE/.volunteer/logs"
AUTH_SHIM="$BASE/runtime_auth_shim.py"
PY="$(command -v python3)"
# Prefer volunteer venv python if present
if [[ -x "$BASE/venv/bin/python" ]]; then
  PY="$BASE/venv/bin/python"
fi

mkdir -p "$LOG_DIR"
chown -R "$REAL_USER:$REAL_USER" "$RUNTIME_HOME" "$LOG_DIR" 2>/dev/null || true

# Auth shim reste en user-space
cat >"/home/$REAL_USER/.config/systemd/user/vc-uy-runtime-auth.service" <<EOF
[Unit]
Description=VC-UY runtime auth shim (vc-uyr boot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
ExecStart=$PY $AUTH_SHIM --host 127.0.0.1 --port 18000
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/runtime-auth-shim.log
StandardError=append:$LOG_DIR/runtime-auth-shim.log

[Install]
WantedBy=default.target
EOF
chown "$REAL_USER:$REAL_USER" "/home/$REAL_USER/.config/systemd/user/vc-uy-runtime-auth.service"

# Runtime Ashley = service système root (namespaces)
cat >/etc/systemd/system/vc-uy-runtime.service <<EOF
[Unit]
Description=VC-UY volunteer runtime vc-uyr (Ashley isolant)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=RUST_LOG=info
ExecStart=$BIN $CFG
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/runtime.log
StandardError=append:$LOG_DIR/runtime.log

[Install]
WantedBy=multi-user.target
EOF

# Désactiver l'ancien service user qui crashait sans root
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$REAL_USER")" systemctl --user disable --now vc-uy-runtime.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now vc-uy-runtime.service

# Auth shim user
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$REAL_USER")" systemctl --user enable --now vc-uy-runtime-auth.service 2>/dev/null || true

sleep 2
if curl -sf --max-time 2 http://127.0.0.1:7070/api/health; then
  echo
  echo "✅ Runtime Ashley (root) OK"
else
  echo "❌ Health KO — voir $LOG_DIR/runtime.log"
  systemctl status vc-uy-runtime.service --no-pager -l | head -40
  exit 1
fi
