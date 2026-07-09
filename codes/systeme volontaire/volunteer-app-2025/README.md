# volunteer-app-2025

Application volontaire pour le calcul distribué VolunSys-UY1 (VC-UY1).

Chaque machine volontaire fait tourner cette application, qui s'enregistre
auprès du coordinateur central (VC-UY1), reçoit des tâches de calcul via
Redis Pub/Sub et les exécute dans le runtime sandboxé **vc-uyr** (binaire
Rust, namespaces + cgroups + seccomp — remplace Docker).

**Il n'y a pas de frontend séparé** (pas de React/Vite, pas de `npm run
dev`). Le tableau de bord (`http://localhost:8003`) est un template Django
classique (Bootstrap/jQuery) servi directement par le même serveur ASGI qui
expose l'API/backend. « Backend » et « frontend » sont donc **le même
processus** : un seul serveur Daphne à lancer.

Pour le détail de l'intégration du runtime vc-uyr (architecture, routes
`/api/runtime/...`, limitations), voir [README_RUNTIME.md](README_RUNTIME.md).

## Arborescence

```
volunteer-app-2025/
├── manage.py                    Point d'entrée Django (migrate, runserver, etc.)
├── backend/                     Projet Django "racine" : settings, urls, asgi/wsgi
│   ├── settings.py              Config (DB SQLite, apps installées, RUNTIME_URL, COORDINATOR_HOST...)
│   ├── urls.py                  Inclut les routes de l'app volontaire
│   └── asgi.py                  Point d'entrée ASGI (Daphne) : HTTP + WebSocket (channels)
├── volontaire/                  Application principale (vue Django + logique métier)
│   ├── views.py / urls.py       Vues et routes (dashboard, API runtime, tâches...)
│   ├── models.py                Modèles (machine, tâches, préférences...)
│   ├── templates/home.html      Le "frontend" : dashboard HTML/Bootstrap/jQuery, onglet "Runtime vc-uyr"
│   ├── static/                  Assets statiques (logo, etc.)
│   ├── services/runtime_client.py  Client HTTP vers le runtime vc-uyr (localhost:7070)
│   ├── redis_communication/     (legacy, voir note ci-dessous)
│   ├── socket_service/          (legacy, voir note ci-dessous)
│   ├── volontaire/              ⚠️ Ancienne copie de l'app (Docker), non utilisée par les scripts actuels
│   ├── install.sh / run.sh              Installation/lancement (variante historique, non maintenue)
│   └── install_windows.ps1 / run_windows.ps1  Idem pour Windows
├── redis_communication/         App Django active : pont Redis Pub/Sub avec VC-UY1
│   ├── client.py / channels.py  Connexion et abonnement aux canaux Redis
│   ├── task_handlers.py         TaskManager : téléchargement du bundle de tâche, soumission au
│   │                            runtime vc-uyr, polling du statut, récupération du résultat
│   ├── auth_client.py           Authentification du volontaire auprès de VC-UY1
│   └── proxy_rpc.py / file_server.py  Échanges de fichiers/RPC avec le coordinateur
├── socket_service/               App Django active : WebSocket (Channels) pour le dashboard temps réel
│   ├── consumers.py / routing.py
├── config/vc-uyr.toml            Emplacement par défaut attendu pour la config du runtime
│                                  (peut être surchargé, voir "Lancement" ci-dessous)
├── agent.py                      Agent de collecte d'état système autonome (CPU/RAM/disque), utilisable hors Django
├── volunteer_daemon.py           Variante "service système" du cycle de vie du volontaire (hors Django)
├── collecte_actualise/           Service systemd Linux packageant l'agent de surveillance (agent binaire + scripts install/uninstall/check)
├── agent_version_windows/        Agent de surveillance précompilé pour Windows (service NSSM)
├── installers/                   Scripts d'installation du service volontaire (Linux systemd / Windows), voir installers/README.md
├── requirements.txt              Dépendances Python (Django, channels, daphne, redis, psutil...)
├── .env.example                  Modèle de configuration (.env à créer à la racine)
├── volontaire-run.sh              Installation complète en une commande (deps système + venv + migrations) puis lancement Daphne SANS runtime
├── start_with_runtime.sh          Lancement recommandé : démarre le runtime vc-uyr puis Daphne (backend+frontend)
├── launch-volunteers.sh           Lance N instances du volontaire en parallèle sur des ports différents (tests multi-machines simulées)
├── stop-volunteers.sh             Arrête toutes les instances Daphne du volontaire
└── README_RUNTIME.md              Détail de l'intégration du runtime vc-uyr
```

