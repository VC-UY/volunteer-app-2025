# Agent de Surveillance Système

Ce projet installe un **agent système** minimal et silencieux, s'exécutant en tâche de fond via un **service `systemd`**. Il collecte ou traite des données selon vos besoins.

## 📁 Contenu du répertoire

```

collecte\_actualise/
├── agent                  # Binaire ou script exécutable de l'agent
├── install\_service.sh     # Script d'installation du service
├── uninstall\_service.sh   # Script de désinstallation du service
└── check\_service.sh       # Script pour vérifier l'état du service

````

---

## 🚀 Installation

1. Rendez le script installable :
   ```bash
   chmod +x install_service.sh
````

2. Lancez l'installation :

   ```bash
   sudo ./install_service.sh
   ```

   Cela :

   * Copie l'agent dans `/opt/system-monitor/`
   * Crée et active un service `agent.service` dans `systemd`
   * Démarre le service automatiquement au démarrage

---

## ▶️ Utilisation

### Lancer manuellement le service :

```bash
sudo systemctl start agent.service
```

### Arrêter le service :

```bash
sudo systemctl stop agent.service
```

### Redémarrer le service :

```bash
sudo systemctl restart agent.service
```

### Activer au démarrage :

```bash
sudo systemctl enable agent.service
```

### Désactiver au démarrage :

```bash
sudo systemctl disable agent.service
```

---

## 🔍 Vérification

### Vérifier que le service tourne :

```bash
sudo ./check_service.sh
```

ou directement :

```bash
systemctl status agent.service
```

> ℹ️ Le service est silencieux : aucune sortie standard ni erreur n’est enregistrée dans `journalctl`.

---

## ❌ Désinstallation

1. Rendez le script exécutable :

   ```bash
   chmod +x uninstall_service.sh
   ```

2. Lancez la désinstallation :

   ```bash
   sudo ./uninstall_service.sh
   ```

   Cela :

   * Supprime le service systemd
   * Supprime les fichiers liés à l'agent

---

## 📦 Prérequis

* Un système Linux compatible `systemd`
* Les droits `sudo` pour l'installation et la gestion du service

---

## 📁 Répertoire cible

L’agent est installé dans :

```
/opt/system-monitor/agent
```

Le fichier de service est situé dans :

```
/etc/systemd/system/agent.service
```

---

## 🔒 Sécurité

Le service tourne en tant que `root`, veillez à ce que l'agent soit **fiable et contrôlé**.

---

## ✉️ Contact

Pour toute question ou amélioration, contactez l'équipe système.



