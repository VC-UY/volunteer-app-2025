# Installation volontaire VC-UY (Windows) — une seule commande, tout automatique
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Preparation de l'environnement volontaire VC-UY..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.10+ requis. Installez-le depuis https://www.python.org/downloads/ (cochez 'Add to PATH')."
}

# Docker n'est plus requis : l'execution passe par le runtime vc-uyr.

New-Item -ItemType Directory -Force -Path ".volunteer\tasks", ".volunteer\temp_data" | Out-Null

Write-Host "Creation de l'environnement virtuel Python..."
Remove-Item -Recurse -Force venv -ErrorAction SilentlyContinue
python -m venv venv
. .\venv\Scripts\Activate.ps1

Write-Host "Installation des dependances Python..."
python -m pip install --upgrade pip
$req = if (Test-Path "requirements.txt") { "requirements.txt" }
       elseif (Test-Path "..\requirements.txt") { "..\requirements.txt" }
       else { $null }
if ($req) {
    pip install -r $req
} else {
    pip install django djangorestframework psutil redis requests PyJWT channels daphne
}

if (-not (Test-Path "venv\Scripts\daphne.exe")) {
    pip install daphne channels
}

Write-Host "Migrations..."
python manage.py migrate --noinput

Write-Host "Installation terminee."
