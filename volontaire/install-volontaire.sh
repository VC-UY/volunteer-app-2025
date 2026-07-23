#!/bin/bash
# Installation + lancement silencieux en arrière-plan (systemd utilisateur).
# Pas de logs interminables dans le terminal ; survit à la fermeture et au reboot.
set -e
cd "$(dirname "$0")"
chmod +x install.sh run.sh install_daemon.sh 2>/dev/null || true

./install.sh
echo ""
echo "🚀 Démarrage en arrière-plan (sans bloquer le terminal)..."
./install_daemon.sh
