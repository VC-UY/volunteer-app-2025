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

## 🚀 INSTALLATION & LANCEMENT

### 🔧 PRÉREQUIS SYSTÈME

- **Python 3.8+**  
- **Docker**  
- **Redis**  
- **Git**
- **(Windows uniquement)** : [Chocolatey](https://chocolatey.org/install) pour installer automatiquement Python et Docker si nécessaires.

---

### 📦 INSTALLATION AUTOMATISÉE

#### ▶️ Sur Linux / macOS :

```bash
# Depuis la racine du projet
chmod +x install.sh
./install.sh
```

#### ▶️ Sur Windows (PowerShell) :

```powershell
# Exécuter PowerShell en tant qu’administrateur
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\install_windows.ps1
```

Ce script :
- Vérifie la présence de Docker, Python, Redis.
- Crée un environnement virtuel Python.
- Installe les dépendances.
- Charge l’image Docker si disponible.

---

## ▶️ LANCEMENT DE L'APPLICATION

#### ▶️ Linux / macOS :

```bash
./run.sh
```

#### ▶️ Windows :

```powershell
.\run_windows.ps1
```

Cela :
- Active l’environnement virtuel
- Lance les migrations Django
- Démarre le serveur ASGI via **Daphne** sur le port `8002`

---

## 🌐 ACCÈS À L'APPLICATION

- Accédez à : [http://localhost:8002](http://localhost:8002)

---

## 🛑 POUR ARRÊTER

```bash
Ctrl + C     # pour arrêter Daphne
deactivate   # pour désactiver l’environnement Python
```

---

## 📄 LICENCE

Ce projet est **open source**.  
Réutilisation, modification et contribution sont autorisées sous licence MIT.

Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

## 👥 CONTRIBUTEURS
- **SergeNoah000** - [https://github.com/SergeNoah000](https://github.com/SergeNoah000)
- **iyemte** - [https://github.com/iyemte](https://github.com/iyemte)
- **Kamron-Ems** - [https://github.com/Kamron-Ems](https://github.com/Kamron-Ems)
- **MorelSOPIE** - [https://github.com/MorelSOPIE](https://github.com/MorelSOPIE)

---
