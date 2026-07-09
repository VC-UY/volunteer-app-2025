#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNINSTALL_SCRIPT="$ROOT_DIR/installers/linux/uninstall.sh"

if [[ ! -f "$UNINSTALL_SCRIPT" ]]; then
  echo "Script introuvable: $UNINSTALL_SCRIPT"
  exit 1
fi

chmod +x "$UNINSTALL_SCRIPT"

if [[ $EUID -ne 0 ]]; then
  echo "Désinscription/suppression complète avec sudo..."
  exec sudo "$UNINSTALL_SCRIPT" --yes --purge-data --remove-user
fi

exec "$UNINSTALL_SCRIPT" --yes --purge-data --remove-user
