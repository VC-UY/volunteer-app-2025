#!/bin/bash
# Démarre le runtime vc-uyr PUIS l'application volontaire, dans CE MEME
# terminal (le script reste au premier plan sur Daphne à la fin).
#
# Usage : sudo bash start_with_runtime.sh
#
# Recommandé pour déboguer : lancez plutôt le runtime et l'app volontaire
# dans deux terminaux séparés, pour voir clairement les logs de chacun et
# identifier facilement lequel pose problème :
#   - Terminal 1 (runtime seul)   : la commande manuelle indiquée plus bas
#                                    à côté de la ligne qui lance vc-uyr.
#   - Terminal 2 (app volontaire) : ./start_volontaire.sh
#     (ce script attend automatiquement que le runtime soit joignable sur
#     le port 7070 avant de démarrer Daphne)
#
# Chaque commande de ce script est accompagnée d'un commentaire donnant
# l'équivalent à taper à la main dans un terminal.
#
# Prérequis: l'installation classique a déjà été faite (venv/ créé et
# dépendances installées, cf. README_RUNTIME.md / volontaire-run.sh).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# Manuellement : cd /chemin/vers/volunteer-app-2025

RUNTIME_BIN="${RUNTIME_BIN:-/usr/local/bin/vc-uyr}"
RUNTIME_CONFIG="${RUNTIME_CONFIG:-config/vc-uyr.toml}"
VOLUNTEER_PORT="${VOLUNTEER_PORT:-8003}"

# Charger les variables de .env si présent (RUNTIME_URL, COORDINATOR_HOST, ...)
# Manuellement : set -a && source .env && set +a
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

# === Runtime vc-uyr ===

# Arrêter toute ancienne instance du runtime
# -x (nom exact du process, pas la ligne de commande complète) : évite de
# matcher le sudo/bash qui exécute ce script lui-même si RUNTIME_BIN est
# passé en variable d'environnement sur la même ligne de commande (ex:
# `sudo RUNTIME_BIN=../vc-uyr ... bash start_with_runtime.sh`), ce qui
# tuerait le script avant même qu'il démarre.
# Manuellement : sudo pkill -x vc-uyr
pkill -x vc-uyr 2>/dev/null
# Manuellement : sudo fuser -k 7070/tcp
fuser -k 7070/tcp 2>/dev/null
sleep 1

if [ -f "$RUNTIME_BIN" ]; then
    # Lance le runtime en arrière-plan (&) dans CE terminal, d'où le
    # mélange de ses logs avec ceux de Daphne plus bas.
    # Manuellement, dans un AUTRE terminal (recommandé) : depuis le
    # dossier qui contient le binaire et sa config, ex:
    #   sudo RUST_LOG=info ./vc-uyr vc-uyr.toml
    # (adaptez le nom du fichier de config à votre emplacement réel)
    RUST_LOG=info "$RUNTIME_BIN" "$RUNTIME_CONFIG" &
    RUNTIME_PID=$!
    echo "Runtime vc-uyr démarré (PID=$RUNTIME_PID)"
    sleep 2
else
    echo "AVERTISSEMENT : binaire vc-uyr non trouvé à $RUNTIME_BIN"
    echo "Le runtime doit être démarré manuellement sur le port 7070"
fi

# === Application volontaire ===

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "ERREUR : environnement virtuel introuvable. Lancez d'abord ./volontaire-run.sh (installation complète)."
    exit 1
fi

# Manuellement : source venv/bin/activate
# shellcheck disable=SC1091
source "$SCRIPT_DIR/venv/bin/activate"

echo "Application des migrations Django..."
# Manuellement : python manage.py migrate
python manage.py migrate

echo "Lancement du serveur ASGI (Daphne) sur le port $VOLUNTEER_PORT..."
# Manuellement : daphne backend.asgi:application -p 8003 -b 0.0.0.0
daphne backend.asgi:application -p "$VOLUNTEER_PORT" -b 0.0.0.0
