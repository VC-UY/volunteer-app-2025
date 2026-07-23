#!/usr/bin/env bash
# Installe le runtime isolant vc-uyr (binaire Ashley) depuis runtime/vc-uyr-runtime.tar.xz.
# Remplace Docker : namespaces + API HTTP :7070.
# Fallback : si l'archive/binaire est absent, l'app utilise encore runtime_compat_server.py.
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$BASE/.." && pwd)"
ARCHIVE="${VCUY_RUNTIME_ARCHIVE:-}"
AUTH_SHIM_PORT="${AUTH_SHIM_PORT:-18000}"

# Cible d'install : HOME si possible, sinon runtime/dist du repo
if [[ -n "${VCUY_RUNTIME_HOME:-}" ]]; then
  RUNTIME_HOME="$VCUY_RUNTIME_HOME"
elif mkdir -p "$HOME/.vcuy/runtime" 2>/dev/null; then
  RUNTIME_HOME="$HOME/.vcuy/runtime"
else
  RUNTIME_HOME="$REPO/runtime/dist"
fi

# Sources possibles (repo VL, monorepo local, override)
if [[ -z "$ARCHIVE" ]]; then
  for cand in \
    "$REPO/runtime/vc-uyr-runtime.tar.xz" \
    "$REPO/../runtime.tar.xz" \
    "$REPO/../../runtime.tar.xz" \
    "$BASE/../runtime/vc-uyr-runtime.tar.xz"
  do
    if [[ -f "$cand" ]]; then
      ARCHIVE="$cand"
      break
    fi
  done
fi

mkdir -p "$RUNTIME_HOME/bin" "$RUNTIME_HOME/config" "$RUNTIME_HOME/data"/{input,output,state,logs,bundles}

if [[ -z "${ARCHIVE:-}" || ! -f "$ARCHIVE" ]]; then
  echo "❌ Archive runtime Ashley introuvable."
  echo "   Attendu : $REPO/runtime/vc-uyr-runtime.tar.xz"
  exit 1
fi

TMP="$(mktemp -d /tmp/vcuyr-install-XXXXXX)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "📦 Extraction runtime → $RUNTIME_HOME"
# --no-same-owner : archive souvent créée sous un autre uid (évite échec non-root)
tar --no-same-owner -xJf "$ARCHIVE" -C "$TMP"

SRC_BIN=""
SRC_TOML=""
if [[ -x "$TMP/runtime/vc-uyr" || -f "$TMP/runtime/vc-uyr" ]]; then
  SRC_BIN="$TMP/runtime/vc-uyr"
  SRC_TOML="$TMP/runtime/vc-uyr.toml"
elif [[ -f "$TMP/vc-uyr" ]]; then
  SRC_BIN="$TMP/vc-uyr"
  SRC_TOML="$TMP/vc-uyr.toml"
else
  SRC_BIN="$(find "$TMP" -type f -name 'vc-uyr' | head -1 || true)"
  SRC_TOML="$(find "$TMP" -type f -name 'vc-uyr.toml' | head -1 || true)"
fi

if [[ -z "$SRC_BIN" || ! -f "$SRC_BIN" ]]; then
  echo "❌ Binaire vc-uyr absent de l'archive ($ARCHIVE)"
  exit 1
fi

install -m 0755 "$SRC_BIN" "$RUNTIME_HOME/bin/vc-uyr"

DATA="$RUNTIME_HOME/data"
# Config adaptée machine : chemins locaux + auth shim local (boot VC-UY1).
cat >"$RUNTIME_HOME/config/vc-uyr.toml" <<EOF
# Généré par install_runtime.sh — runtime isolant vc-uyr (remplace Docker)

[volunteer]
id    = "vol-local"
token = "local-runtime-token"
name  = "Volontaire UY1"

[paths]
vc_root     = "$DATA"
input_dir   = "$DATA/input"
output_dir  = "$DATA/output"
state_dir   = "$DATA/state"
logs_dir    = "$DATA/logs"
bundles_dir = "$DATA/bundles"

[resources]
cpu_limit_percent  = 30
memory_limit_mb    = 512
cpu_threshold_high = 80
cpu_threshold_low  = 30
cpu_min_percent    = 10
cpu_max_percent    = 80
disk_total_mb      = 5000
disk_reserve_mb    = 100
runtime_size_mb    = 200
volunteer_server_port = 7070

[server]
url              = "http://127.0.0.1:${AUTH_SHIM_PORT}"
timeout_secs     = 30
max_retries      = 3
retry_delay_secs = 5

[monitoring]
heartbeat_interval_secs = 30
heartbeat_timeout_secs  = 90
log_to_file             = true
log_level               = "info"

[scheduler]
poll_interval_secs = 5
task_timeout_secs  = 3600
max_task_retries   = 3
cpu_max_percent    = 80
os_reserve_ram_mb  = 512
EOF

# Si un toml source apporte des clés utiles, on garde le nôtre (chemins machine).
# Copie de référence du package d'origine.
if [[ -n "${SRC_TOML:-}" && -f "$SRC_TOML" ]]; then
  cp -f "$SRC_TOML" "$RUNTIME_HOME/config/vc-uyr.toml.upstream"
fi

echo "✅ Runtime installé :"
echo "   bin    : $RUNTIME_HOME/bin/vc-uyr"
echo "   config : $RUNTIME_HOME/config/vc-uyr.toml"
echo "   data   : $DATA"
echo "   source : $ARCHIVE"
