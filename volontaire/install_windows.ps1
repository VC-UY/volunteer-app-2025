# Installation volontaire VC-UY (Windows) — une seule commande, tout automatique
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Preparation de l'environnement volontaire VC-UY..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.10+ requis. Installez-le depuis https://www.python.org/downloads/ (cochez 'Add to PATH')."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning "Docker Desktop requis pour les calculs. Installez-le depuis https://www.docker.com/products/docker-desktop/"
} else {
    try { docker info | Out-Null } catch { Write-Warning "Demarrez Docker Desktop puis relancez." }
}

New-Item -ItemType Directory -Force -Path ".volunteer\tasks", ".volunteer\temp_data" | Out-Null

if (Test-Path "task_docker_img\image-docker.tar") {
    Write-Host "Chargement de l'image Docker malaria..."
    docker load -i task_docker_img\image-docker.tar
} elseif (-not (docker image inspect malaria-exp:latest 2>$null)) {
    Write-Host "Telechargement de l'image malaria-exp:latest..."
    docker pull malaria-exp:latest 2>$null
}

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
    pip install django djangorestframework docker psutil redis requests PyJWT channels daphne
}

if (-not (Test-Path "venv\Scripts\daphne.exe")) {
    pip install daphne channels
}

Write-Host "Migrations..."
python manage.py migrate --noinput

Write-Host "Installation terminee."
