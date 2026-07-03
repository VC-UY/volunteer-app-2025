# Installation du Service Volontaire

Ce dossier contient les scripts d'installation et de désinstallation du service volontaire pour différentes plateformes.

## 📋 Table des Matières
- [Prérequis](#prérequis)
- [Installation sur Linux](#installation-sur-linux)
- [Installation sur Windows](#installation-sur-windows)
- [Vérification](#vérification)
- [Désinstallation](#désinstallation)
- [Dépannage](#dépannage)

---

## Prérequis

### Commun à toutes les plateformes
- ✅ **Python 3.8+** installé
- ✅ **Accès réseau** au serveur coordinateur
- ✅ **Configuration** : `redis_communication/config.py` avec l'adresse du coordinateur

### Linux
- Ubuntu 18.04+ / Debian 10+ / CentOS 8+ / RHEL 8+
- Privilèges `sudo` ou accès root
- `systemd` (installé par défaut sur les distributions modernes)

### Windows
- Windows 10+ / Windows Server 2016+
- Privilèges administrateur
- PowerShell 5.0+

---

## Installation sur Linux

### 1️⃣ Préparation
```bash
# Se placer dans le dossier du projet
cd /chemin/vers/volunteer-app-2025

# Rendre le script exécutable
chmod +x installers/linux/install.sh
```

### 2️⃣ Installation
```bash
# Lancer l'installation avec sudo
sudo installers/linux/install.sh
```

### 3️⃣ Ce que fait le script
✅ Détecte votre distribution Linux  
✅ Crée un utilisateur système `volunteer`  
✅ Installe Python 3 et les dépendances si nécessaire  
✅ Crée un environnement virtuel Python  
✅ Installe les dépendances du projet  
✅ Configure le service systemd  
✅ Démarre automatiquement le service  

### 4️⃣ Commandes utiles
```bash
# Vérifier le statut
sudo systemctl status volunteer

# Voir les logs en temps réel
sudo journalctl -u volunteer -f

# Redémarrer le service
sudo systemctl restart volunteer

# Arrêter le service
sudo systemctl stop volunteer

# Désactiver le démarrage automatique
sudo systemctl disable volunteer
```

---

## Installation sur Windows

### 1️⃣ Préparation
- Assurez-vous que Python est installé et dans le PATH
- Ouvrez PowerShell en tant qu'**Administrateur**

### 2️⃣ Installation
```powershell
# Naviguer vers le dossier des installateurs
cd C:\chemin\vers\volunteer-app-2025\installers\windows

# Exécuter le script d'installation
.\install.bat
```

### 3️⃣ Ce que fait le script
✅ Vérifie que Python est installé  
✅ Télécharge et installe NSSM (Non-Sucking Service Manager)  
✅ Crée l'environnement virtuel Python  
✅ Installe les dépendances du projet  
✅ Configure le service Windows  
✅ Démarre automatiquement le service  

### 4️⃣ Commandes utiles
```powershell
# Vérifier le statut
sc query VolunteerService

# Démarrer le service
net start VolunteerService

# Arrêter le service
net stop VolunteerService

# Ouvrir l'interface de configuration NSSM
C:\volunteer-app\nssm\nssm.exe edit VolunteerService

# Voir les logs
type C:\volunteer-app\logs\service_stdout.log
type C:\volunteer-app\logs\service_stderr.log
```

---

## Vérification

### Après l'installation, vérifiez que tout fonctionne :

#### Linux
```bash
# Le service doit être "active (running)"
sudo systemctl status volunteer

# Les logs doivent montrer une connexion réussie
sudo journalctl -u volunteer -n 20
```

Vous devriez voir quelque chose comme :
```
✓ Connected to Redis proxy at coordinator.example.com:6380
✓ Subscribed to channels: volunteer/broadcast, volunteer/tasks
📊 Service started - Ready to receive tasks
```

#### Windows
```powershell
# Le service doit être "RUNNING"
sc query VolunteerService

# Vérifier les logs
type C:\volunteer-app\logs\service_stdout.log | Select-Object -Last 20
```

---

## Désinstallation

### Linux
```bash
# Lancer le script de désinstallation
sudo installers/linux/uninstall.sh
```

Le script vous demandera :
- Si vous voulez supprimer la base de données et les logs
- Si vous voulez supprimer l'utilisateur système `volunteer`

### Windows
```powershell
# Ouvrir PowerShell en tant qu'Administrateur
cd C:\chemin\vers\volunteer-app-2025\installers\windows

# Lancer la désinstallation
.\uninstall.bat
```

Le script vous demandera :
- Si vous voulez supprimer la base de données et les logs

---

## Dépannage

### ❌ Problème: "Python n'est pas installé ou pas dans le PATH"

**Linux:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv

# CentOS/RHEL
sudo yum install python3 python3-pip
```

**Windows:**
- Téléchargez Python depuis [python.org](https://www.python.org/downloads/)
- **IMPORTANT**: Cochez "Add Python to PATH" lors de l'installation

### ❌ Problème: "Le service ne démarre pas"

**Linux:**
```bash
# Vérifier les logs détaillés
sudo journalctl -u volunteer -xe

# Vérifier la configuration Redis
cat /opt/volunteer-app/redis_communication/config.py

# Tester la connexion au coordinateur
telnet coordinator.example.com 6380
```

**Windows:**
```powershell
# Vérifier les logs d'erreur
type C:\volunteer-app\logs\service_stderr.log

# Tester manuellement le démon
cd C:\volunteer-app
.\exp-env\Scripts\python.exe volunteer_daemon.py
```

### ❌ Problème: "Connexion refusée au coordinateur"

Vérifiez :
1. **Adresse du coordinateur** dans `redis_communication/config.py`
2. **Firewall** : Le port 6380 doit être ouvert sur le coordinateur
3. **Réseau** : Testez avec `ping coordinator.example.com`

```bash
# Tester la connexion Redis
redis-cli -h coordinator.example.com -p 6380 ping
```

### ❌ Problème: "Privilèges insuffisants"

**Linux:**
```bash
# Vous devez utiliser sudo
sudo installers/linux/install.sh
```

**Windows:**
- Clic droit sur `install.bat`
- Sélectionnez "Exécuter en tant qu'administrateur"

### ❌ Problème: "Module 'redis' not found"

Les dépendances ne sont pas installées. Réinstallez manuellement :

**Linux:**
```bash
cd /opt/volunteer-app
source exp-env/bin/activate
pip install -r requirements.txt
```

**Windows:**
```powershell
cd C:\volunteer-app
.\exp-env\Scripts\activate
pip install -r requirements.txt
```

### ❌ Problème: Reconnexion automatique ne fonctionne pas

Le service devrait se reconnecter automatiquement en cas de perte de connexion.

**Linux - Vérifier les paramètres de reconnexion:**
```bash
sudo journalctl -u volunteer | grep -i "reconnect"
```

**Windows - Vérifier NSSM:**
```powershell
# La configuration de redémarrage doit être "Restart"
C:\volunteer-app\nssm\nssm.exe edit VolunteerService
# Onglet "Exit actions" -> "Restart application"
```

---

## 📁 Structure des Répertoires Installés

### Linux
```
/opt/volunteer-app/
├── exp-env/              # Environnement virtuel Python
├── redis_communication/  # Module de communication Redis
├── volontaire/          # Application Django
├── volunteer_daemon.py  # Point d'entrée du service
├── db.sqlite3          # Base de données
├── logs/               # Logs de l'application
└── requirements.txt    # Dépendances Python
```

### Windows
```
C:\volunteer-app\
├── exp-env\              # Environnement virtuel Python
├── nssm\                # NSSM (gestionnaire de services)
├── redis_communication\  # Module de communication Redis
├── volontaire\          # Application Django
├── volunteer_daemon.py  # Point d'entrée du service
├── db.sqlite3          # Base de données
├── logs\               # Logs de l'application (service_stdout.log, service_stderr.log)
└── requirements.txt    # Dépendances Python
```

---

## 🔒 Sécurité

### Linux
Le service s'exécute sous l'utilisateur système `volunteer` avec :
- Pas de shell interactif (`/bin/false`)
- Pas de nouveaux privilèges (`NoNewPrivileges=true`)
- Répertoire temporaire isolé (`PrivateTmp=true`)

### Windows
Le service s'exécute sous le compte système local par défaut.

**Pour plus de sécurité, créez un compte dédié :**
1. Créez un utilisateur Windows "VolunteerService"
2. Ouvrez `C:\volunteer-app\nssm\nssm.exe edit VolunteerService`
3. Onglet "Log on" → Configurez le compte utilisateur

---

## 🆘 Support

Si vous rencontrez des problèmes non couverts par ce guide :

1. **Vérifiez les logs** en priorité
2. **Consultez** le fichier `DEPLOYMENT_VPS_GUIDE.md` pour le coordinateur
3. **Contactez** l'administrateur du coordinateur

---

## 📝 Notes Importantes

- ⚠️ **Ne jamais** exposer le port 6380 publiquement sans authentification
- ⚠️ **Sauvegardez** régulièrement `db.sqlite3`
- ⚠️ **Surveillez** l'espace disque (logs + fichiers temporaires)
- ✅ **Mettez à jour** régulièrement les dépendances Python

---

**Bon calcul distribué!** 🚀
