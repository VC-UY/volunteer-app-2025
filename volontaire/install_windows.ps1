 
# install.ps1
$ErrorActionPreference = "Stop"

# === Fonctions de vérification ===

function Test-Command {
    param($cmd)
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "❌ '$cmd' est introuvable."
        return $false
    }
    return $true
}

function Ensure-Package {
    param($packageName)
    Write-Host "📦 Vérification de $packageName..."
    if (-not (choco list --local-only | Select-String $packageName)) {
        Write-Host "🛠 Installation de $packageName..."
        choco install $packageName -y
    } else {
        Write-Host "✅ $packageName est déjà installé."
    }
}

# === Vérification des prérequis ===

Write-Host "🔧 Préparation de l'environnement..."

if (-not (Test-Command choco)) {
    Write-Error "Chocolatey est requis pour installer les dépendances. Installe-le depuis https://chocolatey.org/install"
    exit 1
}

Ensure-Package docker-desktop
Ensure-Package python

# === Docker ===

Write-Host "🚀 Vérification du démarrage de Docker Desktop..."
Start-Process "Docker Desktop" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 10  # Laisse Docker se lancer

# Vérifie que Docker fonctionne
if (-not (docker info | Out-Null)) {
    Write-Host "⚠️ Docker ne semble pas encore prêt. Lance Docker Desktop manuellement et réessaie si nécessaire."
}

# === Chargement de l'image Docker ===
if (Test-Path "task_docker_img/image-docker.tar") {
    Write-Host "📦 Chargement de l'image Docker..."
    docker load -i task_docker_img/image-docker.tar
} else {
    Write-Host "⚠️ Fichier 'task_docker_img/image-docker.tar' introuvable."
}

# === Environnement virtuel ===

Write-Host "🐍 Création de l'environnement virtuel Python..."
Remove-Item -Recurse -Force venv -ErrorAction SilentlyContinue
python -m venv venv
. .\venv\Scripts\Activate.ps1

# === Paquets Python ===

Write-Host "📦 Installation des paquets Python requis..."
python -m pip install --upgrade pip
pip install django djangorestframework docker psutil redis requests PyJWT channels daphne

Write-Host "🎉 Installation terminée avec succès."
