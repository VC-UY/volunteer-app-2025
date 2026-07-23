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
- **Pas de Docker** — exécution via runtime local `vc-uyr-compat` (léger)

> Le volontaire **n'a pas besoin de Git**. L'installation utilise une archive (snapshot), sans historique `.git`.
> **Pas de PyTorch / CIFAR à l'install** : installés seulement à la 1ʳᵉ tâche `DISTRIBUTED_LEARNING`
> (venv dédié). OpenMalaria, Matrix, etc. restent légers.

## Installation en une commande

### Linux / macOS (recommande)

```bash
curl -fsSL https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.sh | bash
```

Cette commande :
1. telecharge une **archive legere** (pas de clone Git, pas d'historique)
2. nettoie les binaires inutiles (Windows-only, anciennes collectes)
3. installe et lance le volontaire sous `~/VC-UY/volunteer-app-2025`
4. **Linux** : demarre en arriere-plan via systemd utilisateur (`vc-uy-runtime`, `vc-uy-agent`, `vc-uy-volunteer`) — fermer le terminal OK, relance au reboot

Logs : `~/VC-UY/volunteer-app-2025/volontaire/.volunteer/logs/`  
Agent : prediction `:7071` + sync snapshots (outbox, retention locale 72 h apres envoi). Predicteur **ARX** par defaut ; hybride ARX+GRU si torch est present.

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.ps1 | iex
```

### Linux — relancer les services (deja installe)

```bash
cd ~/VC-UY/volunteer-app-2025/volontaire && ./install_daemon.sh
```

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

## Quitter le programme volontaire (Linux)

```bash
systemctl --user disable --now vc-uy-volunteer vc-uy-agent vc-uy-runtime 2>/dev/null
cd ~/VC-UY/volunteer-app-2025 && chmod +x uninstall-volontaire.sh && ./uninstall-volontaire.sh
```

Cela arrete les services systemd, les desactive au demarrage et peut supprimer l'installation locale.

## Depot

https://github.com/VC-UY/volunteer-app-2025

## Branche

`main` — branche unique et actuelle.

## Licence

MIT
