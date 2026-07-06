# Installation volontaire VC-UY (Windows) — coordinateur déjà configuré dans settings.py
$ErrorActionPreference = "Stop"

Write-Host "Preparation de l'environnement volontaire VC-UY..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.10+ est requis. Telechargez-le sur https://www.python.org/downloads/"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning "Docker Desktop est requis pour executer les calculs. Installez-le si ce n'est pas fait."
} else {
    try { docker info | Out-Null } catch { Write-Warning "Demarrez Docker Desktop puis relancez ce script." }
}

New-Item -ItemType Directory -Force -Path ".volunteer\tasks", ".volunteer\temp_data" | Out-Null

if (Test-Path "task_docker_img\image-docker.tar") {
    Write-Host "Chargement de l'image Docker malaria..."
    docker load -i task_docker_img\image-docker.tar
}

Write-Host "Creation de l'environnement virtuel Python..."
Remove-Item -Recurse -Force venv -ErrorAction SilentlyContinue
python -m venv venv
. .\venv\Scripts\Activate.ps1

Write-Host "Installation des dependances Python..."
python -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
} else {
    pip install django djangorestframework docker psutil redis requests PyJWT channels daphne
}

Write-Host "Migrations..."
python manage.py migrate

Write-Host "Installation terminee."
