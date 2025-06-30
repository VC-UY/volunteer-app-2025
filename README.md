# 💻 VOLUNTEER_APP — Plateforme de Calcul Distribué Volontaire

---

## 🧭 STRUCTURE DU PROJET

Ce dépôt contient l’ensemble des composants nécessaires pour exécuter un **système de calcul distribué basé sur des volontaires**.

```
VOLUNTEER_APP/
├── volontaire/              → Application Django + Agent volontaire (Linux/Mac/Windows)
├── collecte_actualise/      → Service de collecte d'état système (Linux)
├── agent_version_windows/   → Service Agent précompilé pour Windows (.exe + scripts)
```

---

## 📝 DESCRIPTION DES COMPOSANTS

### 1. `volontaire/`
Application principale (Django) qui :
- Reçoit les tâches via Redis Pub/Sub
- Les exécute dans des conteneurs Docker
- Gère le profil volontaire et les préférences
- Fournit une interface Web de suivi

Scripts fournis :
- `install.sh` / `run.sh` (Linux/macOS)
- `install_windows.ps1` / `run_windows.ps1` (Windows)

Voir [`volontaire/README.md`](./volontaire/README.md) pour les détails.

---

### 2. `collecte_actualise/`
Service annexe Linux permettant :
- La collecte des statistiques système (CPU, RAM, réseau)
- Leur envoi régulier au coordinateur via Redis

Scripts :
- `install_service.sh`, `uninstall_service.sh`
- `check_service.sh` pour tester le bon fonctionnement

Voir [`collecte_actualise/readme.md`](./collecte_actualise/readme.md).

---

### 3. `agent_version_windows/`
Version Windows autonome du service d'agent :
- Binaire `agent.exe` compilé
- Service installé via `install_service.bat` avec `nssm.exe`

Voir [`agent_version_windows/README.markdown`](./agent_version_windows/README.markdown).

---

## 🚀 INSTALLATION RAPIDE

### ▶️ Linux / macOS :

```bash
cd volontaire
chmod +x install.sh
./install.sh
./run.sh
```

### ▶️ Windows (PowerShell en admin) :

```powershell
cd volontaire
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\install_windows.ps1
.
un_windows.ps1
```

---

## ⚙️ PRÉREQUIS GLOBAUX

- Python 3.8+
- Docker
- Redis
- Git
- (Windows) Chocolatey pour installation automatisée

---

## 📄 LICENCE

Projet open source sous licence MIT.  
Voir [LICENSE](./volontaire/LICENSE) pour les détails.

---

## 👥 CONTRIBUTEURS

- **SergeNoah000** - [https://github.com/SergeNoah000](https://github.com/SergeNoah000)
- **iyemte** – [github.com/iyemte](https://github.com/iyemte)
- **Kamron-Ems** – [github.com/Kamron-Ems](https://github.com/Kamron-Ems)
- **MorelSOPIE** – [github.com/MorelSOPIE](https://github.com/MorelSOPIE)

---
