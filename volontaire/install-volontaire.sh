#!/bin/bash
# Installation + lancement en une seule commande (coordinateur déjà configuré dans settings.py)
set -e
cd "$(dirname "$0")"
chmod +x install.sh run.sh
./install.sh
echo ""
echo "🚀 Démarrage de l'application volontaire..."
exec ./run.sh
