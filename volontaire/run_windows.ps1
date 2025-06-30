# run.ps1
$ErrorActionPreference = "Stop"

# === Vérifications ===

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "❌ L'environnement virtuel est introuvable. Exécute d'abord 'install_windows.ps1'."
    exit 1
}

if (-not (Test-Path "manage.py")) {
    Write-Host "❌ Fichier 'manage.py' introuvable. Lance ce script depuis la racine du projet Django."
    exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ python n'est pas disponible."
    exit 1
}

if (-not (Get-Command daphne -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Daphne n'est pas installé. (pip install daphne)"
    exit 1
}

# === Lancement ===

Write-Host "✅ Activation de l'environnement virtuel..."
. .\venv\Scripts\Activate.ps1

Write-Host "✅ Lancement des migrations Django..."
python manage.py makemigrations
python manage.py migrate

Write-Host "✅ Lancement du serveur ASGI avec Daphne..."
daphne -b 0.0.0.0 -p 8002 backend.asgi:application
 
