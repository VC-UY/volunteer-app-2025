# volunteer-app-2025

Application volontaire pour le calcul distribue VolunSys-UY1.

## Structure

```
volunteer-app-2025/
  volontaire/            Application Django + agent (Linux, macOS, Windows)
  agent/                 Agent recherche ARX+GRU (prediction 15 min + telemetrie)
  collecte_actualise/    Service de collecte d'etat systeme (Linux)
  agent_version_windows/ Agent precompile Windows
```

## Prerequis

- Python 3.10+
- Connexion Internet stable
- 4 Go RAM recommandes
- Docker (installe automatiquement par le script si besoin)

> Le volontaire **n'a pas besoin de Git**. L'installation utilise une archive (snapshot), sans historique `.git`.

## Installation en une commande

### Linux / macOS (recommande)

```bash
curl -fsSL https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.sh | bash
```

Cette commande :
1. telecharge une **archive legere** (pas de clone Git, pas d'historique)
2. nettoie les binaires inutiles (Windows-only, anciennes collectes)
3. installe et lance le volontaire automatiquement sous `~/VC-UY/volunteer-app-2025`

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.ps1 | iex
```

### Linux (mode service/daemon auto-demarrage)

```bash
curl -fsSL https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.sh | bash
cd ~/VC-UY/volunteer-app-2025 && chmod +x install-volontaire-service.sh && ./install-volontaire-service.sh
```

Ce mode installe des services systemd (`volunteer` + `volunteer-web`) qui se lancent automatiquement au boot de la machine.

Au demarrage de Daphne (`volunteer-web`), le bridge de telemetrie demarre aussi (`:7071/predict` + sync snapshots vers le site `/donnees`). Si `torch` est installable, l'agent hybride ARX+GRU complet est prefere.

### Developpeurs (clone Git — optionnel)

```bash
git clone --depth 1 -b main https://github.com/VC-UY/volunteer-app-2025.git
cd volunteer-app-2025/volontaire && chmod +x install-volontaire.sh && ./install-volontaire.sh
```

> Evitez un `git clone` complet sans `--depth 1` : l'historique est lourd et peut couper sur une connexion instable.

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
