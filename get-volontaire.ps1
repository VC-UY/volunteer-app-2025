# Bootstrap volontaire VC-UY — une seule commande Windows, sans Git.
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.ps1 | iex

$ErrorActionPreference = "Stop"
$Repo = if ($env:VCUY_VOLUNTEER_REPO) { $env:VCUY_VOLUNTEER_REPO } else { "VC-UY/volunteer-app-2025" }
$Branch = if ($env:VCUY_VOLUNTEER_BRANCH) { $env:VCUY_VOLUNTEER_BRANCH } else { "main" }
$InstallParent = if ($env:VCUY_INSTALL_DIR) { $env:VCUY_INSTALL_DIR } else { Join-Path $HOME "VC-UY" }
$AppDir = Join-Path $InstallParent "volunteer-app-2025"
$ZipUrl = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
$TmpZip = Join-Path $env:TEMP ("vcuy-volunteer-" + [guid]::NewGuid().ToString() + ".zip")
$TmpExtract = Join-Path $env:TEMP ("vcuy-volunteer-" + [guid]::NewGuid().ToString())

Write-Host "==============================================="
Write-Host "  Volontaire VC-UY — installation automatique"
Write-Host "==============================================="
Write-Host "  Source : https://github.com/$Repo (@$Branch)"
Write-Host "  Cible  : $AppDir"
Write-Host "  Mode   : archive (pas de Git)"
Write-Host ""

New-Item -ItemType Directory -Force -Path $InstallParent | Out-Null
New-Item -ItemType Directory -Force -Path $TmpExtract | Out-Null

$ok = $false
for ($i = 1; $i -le 5; $i++) {
  try {
    Write-Host "Telechargement (essai $i/5)..."
    Invoke-WebRequest -Uri $ZipUrl -OutFile $TmpZip -UseBasicParsing
    if ((Get-Item $TmpZip).Length -gt 0) { $ok = $true; break }
  } catch {
    Write-Host "Echec reseau — nouvelle tentative..."
    Start-Sleep -Seconds 3
  }
}
if (-not $ok) { throw "Impossible de telecharger l'archive GitHub." }

Expand-Archive -Path $TmpZip -DestinationPath $TmpExtract -Force
$Src = Get-ChildItem -Path $TmpExtract -Directory | Select-Object -First 1
if (-not $Src -or -not (Test-Path (Join-Path $Src.FullName "volontaire"))) {
  throw "Archive invalide (dossier volontaire/ introuvable)."
}

# Nettoyage package Windows: pas besoin de binaires Linux de collecte, ni .git
@(
  "collecte_actualise",
  ".github"
) | ForEach-Object {
  $p = Join-Path $Src.FullName $_
  if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
Move-Item $Src.FullName $AppDir

$Vol = Join-Path $AppDir "volontaire"
Set-Location $Vol
Write-Host "Lancement de l'installateur..."
& powershell -ExecutionPolicy Bypass -File .\install-volontaire.ps1

Remove-Item -Force $TmpZip -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $TmpExtract -ErrorAction SilentlyContinue
