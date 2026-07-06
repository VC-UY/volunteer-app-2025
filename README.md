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
## Connexion coordinateur (preconfiguree)

Les volontaires n'ont **rien a configurer**. L'application utilise par defaut :

- Hote : `173.249.38.251`
- Port : **6380** (proxy Redis public VC-UY)

> Le port **6379** est le Redis interne du serveur (Docker uniquement) — ne pas l'utiliser cote volontaire.

Installation en une commande :

```bash
git clone https://github.com/VC-UY/volunteer-app-2025.git && cd volunteer-app-2025/volontaire && chmod +x install-volontaire.sh && ./install-volontaire.sh
```
```

## Acces local

http://localhost:8003

## Depot

https://github.com/VC-UY/volunteer-app-2025

## Branche

`version3.0` -- configuration production et client Redis proxy.

## Licence

MIT
