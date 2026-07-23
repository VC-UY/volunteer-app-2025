# Exécution sans Docker — runtime Ashley uniquement (vc-uyr)

Le binaire isolant `vc-uyr` remplace Docker pour **tous** les workflows.
Le shim Python `runtime_compat` n’est **plus** utilisé.

## Install / démarrage

```bash
cd volontaire
./install_runtime.sh
sudo bash ./install_runtime_system.sh   # OBLIGATOIRE (namespaces root)
./install_daemon.sh
```

Sans `sudo`, le binaire Ashley crash (`unshare EPERM`). Pas de fallback compat.

Commande volontaire (install complète) :
```bash
curl -fsSL https://raw.githubusercontent.com/VC-UY/volunteer-app-2025/main/get-volontaire.sh | bash
```

## Vérifier

```bash
curl -s http://127.0.0.1:7070/api/health
# ne doit PAS contenir "vc-uyr-compat"
```

## Contrat tâche

Bundle `.tar.gz` self-contained avec `run.sh` à la racine.
Env: `vc_INPUT`, `vc_OUTPUT`, `vc_STATE`, `vc_LOGS`, `vc_TASK_ID`.
