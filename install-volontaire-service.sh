#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SCRIPT="$ROOT_DIR/installers/linux/install.sh"

if [[ ! -f "$INSTALL_SCRIPT" ]]; then
  echo "Script introuvable: $INSTALL_SCRIPT"
  exit 1
fi

chmod +x "$INSTALL_SCRIPT"

if [[ $EUID -ne 0 ]]; then
  echo "Installation service (daemon) avec sudo..."
  exec sudo "$INSTALL_SCRIPT"
fi

exec "$INSTALL_SCRIPT"
