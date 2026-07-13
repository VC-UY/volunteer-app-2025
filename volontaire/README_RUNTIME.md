# Exécution sans Docker (vc-uyr)

Par défaut, l'app démarre un **runtime local compatible** (`runtime_compat_server.py`)
sur `http://127.0.0.1:7070`. Même API que le binaire Rust Ashley, sans root ni Docker.

## Démarrage
```bash
cd volontaire
bash start_with_runtime.sh
```

## Binaire Rust (optionnel)
```bash
USE_RUST_BINARY=1 bash start_with_runtime.sh
```
Nécessite souvent `sudo` (namespaces) + le shim auth (`runtime_auth_shim.py`).

## Contrat tâche
Bundle `.tar.gz` self-contained avec `run.sh` à la racine.
Env: `vc_INPUT`, `vc_OUTPUT`, `vc_STATE`, `vc_LOGS`, `vc_TASK_ID`.
