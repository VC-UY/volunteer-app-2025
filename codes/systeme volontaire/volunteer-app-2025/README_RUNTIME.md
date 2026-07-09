# Intégration du runtime vc-uyr

Cette app volontaire (basée sur [volunteer-app-2025](https://github.com/VC-UY/volunteer-app-2025),
branche `master`) exécute désormais les tâches via le runtime **vc-uyr**
(binaire Rust, port `7070`) à la place de Docker. Seule la couche
d'exécution a changé : l'authentification, le pont Redis Pub/Sub, le
heartbeat et la réception/soumission de tâches vers VC-UY1 sont inchangés.

## Architecture

```
VC-UY1 (serveur central)
   ↕ HTTP REST / Redis Pub/Sub          ← inchangé
App Volontaire (Django + templates)
   ↕ HTTP REST localhost:7070            ← nouveau
Runtime vc-uyr (binaire Rust, port 7070)
   ↕ syscalls kernel
Conteneur isolé (namespaces + cgroups + seccomp)
```

## Ce qui a changé

- `volontaire/services/runtime_client.py` : client HTTP vers le runtime
  (health check court, aucune exception ne remonte si le runtime est hors
  ligne).
- `redis_communication/task_handlers.py` : `TaskManager._execute_task`
  télécharge le bundle de la tâche (logique de téléchargement VC-UY1
  inchangée), l'encode en base64, le soumet au runtime, poll
  `GET /api/status` toutes les 2s jusqu'à la fin d'exécution puis récupère
  `GET /api/result`. `pause_task` / `resume_task` / `stop_task` /
  `update_limits` pilotent désormais le runtime plutôt que des conteneurs
  Docker (voir limitation ci-dessous).
- `volontaire/views.py` + `volontaire/urls.py` : nouvelles routes
  `/api/runtime/...` (statut, ressources, contrôle, disque, historique,
  soumission manuelle, résultat).
- `volontaire/templates/home.html` : nouvel onglet **Runtime vc-uyr** dans
  le tableau de bord existant (même thème Bootstrap/CSS que le reste de
  l'app, aucun nouveau framework introduit).
- `start_with_runtime.sh` : démarre le binaire vc-uyr puis l'application.

## Pas de `npm run dev` / React ici

L'app locale que vous m'avez fournie comme référence pour le protocole vc-uyr
(`new_app_volontaire.tar.gz`) a un frontend React/Vite séparé
(`frontend/`, `npm run dev`, `http://localhost:5173`). L'app de référence
**volunteer-app-2025**, elle, n'a jamais eu de frontend séparé : son
interface est un template Django classique
(`volontaire/templates/home.html`, Bootstrap + jQuery) rendu directement
par le serveur. Ce n'est pas un changement introduit par cette
intégration — c'est l'architecture d'origine de l'app de référence, et la
consigne était explicitement de garder son style CSS existant sans
introduire de nouveau framework.

Conséquence : il n'y a rien à build ni à lancer côté frontend. Démarrez
simplement le serveur Django (`start_with_runtime.sh` ou
`daphne backend.asgi:application -p 8003 -b 0.0.0.0`) et ouvrez
`http://localhost:8003/` — la page (avec l'onglet Runtime vc-uyr) est déjà
servie par Django, sans étape npm/vite.

## Limitation importante

Le runtime vc-uyr n'exécute **qu'une tâche à la fois** et n'expose que des
contrôles globaux (`pause` / `resume` / `shutdown`), pas de gestion par
tâche comme le faisait Docker (un conteneur par tâche). En conséquence :

- Les boutons Pause/Reprendre/Arrêter du tableau des tâches n'agissent que
  sur la tâche actuellement exécutée par le runtime.
- « Arrêter » une tâche revient à éteindre le runtime
  (`POST /api/control/shutdown`) : il faut le relancer
  (`start_with_runtime.sh`) pour qu'il accepte une nouvelle tâche.
- Si une tâche est déjà en cours d'exécution (`state == "Executing"`),
  toute nouvelle soumission est refusée tant qu'elle n'est pas terminée.

## Format du bundle de tâche

Le bundle est le fichier `.tar.gz` déjà téléchargé par
`_download_input_files` (logique VC-UY1 existante, inchangée) dans le
dossier d'entrée de la tâche. Il doit contenir un `run.sh` à sa racine ;
le runtime l'exécute avec `$vc_INPUT`, `$vc_OUTPUT`, `$vc_STATE`,
`$vc_LOGS`, `$vc_TASK_ID` disponibles dans l'environnement.

## Installation et démarrage

1. Suivre l'installation habituelle (une seule fois) :

   ```bash
   sudo bash volontaire-run.sh
   ```

   Cela installe Python, Redis, crée le virtualenv `venv/` et applique les
   migrations. (Docker est encore installé par ce script pour compatibilité
   mais n'est plus utilisé pour exécuter les tâches.)

2. Installer le binaire `vc-uyr` (voir le dépôt du runtime) à
   `/usr/local/bin/vc-uyr`, avec sa configuration TOML dans
   `config/vc-uyr.toml`.

3. Copier `.env.example` vers `.env` à la racine du projet et renseigner au
   besoin :

   ```
   RUNTIME_URL=http://localhost:7070
   RUNTIME_HEALTH_TIMEOUT=5
   ```

4. Démarrer le runtime puis l'application :

   ```bash
   sudo bash start_with_runtime.sh
   ```

   Ce script arrête toute instance vc-uyr existante, relance le binaire en
   arrière-plan sur le port 7070, applique les migrations puis démarre
   Daphne (ASGI) sur le port 8003.

Si le binaire `vc-uyr` n'est pas trouvé, le script affiche un
avertissement et démarre quand même l'application : le volontaire continue
de fonctionner (authentification, heartbeat, réception de tâches) mais
toute tentative d'exécution échouera proprement tant que le runtime n'est
pas démarré manuellement sur le port 7070.

## Onglet « Runtime vc-uyr »

Accessible depuis le tableau de bord de l'application (bouton en haut de
la zone principale, à côté de « Tâches ») :

- Statut en direct (online/offline, état, CPU %, mémoire, uptime).
- Formulaire de modification des ressources allouées (CPU %, RAM Mo,
  disque Mo).
- Boutons Pause / Reprendre / Arrêter (contrôle global du runtime).
- Barres de quota disque.
- Historique des tâches exécutées par le runtime.
- Soumission manuelle d'un bundle `.tar.gz` (tests) et téléchargement du
  dernier résultat disponible.

## Note sur la structure du dépôt

Le dépôt `volunteer-app-2025` (branche `master`) contient deux copies de
l'application : celle utilisée en production, à la racine du dépôt
(`manage.py`, `backend/`, `volontaire/`, `redis_communication/`,
`socket_service/`, lancée via `volontaire-run.sh` /
`launch-volunteers.sh`), et une copie plus ancienne dans
`volontaire/volontaire/` (avec son propre `manage.py`/`run.sh`, décrite par
le `README.md` d'origine mais non utilisée par les scripts de lancement
actuels). L'intégration vc-uyr ci-dessus ne touche que la copie active à la
racine du dépôt ; l'ancienne copie n'a pas été modifiée.
