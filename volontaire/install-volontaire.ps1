# Installation + lancement en une commande (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
& "$PSScriptRoot\install_windows.ps1"
& "$PSScriptRoot\run_windows.ps1"
