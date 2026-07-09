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

## Installation en une commande

### Linux / macOS

```bash
git clone -b main https://github.com/VC-UY/volunteer-app-2025.git && cd volunteer-app-2025/volontaire && chmod +x install-volontaire.sh && ./install-volontaire.sh
```

### Linux (mode service/daemon auto-demarrage)

```bash
git clone -b main https://github.com/VC-UY/volunteer-app-2025.git && cd volunteer-app-2025 && chmod +x install-volontaire-service.sh && ./install-volontaire-service.sh
```

Ce mode installe des services systemd (`volunteer` + `volunteer-web`) qui se lancent automatiquement au boot de la machine.

### Windows (PowerShell)

```powershell
git clone -b main https://github.com/VC-UY/volunteer-app-2025.git; cd volunteer-app-2025\volontaire; powershell -ExecutionPolicy Bypass -File .\install-volontaire.ps1
```

## Connexion coordinateur (preconfiguree)

Les volontaires n'ont **rien a configurer**. L'application utilise par defaut :

- Hote : `173.249.38.251`
- Port : **6380** (proxy Redis public VC-UY)

> Le port **6379** est le Redis interne du serveur (Docker uniquement) — ne pas l'utiliser cote volontaire.

## Acces local

http://localhost:8003

## Quitter le programme volontaire en une commande (Linux)

```bash
cd volunteer-app-2025 && chmod +x uninstall-volontaire.sh && ./uninstall-volontaire.sh
```

Cette commande arrête les services, les désactive au démarrage et supprime l'installation locale.

## Depot

https://github.com/VC-UY/volunteer-app-2025

## Branche

`main` — branche unique et actuelle.

## Licence

MIT
