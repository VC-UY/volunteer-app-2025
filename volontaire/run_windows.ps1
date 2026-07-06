# Lancement volontaire VC-UY (Windows)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Error "Environnement virtuel introuvable. Executez install-volontaire.ps1"
}
if (-not (Test-Path "manage.py")) {
    Write-Error "Lancez ce script depuis volunteer-app-2025\volontaire"
}

. .\venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path ".volunteer\tasks", ".volunteer\temp_data" | Out-Null

if (-not (Test-Path "venv\Scripts\daphne.exe")) {
    Write-Host "Installation de daphne..."
    pip install daphne channels
}

Write-Host "Migrations..."
python manage.py migrate --noinput

$port = if ($env:VOLUNTEER_API_PORT) { $env:VOLUNTEER_API_PORT } else { "8003" }
Write-Host "Demarrage sur http://localhost:${port} ..."
& ".\venv\Scripts\daphne.exe" -b 0.0.0.0 -p $port backend.asgi:application
