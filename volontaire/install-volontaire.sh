#!/bin/bash
# Installation + lancement silencieux en arrière-plan (systemd utilisateur).
# Pas de logs interminables dans le terminal ; survit à la fermeture et au reboot.
set -e
cd "$(dirname "$0")"
chmod +x install.sh run.sh install_daemon.sh install_runtime.sh 2>/dev/null || true

./install.sh
echo ""
echo "📦 Installation runtime isolant Ashley (vc-uyr)…"
./install_runtime.sh || true
echo ""
echo "🔐 Runtime Ashley = root (namespaces). Lance si pas déjà fait :"
echo "     sudo bash $(pwd)/install_runtime_system.sh"
echo ""
echo "🚀 Démarrage en arrière-plan…"
./install_daemon.sh
