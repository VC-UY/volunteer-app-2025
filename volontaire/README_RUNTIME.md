# Runtime vc-uyr (sans Docker)

L'exécution des tâches passe par le binaire **vc-uyr** (`localhost:7070`),
plus par Docker.

## Prérequis
- Binaire + config : `VC-UY/.vcuy/runtime/bin/vc-uyr` et `.../config/vc-uyr.toml`
- Le runtime v0.1.0 valide encore un token auprès de `[server].url` au démarrage
  (`/api/auth/validate/`). Pointer cette URL vers un endpoint compatible, ou
  obtenir d'Ashley un mode « offline / local-only ».

## Démarrage
```bash
cd volontaire
bash start_with_runtime.sh
```

## Contrat tâche
Bundle `.tar.gz` self-contained avec `run.sh` à la racine.
Variables : `vc_INPUT`, `vc_OUTPUT`, `vc_STATE`, `vc_LOGS`, `vc_TASK_ID`.
