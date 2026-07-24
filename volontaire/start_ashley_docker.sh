#!/usr/bin/env bash
# Lance le binaire Ashley vc-uyr avec privilèges (namespaces) via Docker.
# Utilisé quand sudo interactif n'est pas dispo mais le groupe docker l'est.
# Le process d'exécution reste vc-uyr (pas runtime_compat).
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
mkdir -p "$LOG_DIR" "$RUNTIME_HOME/data"/{input,output,state,logs,bundles}

if [[ ! -x "$BIN" || ! -f "$CFG" ]]; then
  echo "❌ Runtime manquant. Lance d'abord ./install_runtime.sh"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ docker introuvable — utilise sudo bash ./install_runtime_system.sh"
  exit 1
fi

run_docker() {
  if docker info >/dev/null 2>&1; then
    "$@"
  elif command -v sg >/dev/null 2>&1; then
    sg docker -c "$*"
  else
    "$@"
  fi
}

# Stop leftovers
pkill -f 'runtime_compat_server.py' 2>/dev/null || true
systemctl --user disable --now vc-uy-runtime.service >/dev/null 2>&1 || true
run_docker docker rm -f "$NAME" >/dev/null 2>&1 || true
fuser -k 7070/tcp 2>/dev/null || true
sleep 1

# Auth shim (user)
pkill -f 'runtime_auth_shim.py' 2>/dev/null || true
nohup "$BASE/venv/bin/python" "$BASE/runtime_auth_shim.py" --host 127.0.0.1 --port 18000 \
  >>"$LOG_DIR/runtime-auth-shim.log" 2>&1 &
sleep 1

# Conteneur privilégié : binaire Ashley + host network (port 7070)
# Image minimale avec glibc (le binaire est dynamiquement lié)
# Image avec bash+python3 : les bundles Ashley (benchmark / OpenMalaria wrappers) en dépendent.
# cgroupns=host + bind /sys/fs/cgroup : sinon crash « cgroup.subtree_control … ENOENT »
IMG="${VCUY_RUNTIME_IMAGE:-python:3.12-slim-bookworm}"
run_docker docker pull -q "$IMG" >/dev/null || true

run_docker docker run -d --name "$NAME" --restart unless-stopped \
  --privileged --network host --cgroupns=host \
  -e RUST_LOG=info \
  -v "$RUNTIME_HOME:$RUNTIME_HOME" \
  -v /tmp:/tmp \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  "$IMG" \
  "$BIN" "$CFG"

# Adapter chemins dans toml si besoin : le cfg pointe déjà vers RUNTIME_HOME/data
# Si le cfg a des chemins host absolus, --network host + bind data suffit.

ok=0
for _ in $(seq 1 30); do
  if curl -sf --max-time 1 http://127.0.0.1:7070/api/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

# Le serveur HTTP démarre avant l'init cgroup : attendre que le conteneur reste Up
sleep 4
if ! run_docker docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
  echo "❌ Conteneur Ashley crashé après démarrage"
  run_docker docker logs "$NAME" 2>&1 | tail -40
  exit 1
fi

HEALTH="$(curl -sf http://127.0.0.1:7070/api/health || true)"
echo "health=$HEALTH"
if [[ "$ok" -ne 1 ]] || [[ -z "$HEALTH" ]]; then
  echo "❌ Ashley non joignable"
  run_docker docker logs "$NAME" 2>&1 | tail -40
  exit 1
fi
if echo "$HEALTH" | grep -q 'vc-uyr-compat'; then
  echo "❌ Compat détecté — interdit"
  exit 1
fi
echo "✅ Runtime Ashley (vc-uyr) actif via conteneur privilégié $NAME"
