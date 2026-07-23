# Runtime vc-uyr (isolant)

Livrable Ashley : remplace Docker pour exécuter les tâches volontaires dans un
environnement isolé (API HTTP `localhost:7070`).

| Fichier | Description |
|---|---|
| `vc-uyr-runtime.tar.xz` | Archive officielle (`vc-uyr` + `vc-uyr.toml`) |
| `start.sh` | Script de démarrage privilégié (sudo) fourni avec le runtime |

Installation côté volontaire :

```bash
cd volontaire && ./install_runtime.sh
```

Installe sous `~/.vcuy/runtime/{bin,config,data}` et est pris en charge par
`install_daemon.sh` / `start_with_runtime.sh`.