> **Note sur les doublons** : le dépôt contient deux copies de l'application :
> celle **active**, à la racine (`manage.py`, `backend/`, `volontaire/`,
> `redis_communication/`, `socket_service/`, lancée via les scripts
> `*.sh` listés ci-dessus), et une **ancienne copie** dans
> `volontaire/volontaire/` (avec son propre `manage.py`/`run.sh`, basée sur
> Docker). Utilisez uniquement les scripts à la racine du dossier
> `volunteer-app-2025/`.

## Prérequis

- Python 3.10+ (3.8+ minimum)
- Redis (installé automatiquement par `volontaire-run.sh`)
- Le binaire **runtime `vc-uyr`** compilé (dépôt `vc-uyr/`, `cargo build --release`)
  et son fichier de configuration **`vc-uyr.toml`**
- Git, 4 Go de RAM recommandés, connexion Internet stable

## Placement du runtime vc-uyr

Ce guide part du principe que, après avoir récupéré cette branche, vous
placez les deux fichiers du runtime **au même niveau que le dossier**
`volunteer-app-2025/` (et non à l'intérieur) :

```
mon_dossier_de_travail/
├── vc-uyr                  ← binaire runtime (compilé depuis le dépôt vc-uyr)
├── vc-uyr.toml             ← fichier de configuration du runtime
└── volunteer-app-2025/     ← ce dossier
```

Rendez le binaire exécutable si besoin : `chmod +x vc-uyr`.

## Installation (une seule fois)

Depuis `volunteer-app-2025/` :

```bash
sudo bash volontaire-run.sh
```

Ce script installe Python/pip/venv, Redis, crée l'environnement virtuel
`venv/`, installe `requirements.txt` et applique les migrations Django. Il
lance aussi Daphne à la fin, mais **sans le runtime** — pour l'usage
courant, arrêtez-le (Ctrl+C) et utilisez la commande de lancement ci-dessous.

Copiez ensuite le modèle de configuration, **sans écraser un `.env` existant** :

```bash
[ -f .env ] || cp .env.example .env
```

(`.env.example` est pré-rempli pour un usage **local** avec
`RUNTIME_URL=http://localhost:7070` et `COORDINATOR_HOST=localhost`. Si
vous voulez vous connecter au vrai coordinateur VC-UY1 en production,
éditez `COORDINATOR_HOST`/`COORDINATOR_PROXY_PORT` dans `.env` avec la
vraie adresse — sinon, avec `localhost`, le volontaire tentera de joindre
un Redis local sur le port 6380 et échouera en boucle avec `Connection
refused` si rien n'y écoute. Ce n'est pas bloquant pour le dashboard local
grâce au correctif d'enregistrement en arrière-plan, mais ça spamme les
logs et empêche l'enregistrement auprès d'un vrai coordinateur.)

## Lancement (backend + frontend, en une commande)

Comme `vc-uyr` et `vc-uyr.toml` sont **à côté** de `volunteer-app-2025/`
(et non dans `volunteer-app-2025/config/`), indiquez leur chemin via les
variables `RUNTIME_BIN` et `RUNTIME_CONFIG` en surchargeant les valeurs par
défaut du script :

```bash
cd volunteer-app-2025
sudo RUNTIME_BIN=../vc-uyr RUNTIME_CONFIG=../vc-uyr.toml bash start_with_runtime.sh
```

Ce script, dans l'ordre :

1. arrête toute instance `vc-uyr` déjà lancée et libère le port 7070 ;
2. démarre le binaire `vc-uyr` (avec `../vc-uyr.toml`) en arrière-plan sur le port **7070** ;
3. applique les migrations Django ;
4. démarre le serveur ASGI **Daphne** (backend API + dashboard/"frontend" HTML) sur le port **8003**.

`sudo` est nécessaire car le runtime `vc-uyr` crée des namespaces/cgroups
Linux pour isoler l'exécution des tâches (privilège root). Si `vc-uyr`
n'est pas trouvé au chemin indiqué, le script affiche un avertissement et
démarre quand même l'application Django (authentification, heartbeat,
réception de tâches fonctionnels ; seule l'exécution de tâches échouera
tant que le runtime n'est pas lancé).

### Accès

Ouvrez **http://localhost:8003** — dashboard volontaire avec l'onglet
« Runtime vc-uyr » (statut, ressources, contrôle, historique des tâches).

### Arrêter

```bash
# Arrête Daphne (Ctrl+C dans le terminal du lancement), puis :
sudo pkill -x vc-uyr        # arrête le runtime
./stop-volunteers.sh        # ou : arrête toutes les instances Daphne du volontaire
```

## Lancer en deux terminaux (recommandé pour déboguer)

Pour isoler clairement les logs du runtime de ceux de l'app (utile pour
identifier d'où vient un problème), lancez chaque composant dans son
propre terminal au lieu de `start_with_runtime.sh` :

```bash
# Terminal 1 — runtime seul, depuis le dossier qui contient vc-uyr et vc-uyr.toml
sudo ./vc-uyr vc-uyr.toml

# Terminal 2 — app volontaire seule, depuis volunteer-app-2025/
./start_volontaire.sh
```

`start_volontaire.sh` ne touche pas au runtime : il attend que
`localhost:7070` (ou `RUNTIME_HOST`/`RUNTIME_PORT` si personnalisés) soit
joignable avant d'appliquer les migrations et de lancer Daphne — peu
importe l'ordre dans lequel vous démarrez les deux terminaux. Par défaut
l'attente est indéfinie (Ctrl+C pour annuler) ; réglable avec
`RUNTIME_WAIT_TIMEOUT=<secondes>` (0 = attendre indéfiniment).

`start_with_runtime.sh` reste disponible pour tout lancer en une seule
commande (voir plus haut) ; chacune de ses lignes est aussi annotée en
commentaire avec l'équivalent à taper manuellement.

## Lancement manuel (équivalent, étape par étape, sans script)

```bash
# 1. Runtime (depuis le dossier qui contient vc-uyr et vc-uyr.toml)
sudo ./vc-uyr vc-uyr.toml &

# 2. Application (depuis volunteer-app-2025/)
cd volunteer-app-2025
source venv/bin/activate
python manage.py migrate
daphne backend.asgi:application -p 8003 -b 0.0.0.0
```

## Lancer plusieurs volontaires simulés sur une même machine

```bash
./launch-volunteers.sh 3 8003   # 3 instances sur les ports 8003, 8004, 8005
./stop-volunteers.sh            # tout arrêter
```

(Chaque instance a sa propre base SQLite dans `data_<port>/`. Cela ne
démarre pas le runtime vc-uyr, uniquement Daphne — à réserver aux tests.)

## Configuration coordinateur (production)

Dans le fichier `.env` à la racine du projet :

```
COORDINATOR_HOST=173.249.38.251
COORDINATOR_PROXY_PORT=6380
```

## Dépôt

https://github.com/VC-UY/volunteer-app-2025

## Branche

`master` (copie active) — intégration runtime vc-uyr documentée dans
[README_RUNTIME.md](README_RUNTIME.md).

## Licence

MIT
