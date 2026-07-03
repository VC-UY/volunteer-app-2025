# volunteer-app-2025

Application volontaire pour le calcul distribue VolunSys-UY1.

## Structure

```
volunteer-app-2025/
  volontaire/            Application Django + agent (Linux, macOS, Windows)
  collecte_actualise/    Service de collecte d'etat systeme (Linux)
  agent_version_windows/ Agent precompile Windows
```

## Prerequis

- Python 3.10+
- Docker
- Git
- 4 Go RAM recommandes
- Connexion Internet stable

## Installation rapide

### Linux / macOS

```bash
cd volontaire
chmod +x install.sh run.sh
./install.sh
newgrp docker   # si necessaire
./run.sh
```

### Windows (PowerShell administrateur)

```powershell
cd volontaire
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\install_windows.ps1
.\run_windows.ps1
```

## Configuration coordinateur (production)

Dans le fichier `.env` du dossier `volontaire/` :

```
COORDINATOR_HOST=173.249.38.251
COORDINATOR_PROXY_PORT=6380
```

## Acces local

http://localhost:8003

## Depot

https://github.com/VC-UY/volunteer-app-2025

## Branche

`version3.0` -- configuration production et client Redis proxy.

## Licence

MIT
