# Agent de Surveillance Système

## Présentation
L'**Agent de Surveillance Système** est un outil conçu pour collecter des données sur les performances et la configuration des ordinateurs des étudiants dans un environnement éducatif. Il s'exécute en arrière-plan en tant que service Windows, recueillant des métriques telles que l'utilisation du processeur, la mémoire, l'espace disque, l'activité réseau et les détails matériels. Les données collectées sont enregistrées localement et envoyées périodiquement à un serveur central pour analyse, permettant aux administrateurs de surveiller la santé des systèmes et d'assurer des performances optimales pour les activités éducatives.

Cet agent a été développé pour :
- Surveiller l'utilisation des ressources pour identifier les goulets d'étranglement.
- Recueillir un inventaire des matériels et logiciels pour la gestion des actifs.
- Minimiser l'impact sur les performances du système tout en fonctionnant en arrière-plan.

## Fonctionnalités
- Collecte des informations initiales du système (par exemple, détails du système d'exploitation, type de processeur, informations BIOS) et des métriques continues (par exemple, utilisation du processeur, mémoire, réseau).
- Enregistre les données dans des fichiers JSON compressés dans le répertoire `C:\Program Files\SystemMonitor\data`.
- Envoie les données à un serveur central (par défaut : `192.168.1.165:12345`) toutes les 30 secondes.
- Démarre automatiquement avec Windows en tant que service, sans interaction de l'utilisateur.
- Enregistre les erreurs dans `C:\ProgramData\SystemMonitor\system_monitor.log` pour le dépannage.

## Prérequis
- Windows 10 ou ultérieur.
- Privilèges administratifs pour l'installation.
- Le paquet de distribution comprend :
  - `agent.exe` : L'exécutable de l'agent de surveillance.
  - `nssm.exe` : Outil Non-Sucking Service Manager pour créer le service Windows.
  - `install_service.bat` : Script pour installer le service.
  - `uninstall_service.bat` : Script pour supprimer le service.
  - `README.markdown` : Ce fichier de documentation.

## Installation
### Étapes
1. **Extraire le paquet** :
   - Décompressez le paquet de distribution dans un dossier temporaire (par exemple, `C:\Users\<votre_nom>\Desktop\collecte\agent_version_windows`).
   - Assurez-vous que les fichiers `agent.exe`, `nssm.exe`, `install_service.bat`, `uninstall_service.bat` et `README.markdown` sont présents.

2. **Exécuter le script d'installation** :
   - Cliquez avec le bouton droit sur `install_service.bat` et sélectionnez « Exécuter en tant qu'administrateur ».
   - Le script va :
     - Copier les fichiers vers `C:\Program Files\SystemMonitor`.
     - Créer les répertoires `C:\Program Files\SystemMonitor\data` pour les données et `C:\ProgramData\SystemMonitor` pour les journaux.
     - Installer `agent.exe` en tant que service Windows nommé `SystemMonitorAgent`.
     - Démarrer le service automatiquement.

3. **Vérifier l'installation** :
   - Ouvrez le Gestionnaire des tâches ou Services (`services.msc`) et recherchez `SystemMonitorAgent`.
   - Vérifiez que des fichiers `.json.gz` sont générés dans `C:\Program Files\SystemMonitor\data`.
   - Consultez `C:\ProgramData\SystemMonitor\system_monitor.log` pour détecter d'éventuelles erreurs.

## Désinstallation
1. **Exécuter le script de désinstallation** :
   - Cliquez avec le bouton droit sur `uninstall_service.bat` (situé dans `C:\Program Files\SystemMonitor`) et sélectionnez « Exécuter en tant qu'administrateur ».
   - Le script va :
     - Arrêter et supprimer le service `SystemMonitorAgent`.
     - Proposer de supprimer les répertoires `C:\Program Files\SystemMonitor`, `C:\ProgramData\SystemMonitor` et le fichier `machine_id.txt`.

2. **Nettoyage manuel (facultatif)** :
   - Si les répertoires n'ont pas été supprimés, vous pouvez les supprimer manuellement.

## Notes pour les étudiants
- L'agent s'exécute silencieusement en arrière-plan et n'interfère pas avec l'utilisation normale de l'ordinateur.
- Il nécessite une connexion Internet pour envoyer les données au serveur. En mode hors ligne, les données sont stockées localement jusqu'à ce qu'une connexion soit disponible.
- Ne supprimez pas le répertoire `C:\Program Files\SystemMonitor\data` ou le fichier `machine_id.txt` pendant que l'agent est en cours d'exécution, car cela pourrait provoquer des erreurs.

## Notes pour les administrateurs
- **Configuration du serveur** :
  - Assurez-vous que le serveur à l'adresse `192.168.1.165:12345` est opérationnel et accessible.
  - Si vous utilisez un autre serveur, modifiez `SERVER_HOST` et `SERVER_PORT` dans le script source (`agent.py`) avant de reconstruire `agent.exe`.
- **Limites de stockage** :
  - L'agent cesse de collecter des données si le répertoire `data` dépasse 200 Mo pour éviter les problèmes d'espace disque.
- **Dépannage** :
  - Consultez `C:\ProgramData\SystemMonitor\system_monitor.log` pour les erreurs (par exemple, problèmes de connexion au serveur, erreurs WMI).
  - Exécutez `agent.exe` manuellement depuis `C:\Program Files\SystemMonitor` pour diagnostiquer les problèmes avant l'installation en tant que service :
    ```powershell
    cd C:\Program Files\SystemMonitor
    .\agent.exe
    ```
- **Permissions** :
  - Le service s'exécute sous le compte SYSTEM pour accéder aux métriques du système.
  - Les erreurs WMI peuvent nécessiter des privilèges administratifs ou des ajustements des paramètres de sécurité.

## Contact
Pour toute assistance, contactez le département informatique ou le développeur du projet [https://github.com/SergeNoah000](https://github.com/SergeNoah000) ou par mail [gaetan.noah@facsciences-uy1.cm](mailto:gaetan.noah@facsciences-uy1.cm).

---
*Généré le 22 juin 2025*