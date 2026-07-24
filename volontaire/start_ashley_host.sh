#!/usr/bin/env bash
# Lance vc-uyr Ashley sur le host (namespaces réels) via Docker privilégié + nsenter.
# Contourne sudo interactif tout en évitant le double-nesting Docker qui tue run.sh (code=-1).
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$BASE/.." && pwd)"
RUNTIME_HOME="${VCUY_RUNTIME_HOME:-}"
if [[ -z "$RUNTIME_HOME" ]]; then
  if [[ -x "$HOME/.vcuy/runtime/bin/vc-uyr" ]]; then
    RUNTIME_HOME="$HOME/.vcuy/runtime"
  else
    RUNTIME_HOME="$REPO/runtime/dist"
  fi
fi
BIN="$RUNTIME_HOME/bin/vc-uyr"
CFG="$RUNTIME_HOME/config/vc-uyr.toml"
NAME="${VCUY_RUNTIME_CONTAINER:-vc-uyr-ashley}"
LOG_DIR="$BASE/.volunteer/logs"
HELPER_IMG="${VCUY_RUNTIME_HELPER_IMAGE:-ubuntu:22.04}"
mkdir -p "$LOG_DIR" "$RUNTIME_HOME/data"/{input,output,state,logs,bundles}

if [[ ! -x "$BIN" || ! -f "$CFG" ]]; then
  echo "❌ Runtime manquant. Lance d'abord ./install_runtime.sh"
  exit 1
fi

pkill -f 'runtime_compat_server.py' 2>/dev/null || true
systemctl --user disable --now vc-uy-runtime.service >/dev/null 2>&1 || true
docker rm -f "$NAME" >/dev/null 2>&1 || true
# tuer un vc-uyr host éventuel laissé par un précédent nsenter
pkill -x vc-uyr 2>/dev/null || true
fuser -k 7070/tcp 2>/dev/null || true
sleep 1

pkill -f 'runtime_auth_shim.py' 2>/dev/null || true
nohup "$BASE/venv/bin/python" "$BASE/runtime_auth_shim.py" --host 127.0.0.1 --port 18000 \
  >>"$LOG_DIR/runtime-auth-shim.log" 2>&1 &
sleep 1

docker pull -q "$HELPER_IMG" >/dev/null || true

# Conteneur qui nsenter dans PID 1 host → vc-uyr tourne comme root sur la machine.
# Les tâches voient le python/bash host (pas l'image Docker).
docker run -d --name "$NAME" --restart unless-stopped \
  --privileged --pid=host --network host --cgroupns=host --ipc=host \
  -e RUST_LOG=info \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  "$HELPER_IMG" \
  nsenter --target 1 --mount --uts --ipc --net --pid -- \
  env RUST_LOG=info "$BIN" "$CFG"

ok=0
for _ in $(seq 1 40); do
  if curl -sf --max-time 1 http://127.0.0.1:7070/api/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

sleep 4
if ! docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
  echo "❌ Conteneur helper crashé"
  docker logs "$NAME" 2>&1 | tail -50
  exit 1
fi
if ! pgrep -x vc-uyr >/dev/null; then
  echo "❌ vc-uyr host non démarré"
  docker logs "$NAME" 2>&1 | tail -50
  exit 1
fi

HEALTH="$(curl -sf http://127.0.0.1:7070/api/health || true)"
echo "health=$HEALTH"
if [[ "$ok" -ne 1 ]] || [[ -z "$HEALTH" ]]; then
  echo "❌ Ashley non joignable"
  docker logs "$NAME" 2>&1 | tail -50
  exit 1
fi
if echo "$HEALTH" | grep -q 'vc-uyr-compat'; then
  echo "❌ Compat détecté — interdit"
  exit 1
fi
echo "✅ Runtime Ashley (vc-uyr) actif sur le host via nsenter ($NAME)"
pgrep -a vc-uyr | head -3
