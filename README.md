# 💻 APPLICATION VOLONTAIRE POUR L’EXÉCUTION DES CALCULS DISTRIBUÉS

---

## 📝 DESCRIPTION DU PROJET

Cette application permet à des **volontaires d’utiliser leurs ressources informatiques inutilisées** pour effectuer des calculs demandés par des gestionnaires de workflow.  
Elle offre une solution **flexible et peu coûteuse**, particulièrement adaptée aux environnements à **ressources limitées**.
Dépôt du projet : https://github.com/VC-UY/volunteer-app-2025

---

## 🎯 OBJECTIFS

- **Objectif principal** : Développer un système permettant aux volontaires de partager leurs ressources pour l’exécution de tâches de calcul.
- **Problématique** : Pallier les difficultés d’accès aux supercalculateurs et infrastructures HPC dans les zones à connectivité ou énergie instables.
- **Solution** : Système de calcul distribué basé sur des machines volontaires non dédiées, avec communication Pub/Sub via Redis.

---

## 🧩 FONCTIONNALITÉS

### ✅ INSCRIPTION DES VOLONTAIRES
- Enregistrement des capacités machine (CPU, RAM, stockage).
- Configuration des préférences d’exécution (périodes d’activation, limites de ressources).
- Gestion de profil utilisateur.

### 📡 SUIVI DE LA DISPONIBILITÉ
- Surveillance en temps réel de la machine volontaire.
- Détection des anomalies, pannes ou ralentissements.
- Mise à jour dynamique du statut vers le coordinateur.

### 📥 GESTION DES TÂCHES
- Réception automatique des tâches via **canal Redis Pub/Sub**.
- Exécution, suspension, reprise, annulation des tâches.
- Communication en temps réel de l’état de chaque tâche.
- Envoi sécurisé des résultats.

### 📊 INTERFACE GRAPHIQUE
- Tableau de bord du volontaire (tâches en cours, terminées, suspendues).
- Visualisation des performances personnelles.
- Modification des préférences d’exécution à tout moment.

### 📁 GESTION DES FICHIERS
- Réception et exécution des tâches dans des **conteneurs Docker** contenant tous les fichiers nécessaires.
- Nettoyage automatique des fichiers à la fin de l’exécution pour préserver l’espace disque.

---

## 🚀 COMMENT LANCER LE PROJET ?

### 🔧 PRÉREQUIS

- Python (avec Django)
- Redis (pour le canal Pub/Sub)
- Docker (pour l’exécution isolée des tâches)

### 📦 INSTALLATION

```bash
git clone https://github.com/VC-UY/volunteer-app-2025.git
cd volunteer-app-2025
```

### ▶️ LANCEMENT

```bash
# Depuis le dossier backend du projet
python manage.py runserver
```

📝 **Important** : Assurez-vous que le volontaire est connecté au **réseau du coordinateur** pour activer la communication Pub/Sub Redis.

---

## 📄 LICENCE

Ce projet est **open source**.  
Réutilisation, modification et contribution sont autorisées sous licence MIT.

---

## 👥 CONTRIBUTEURS

- GitHub : https://github.com/iyemte
- GitHub : https://github.com/Kamron-Ems
- GitHub : https://github.com/MorelSOPIE

---
