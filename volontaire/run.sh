#!/bin/bash

set -e

# === Vérifications minimales ===

# Vérifie que l'environnement virtuel existe
if [[ ! -f venv/bin/activate ]]; then
    echo "❌ L'environnement virtuel 'venv' est introuvable. Exécutez d'abord le script d'installation."
    exit 1
fi

# Vérifie la présence de manage.py
if [[ ! -f manage.py ]]; then
    echo "❌ Le fichier 'manage.py' est introuvable. Lancez ce script depuis la racine du projet Django."
    exit 1
fi

# Vérifie la présence de python3
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 est introuvable. Installez-le avant de continuer."
    exit 1
fi

# Vérifie la présence de daphne
if ! command -v daphne &>/dev/null; then
    echo "❌ Daphne n'est pas installé (pip install daphne)."
    exit 1
fi

# === Lancement ===

echo "✅ Activation de l'environnement virtuel..."
source venv/bin/activate

echo "✅ Lancement des migrations Django..."
python3 manage.py makemigrations
python3 manage.py migrate

echo "✅ Lancement du serveur ASGI avec Daphne..."
daphne -b 0.0.0.0 -p 8002 backend.asgi:application
