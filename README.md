# 💻 APPLICATION VOLONTAIRE POUR L'EXÉCUTION DES CALCULS DISTRIBUÉS

---

##  DESCRIPTION DU PROJET

Cette application permet à des **volontaires d'utiliser leurs ressources informatiques inutilisées** pour effectuer des calculs demandés par des gestionnaires de workflow via un système de coordinateur central.  

L'application volontaire se connecte au **réseau du coordinateur** via Redis Pub/Sub, reçoit des tâches automatiquement, les exécute dans des conteneurs Docker isolés, et renvoie les résultats au coordinateur.

**Architecture distribuée** : Coordinateur ↔ Manager ↔ **Volontaire** (cette app)

---

##  OBJECTIFS

- **Objectif principal** : Permettre aux volontaires de partager leurs ressources pour l'exécution de tâches de calcul distribué
- **Problématique** : Pallier les difficultés d'accès aux supercalculateurs et infrastructures HPC 
- **Solution** : Application volontaire autonome qui se connecte au réseau du coordinateur et exécute les tâches assignées

---

##  FONCTIONNALITÉS

###  CONNEXION AU COORDINATEUR
- Authentification automatique auprès du coordinateur
- Communication temps réel via Redis Pub/Sub
- Détection automatique des tâches assignées

###  GESTION DES RESSOURCES
- Surveillance en temps réel des ressources système (CPU, RAM, disque)
- Configuration des limites d'utilisation
- Gestion intelligente de la disponibilité

###  EXÉCUTION DES TÂCHES
- Réception automatique des tâches via Redis
- Exécution sécurisée dans des conteneurs Docker
- Isolation complète entre les tâches
- Nettoyage automatique après exécution

###  COMMUNICATION TEMPS RÉEL
- WebSockets pour l'interface utilisateur
- Pub/Sub Redis pour la communication avec le coordinateur
- Mise à jour en temps réel du statut des tâches

###  INTERFACE WEB
- Dashboard de suivi des tâches en cours et terminées
- Visualisation des performances système
- Configuration des préférences volontaire

---

##  PRÉREQUIS SYSTÈME

