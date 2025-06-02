# 💻 APPLICATION VOLONTAIRE POUR L'EXÉCUTION DES CALCULS DISTRIBUÉS

---

## 📝 DESCRIPTION DU PROJET

Cette application permet à des **volontaires d'utiliser leurs ressources informatiques inutilisées** pour effectuer des calculs demandés par des gestionnaires de workflow.  
Elle offre une solution **flexible et peu coûteuse**, particulièrement adaptée aux environnements à **ressources limitées**.

**Dépôt du projet** : [https://github.com/VC-UY/volunteer-app-2025](https://github.com/VC-UY/volunteer-app-2025)

---

## 🎯 OBJECTIFS

- **Objectif principal** : Développer un système permettant aux volontaires de partager leurs ressources pour l'exécution de tâches de calcul.
- **Problématique** : Pallier les difficultés d'accès aux supercalculateurs et infrastructures HPC dans les zones à connectivité ou énergie instables.
- **Solution** : Système de calcul distribué basé sur des machines volontaires non dédiées, avec communication Pub/Sub via Redis.

---

## 🧩 FONCTIONNALITÉS

### ✅ INSCRIPTION DES VOLONTAIRES
- Enregistrement des capacités machine (CPU, RAM, stockage).
- Configuration des préférences d'exécution (périodes d'activation, limites de ressources).
- Gestion de profil utilisateur.

### 📡 SUIVI DE LA DISPONIBILITÉ
- Surveillance en temps réel de la machine volontaire.
- Détection des anomalies, pannes ou ralentissements.
- Mise à jour dynamique du statut vers le coordinateur.

### 📥 GESTION DES TÂCHES
- Réception automatique des tâches via **canal Redis Pub/Sub**.
- Exécution, suspension, reprise, annulation des tâches.
- Communication en temps réel de l'état de chaque tâche.
- Envoi sécurisé des résultats.

### 📊 INTERFACE GRAPHIQUE
- Tableau de bord du volontaire (tâches en cours, terminées, suspendues).
- Visualisation des performances personnelles.
- Modification des préférences d'exécution à tout moment.

### 📁 GESTION DES FICHIERS
- Réception et exécution des tâches dans des **conteneurs Docker** contenant tous les fichiers nécessaires.
- Nettoyage automatique des fichiers à la fin de l'exécution pour préserver l'espace disque.

---

## 🚀 COMMENT LANCER LE PROJET ?

### 🔧 PRÉREQUIS SYSTÈME
- **Python 3.8+** - [Télécharger Python](https://www.python.org/downloads/)
- **Git** - [Installer Git](https://git-scm.com/downloads)
- **Redis** - [Installer Redis](https://redis.io/docs/getting-started/installation/)
- **Docker** - [Installer Docker](https://docs.docker.com/get-docker/)

### 📦 INSTALLATION COMPLÈTE

#### 1️⃣ **Cloner le Projet**
```bash
git clone https://github.com/VC-UY/volunteer-app-2025.git
cd volunteer-app-2025
```

#### 2️⃣ **Créer un Environnement Virtuel**
```bash
# Créer l'environnement virtuel
python -m venv volunteer-env

# Activer l'environnement virtuel
# Sur Linux/Mac :
source volunteer-env/bin/activate

# Sur Windows :
volunteer-env\Scripts\activate
```

#### 3️⃣ **Installer les Dépendances**
```bash
# Installer toutes les dépendances Python
pip install -r requirements.txt
```

#### 4️⃣ **Configuration de la Base de Données**
```bash
# Depuis le dossier backend du projet
cd backend
python manage.py makemigrations
python manage.py migrate
```

### ▶️ LANCEMENT DE L'APPLICATION

#### 🚀 **Démarrer Redis** (Terminal 1)
```bash
# Démarrer le serveur Redis
redis-server
```

#### 🚀 **Démarrer l'Application** (Terminal 2)
```bash
# Activer l'environnement virtuel (si pas déjà fait)
source volunteer-env/bin/activate  # Linux/Mac
# OU
volunteer-env\Scripts\activate     # Windows

# Lancer le serveur Django
cd backend
python manage.py runserver
```

#### 🌐 **Accéder à l'Application**
- Ouvrez votre navigateur
- Allez sur : `http://127.0.0.1:8000`

### 🛑 **Arrêter l'Application**
```bash
# Dans chaque terminal, appuyez sur :
Ctrl + C

# Désactiver l'environnement virtuel :
deactivate
```

📝 **Important** : 
- Assurez-vous que **Redis fonctionne** avant de lancer l'application
- Le volontaire doit être connecté au **réseau du coordinateur** pour la communication Pub/Sub
- Gardez l'environnement virtuel **activé** pendant le développement

---

## 📄 LICENCE

Ce projet est **open source**.  
Réutilisation, modification et contribution sont autorisées sous licence MIT.

Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

## 👥 CONTRIBUTEURS

- **iyemte** - [https://github.com/iyemte](https://github.com/iyemte)
- **Kamron-Ems** - [https://github.com/Kamron-Ems](https://github.com/Kamron-Ems)
- **MorelSOPIE** - [https://github.com/MorelSOPIE](https://github.com/MorelSOPIE)

---


