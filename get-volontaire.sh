#!/usr/bin/env bash
# Bootstrap volontaire VC-UY — une seule commande, sans Git.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.sh | bash
set -euo pipefail

REPO="${VCUY_VOLUNTEER_REPO:-VC-UY/volunteer-app-2025}"
BRANCH="${VCUY_VOLUNTEER_BRANCH:-main}"
INSTALL_PARENT="${VCUY_INSTALL_DIR:-$HOME/VC-UY}"
APP_DIR="${INSTALL_PARENT}/volunteer-app-2025"
TMP_TGZ="$(mktemp /tmp/vcuy-volunteer-XXXXXX.tar.gz)"
TMP_EXTRACT="$(mktemp -d /tmp/vcuy-volunteer-XXXXXX)"

cleanup() {
  rm -f "$TMP_TGZ" 2>/dev/null || true
  rm -rf "$TMP_EXTRACT" 2>/dev/null || true
}
trap cleanup EXIT

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "❌ Commande requise manquante: $1"
    echo "   Installez-la puis relancez."
    exit 1
  }
}

need_cmd curl
need_cmd tar

echo "═══════════════════════════════════════════════"
echo "  Volontaire VC-UY — installation automatique"
echo "═══════════════════════════════════════════════"
echo "  Source : https://github.com/${REPO} (@${BRANCH})"
echo "  Cible  : ${APP_DIR}"
echo "  Mode   : archive (pas de Git, pas d'historique)"
echo

ARCHIVE_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

download_with_retry() {
  local url="$1" out="$2" attempt=1 max=5
  while [ "$attempt" -le "$max" ]; do
    echo "📥 Téléchargement (essai ${attempt}/${max})..."
    if curl -fL --retry 3 --retry-delay 2 --connect-timeout 30 \
         --max-time 600 -o "$out" "$url"; then
      # fichier non vide
      if [ -s "$out" ]; then
        echo "✅ Archive téléchargée ($(du -h "$out" | awk '{print $1}'))"
        return 0
      fi
    fi
    echo "⚠️  Échec réseau — nouvelle tentative dans 3s..."
    sleep 3
    attempt=$((attempt + 1))
  done
  echo "❌ Impossible de télécharger l'archive depuis GitHub."
  echo "   Vérifiez votre connexion Internet et réessayez."
  exit 1
}

download_with_retry "$ARCHIVE_URL" "$TMP_TGZ"

echo "📦 Extraction..."
tar -xzf "$TMP_TGZ" -C "$TMP_EXTRACT"
SRC="$(find "$TMP_EXTRACT" -mindepth 1 -maxdepth 1 -type d | head -1)"
if [ -z "${SRC:-}" ] || [ ! -d "$SRC/volontaire" ]; then
  echo "❌ Archive invalide (dossier volontaire/ introuvable)."
  exit 1
fi

# Retirer les binaires / dossiers inutiles à un volontaire Linux/macOS
# (Windows / anciennes collectes / historique agent) — réduit disque + bruit.
rm -rf \
  "$SRC/agent_version_windows" \
  "$SRC/collecte_actualise" \
  "$SRC/.github" \
  "$SRC/volontaire/db.sqlite3" \
  "$SRC/volontaire/.volunteer" \
  2>/dev/null || true

mkdir -p "$INSTALL_PARENT"
if [ -d "$APP_DIR" ]; then
  echo "♻️  Remplacement de l'installation précédente..."
  rm -rf "$APP_DIR"
fi
mv "$SRC" "$APP_DIR"

cd "$APP_DIR/volontaire"
chmod +x install-volontaire.sh install.sh run.sh install_daemon.sh 2>/dev/null || true

echo
echo "🚀 Lancement de l'installateur..."
exec ./install-volontaire.sh
