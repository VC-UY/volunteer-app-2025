# Exécution sans Docker — runtime Ashley uniquement (vc-uyr)

Le binaire isolant `vc-uyr` remplace Docker pour **tous** les workflows.
Le shim Python `runtime_compat` n’est **plus** utilisé.

## Install / démarrage

```bash
cd volontaire
./install_runtime.sh
sudo bash ./install_runtime_system.sh   # recommandé (namespaces + cgroups root)
./install_daemon.sh
```

Sans `sudo`, le binaire Ashley crash (`unshare EPERM`) en user systemd. Alternatives :

```bash
# 1) root host via Docker privilégié + nsenter (groupe docker requis)
./start_ashley_host.sh

# 2) conteneur privilégié seul (cgroupns=host) — API OK, exécution tâches plus fragile
./start_ashley_docker.sh
```

Pas de fallback `runtime_compat`.

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

Bundle `.tar.gz` self-contained avec `run.sh` à la racine (produit par le **Manager**, pas par Ashley).

Env injectées par le runtime : `vc_INPUT`, `vc_OUTPUT`, `vc_STATE`, `vc_LOGS`, `vc_TASK_ID`.

Le `run.sh` doit écrire dans `$vc_OUTPUT` au minimum :
- `progress.txt`
- `result.txt`

Chemins runtime alignés Ashley : `/tmp/vc/{input,output,state,logs,bundles}`.

### Note isolant

Si Ashley accepte la tâche puis échoue (`run.sh terminé code=-1` / « Résultat introuvable »),
l’app volontaire **relance le même `run.sh` en local** (même contrat `vc_*`) pour ne pas
bloquer les workflows — en attendant un correctif seccomp côté `vc-uyr`.
