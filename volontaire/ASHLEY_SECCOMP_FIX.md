# Correctif Ashley — seccomp tue run.sh (code=-1)

## Symptôme
```
[SECCOMP] Installation filtre — 29 syscalls bloqués, 111 autorisés
[EXEC] run.sh terminé (code=-1)
[INT] Résultat introuvable
```
Le même `run.sh` (y compris l’exemple Ashley) **marche hors isolant**, meurt **dedans**.

## Cause
Profil `Standard` : allowlist incomplète. Extraite du binaire livré (`vc-uyr` 2.6 Mo).

### Manquants critiques (bloquent bash/python immédiatement)
| Syscall | Pourquoi |
|---------|----------|
| `read` | Toute lecture de fichier/stdin |
| `close` | Fermeture de fd |
| `mmap` / `mprotect` | Chargeur ELF / libc / Python |
| `open` | Ouverture classique (souvent en plus de `openat`) |
| `dup2` / `dup3` | Redirections shell |

### Déjà autorisés (extrait)
`write`, `openat`, `munmap`, `brk`, `exit_group`, `execve`, `vfork`, `wait4`,
`clone`/`clone3`, `futex`, `arch_prctl`, `fcntl`, `ioctl`, `socket`, …

→ Un process peut `execve` puis meurt au premier `read`/`close`/`mmap` → `code=-1` (signal, souvent SIGSYS).

## Correctif demandé (Ashley)
Dans `src/worker/seccomp.rs` (profil `Standard`), **ajouter au minimum** :

```text
read, readv, writev, close,
mmap, mprotect, mremap,
open, creat,
dup2, dup3,
pipe,           # en plus de pipe2
pwrite64,
statx,          # kernels récents
epoll_create1, epoll_ctl, epoll_wait,   # utile Python
eventfd2, signalfd4,                    # utile runtimes
```

Rebuilder + livrer un nouveau `vc-uyr` (+ `runtime.tar.xz`).

Option utile : profil `Permissive` / `Debug` (SECCOMP log-only) activable via `vc-uyr.toml` pour valider avant durcissement.

## Validation chez nous (après nouveau binaire)
```bash
cd VL/volunteer-app-2025/volontaire
./install_runtime.sh
./start_ashley_host.sh   # ou sudo bash ./install_runtime_system.sh

# Bundle exemple Ashley (result.txt + progress.txt dans $vc_OUTPUT)
curl -s http://127.0.0.1:7070/api/health   # runtime=vc-uyr
# POST /api/task avec bundle_example_self_contained.tar.gz
# Attendu : state Executing → Ready, GET /api/result ready=true, exit_code=0
```

## Périmètre
- **Ashley** : patch seccomp + nouveau binaire.
- **Nous** : pas de fallback local ; on garde uniquement le contrat `run.sh` / `/tmp/vc` / `result.txt`.