###  **Logiciels Requis**
- **Python 3.8+** - [Télécharger Python](https://www.python.org/downloads/)
- **Redis Server** - [Installer Redis](https://redis.io/docs/getting-started/installation/)
- **Docker** - [Installer Docker](https://docs.docker.com/get-docker/)
- **Git** - [Installer Git](https://git-scm.com/downloads)

###  **Connexion Réseau**
- **Accès au réseau du coordinateur** (même réseau local ou VPN)
- **Port Redis accessible** (par défaut 6379)
- **Connexion Internet** pour télécharger les images Docker

---

##  INSTALLATION COMPLÈTE

###  **Cloner le Projet**
```bash
git clone https://github.com/VC-UY/volunteer-app-2025.git
cd volunteer-app-2025
```

###  **Créer l'Environnement Virtuel**
```bash
# Créer l'environnement virtuel
python -m venv volunteer-env

# Activer l'environnement virtuel
# Sur Linux/Mac :
source volunteer-env/bin/activate

# Sur Windows :
volunteer-env\Scripts\activate
```

###  **Installer les Dépendances**
```bash
# Installer toutes les dépendances Python
pip install -r requirements.txt
```

###  **Vérifications Prérequis**

#### **Vérifier Docker**
```bash
# Vérifier que Docker fonctionne
docker --version
docker ps

# Si Docker n'est pas démarré :
sudo systemctl start docker  # Linux
# ou démarrer Docker Desktop    # Windows/Mac
```

####  **Vérifier la Connexion au Coordinateur**
```bash
# Tester la connexion Redis au coordinateur
# Remplacer COORDINATOR_IP par l'IP du coordinateur
redis-cli -h COORDINATOR_IP -p 6379 ping

# Devrait retourner : PONG
```

###  **Configuration de la Base de Données**
```bash
# Appliquer les migrations Django
python manage.py makemigrations
python manage.py migrate
```

---

## LANCEMENT DE L'APPLICATION

###  **Méthode Recommandée : Daphne (ASGI)**



#### **Terminal 1 : Lancer l'Application Volontaire**
```bash
# Activer l'environnement virtuel
source volunteer-env/bin/activate  # Linux/Mac
# OU
volunteer-env\Scripts\activate     # Windows

# Lancer l'application avec Daphne (ASGI)
daphne backend.asgi:application -p 8002 >> server.log 2>&1
```

#### **Terminal  2: Lancer l'Agent Volontaire (optionnel)**
```bash
# Dans un autre terminal, pour l'agent autonome
source volunteer-env/bin/activate
python agent.py
```

###  **Accéder à l'Application**
- Ouvrez votre navigateur
- Allez sur : `http://127.0.0.1:8002`
- L'application devrait se connecter automatiquement au coordinateur

---

##  CONFIGURATION

###  **Configuration Redis/Coordinateur**
Modifier le fichier `backend/settings.py` :
```python
# Configuration Redis - Coordinateur
REDIS_HOST = 'IP_DU_COORDINATEUR'  # Ex: '192.168.1.100'
REDIS_PORT = 6379
REDIS_DB = 0

# Configuration Volontaire
VOLUNTEER_NAME = 'Mon-Volontaire-001'
VOLUNTEER_ID = 'unique-volunteer-id'
```

###  **Configuration Docker**
```python
# settings.py
DOCKER_ENABLED = True
DOCKER_MEMORY_LIMIT = '2g'  # Limite mémoire par conteneur
DOCKER_CPU_LIMIT = '1.0'    # Limite CPU par conteneur
```

###  **Limites de Ressources**
```python
# settings.py  
MAX_CPU_USAGE = 80    # % maximum d'utilisation CPU
MAX_RAM_USAGE = 70    # % maximum d'utilisation RAM
MAX_DISK_USAGE = 85   # % maximum d'utilisation disque
```

---

## STRUCTURE DU PROJET

```
volunteer-app-2025/
├── manage.py                    # Point d'entrée Django
├── agent.py                     # Agent volontaire autonome
├── requirements.txt             # Dépendances Python
├── backend/                     # Configuration Django
│   ├── settings.py             # Configuration principale
│   ├── urls.py                 # Routes URL
│   ├── asgi.py                 # Configuration ASGI (WebSockets)
│   └── wsgi.py                 # Configuration WSGI
├── redis_communication/         # Communication Redis
│   ├── client.py               # Client Redis Pub/Sub
│   ├── channels.py             # Canaux de communication
│   ├── handlers.py             # Gestionnaires de messages
│   └── task_handlers.py        # Gestionnaires de tâches
├── socket_service/             # Service WebSocket
│   ├── consumers.py            # Consommateurs WebSocket
│   └── routing.py              # Routes WebSocket
├── volontaire/                 # App Django principale
│   ├── models.py               # Modèles de données
│   ├── views.py                # Vues Django
│   ├── urls.py                 # Routes de l'app
│   └── templates/              # Templates HTML
├── data/                       # Données temporaires des tâches
└── pending_requests/           # Requêtes en attente
```

---

##  FONCTIONNEMENT

### 1. **Connexion au Coordinateur**
L'application se connecte automatiquement au coordinateur via Redis et s'authentifie.

### 2. **Écoute des Tâches**
L'application écoute en permanence les canaux Redis pour détecter les nouvelles tâches assignées.

### 3. **Exécution des Tâches**
Quand une tâche arrive :
- Téléchargement des fichiers nécessaires
- Création d'un conteneur Docker isolé
- Exécution de la tâche dans le conteneur
- Récupération des résultats
- Nettoyage automatique

### 4. **Retour des Résultats**
Les résultats sont automatiquement envoyés au coordinateur via Redis.

---

##  ARRÊTER L'APPLICATION

```bash
# Dans chaque terminal, appuyez sur :
Ctrl + C

# Désactiver l'environnement virtuel :
deactivate

# Arrêter les conteneurs Docker en cours (optionnel)
docker container prune -f
```

---

## DÉPANNAGE

###  **Erreur de connexion Redis**
```bash
# Vérifier que le coordinateur est accessible
ping IP_DU_COORDINATEUR

# Vérifier que Redis fonctionne sur le coordinateur
redis-cli -h IP_DU_COORDINATEUR -p 6379 ping
```

### **Erreur Docker**
```bash
# Vérifier que Docker fonctionne
docker ps

# Redémarrer Docker si nécessaire
sudo systemctl restart docker  # Linux
```

###  **Port 8002 déjà utilisé**
```bash
# Utiliser un autre port
daphne backend.asgi:application -p 8003
```

---

##  MONITORING

### **Vérifier le Statut**
- Interface web : `http://localhost:8002`
- Logs : `tail -f server.log`
- Statut Docker : `docker ps`

### **Commandes Utiles**
```bash
# Voir les tâches en cours
docker ps

# Voir les logs de l'application
tail -f server.log

# Vérifier l'utilisation des ressources
htop
```

---

##  LICENCE

Ce projet est **open source** sous licence MIT.  
Réutilisation, modification et contribution autorisées.

---

## CONTRIBUTEURS

- **iyemte** - [https://github.com/iyemte](https://github.com/iyemte)
- **Kamron-Ems** - [https://github.com/Kamron-Ems](https://github.com/Kamron-Ems)
- **MorelSOPIE** - [https://github.com/MorelSOPIE](https://github.com/MorelSOPIE)
- **Serge Noah** - [https://github.com/SergeNoah000](https://github.com/SergeNoah000)

---

## SUPPORT

En cas de problème :
1. Vérifier que tous les prérequis sont installés
2. Vérifier la connexion au coordinateur
3. Consulter les logs : `server.log`
4. Contacter l'équipe de développement

---


