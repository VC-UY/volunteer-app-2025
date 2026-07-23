# Agent volontaire VC-UY1 — Guide d'intégration

Ce dossier est **le paquet à porter** dans l'application volontaire.

Tu peux le remettre tel quel à un agent IA / un développeur : tout le nécessaire
(collecte, modèle hybride ARX+GRU, sync serveur) est ici.

---

## 1. Quoi copier ?

**Copier tout le dossier `agent/`** (pas seulement `models/`).

Minimum indispensable :

```
agent/
├── README.md                 ← ce fichier
├── main.py                   ← boucle principale
├── collector.py              ← télémétrie locale
├── predictor.py              ← hybride ARX + GRU (OBLIGATOIRE)
├── syncer.py                 ← sync serveur VC-UY1
├── heartbeat.py
├── persistence.py
├── requirements.txt
├── models/
│   ├── README.md
│   ├── weights_arx_stay_15m.json   ← branche ARX
│   └── gru_uy1_phase2.pt           ← branche GRU
├── test_hybrid_smoke.py
├── vc-agent-linux.spec
└── vc-agent.spec
```

Les deux fichiers sous `models/` sont **obligatoires**. Sans l'un d'eux,
`HybridRuntimePredictor()` lève une erreur au démarrage.

---

## 2. Architecture (à comprendre absolument)

```
┌─────────────────────────────────────────────────────────────┐
│  Application volontaire (= ce dossier agent/)               │
│                                                             │
│  collector  →  snapshot 18D + is_available                  │
│       ↓                                                     │
│  HybridRuntimePredictor                                     │
│       ├─ ARX 15D (weights_arx_stay_15m.json)                │
│       └─ GRU   (gru_uy1_phase2.pt)                          │
│       ↓                                                     │
│  sortie : linear, gru, hybrid, launch (bool)                │
│       ↓                                                     │
│  syncer → serveur VC-UY1                                    │
│  (+ futur) → runtime vc-uyr : accepter / refuser un job     │
└─────────────────────────────────────────────────────────────┘
```

- **ARX** : logistique frugal, label `stay_soft` (≥ 80 % dispo sur 15 min).
- **GRU** : séquence temporelle 18D (besoin de PyTorch).
- **Hybride** : `hybrid = α * ARX + (1-α) * GRU` (défaut α = 0.5),
  avec porte **réseau** (si offline → score 0). La porte **secteur** ne s'applique
  qu'aux **desktops** : un laptop débranché reste prédictible (autonomie batterie).
  Seule une batterie critique (`VC_MIN_BATTERY_PERCENT`, défaut 15 %) bloque.
- **`launch`** : `hybrid >= seuil` (défaut ≈ 0.32, lu depuis les poids ARX).

Ce n'est **pas** optionnel : les deux branches doivent tourner.

---

## 3. API Python à utiliser (intégration code)

### Démarrage

```python
from predictor import HybridRuntimePredictor
from collector import get_stats

predictor = HybridRuntimePredictor()  # échoue si ARX ou GRU manquant
```

### Une prédiction

```python
snapshot = get_stats(aggregate=False)   # ou aggregate=True
detail = predictor.predict_from_snapshot(snapshot)

# detail["linear"]   float 0..1
# detail["gru"]      float 0..1
# detail["hybrid"]   float 0..1   ← score à utiliser
# detail["launch"]   bool         ← oui/non pour lancer un job
# detail["horizon_min"] == 15
```

### Après chaque snapshot (buffer 72 h)

```python
y_now = 1.0 if snapshot.get("is_available") else 0.0
predictor.observe(snapshot, y_now)
```

### Variables d'environnement utiles

| Variable | Défaut | Rôle |
|---|---|---|
| `VC_LAUNCH_THRESHOLD` | depuis poids ARX (~0.32) | Seuil oui/non |
| `VC_HYBRID_ALPHA` | `0.5` | Poids ARX dans le mélange |
| `VC_ENABLE_RLS` | `0` | Adaptation locale RLS (désactivée par défaut) |
| `VC_MIN_BATTERY_PERCENT` | `15` | Sous ce % (laptop débranché) → indisponible |
| `VC_REQUIRE_AC` | auto | `1` force porte secteur même sur laptop |

---

## 4. Dépendances

```bash
cd agent
pip install -r requirements.txt
# = psutil, requests, numpy, torch
```

Torch CPU suffit pour les machines volontaires.

### Smoke test (à faire avant toute intégration UI)

```bash
cd agent
python test_hybrid_smoke.py
```

Attendu : `OK hybride ARX+GRU` + scores `linear` / `gru` / `hybrid`.

### Lancer l'agent tel quel

```bash
python main.py --setup   # consentement + préférences horaires
python main.py           # boucle collecte → prédiction → sync
```

Serveur cible par défaut (télémétrie) : `https://vc-uy.npe-techs.com/api/agent`  
Configurable via `VCUY_SITE_API`. Dual-write optionnel vers `VCUY_RESEARCH_API`.

API locale agent : `http://127.0.0.1:7071/predict` (consultée par le coordinateur via Redis).

---

## 5. Intégration dans l'app volontaire (checklist pour l'agent IA)

1. **Embarquer** tout le dossier `agent/` (ou le compiler via PyInstaller).
2. **Garantir** que `models/weights_arx_stay_15m.json` et `models/gru_uy1_phase2.pt`
   sont au runtime (cwd / `_MEIPASS` PyInstaller).
3. **Appeler** `HybridRuntimePredictor` avant d'accepter une tâche de calcul.
4. **Décision** :
   - `launch is True` → autoriser le runtime `vc-uyr` à exécuter le bundle (`run.sh`)
   - `launch is False` → refuser / reporter la tâche
5. **Conserver** la boucle de collecte (~60 s idéal ; `main.py` est encore en 15 s « démo »).
6. **Ne pas** retirer le GRU « pour alléger » : architecture mémoire = ARX + GRU.
7. Brancher le pont HTTP local vers `vc-uyr` (port **7070**, voir `vc-uyr.toml`
   côté runtime) si l'app orchestre déjà le runtime.

### Pont logique attendu avec vc-uyr

```
Serveur / coordinateur propose une tâche
  → App volontaire demande pred = predictor.predict_from_snapshot(...)
  → si pred["launch"]:
        runtime vc-uyr exécute le bundle Self-contained (run.sh)
     sinon:
        refuse / attend
```

Le runtime `vc-uyr` exécute ; **cet agent décide**.

---

## 6. Build binaire (optionnel)

```bash
# Linux
pyinstaller vc-agent-linux.spec
# → dist/vc-agent-linux

# Windows
pyinstaller vc-agent.spec
# → dist/vc-agent.exe
```

Les specs incluent déjà `models/` via `datas=[('models','models')]`.

---

## 7. Ce que cet agent fait / ne fait pas

| Fait | Ne fait pas (encore) |
|---|---|
| Collecte CPU/RAM/réseau/secteur/préférences | UI graphique |
| Prédiction hybride ARX+GRU +15 min | Appel HTTP direct à vc-uyr (à brancher) |
| Sync snapshots vers serveur | Ordonnancement multi-tâches avancé |
| Buffer glissant 72 h | Réentraînement GRU on-device |

---

## 8. Prompt type pour un agent IA d'intégration

Tu peux coller ceci :

> Intègre le dossier `agent/` de VC-UY1 dans l'application volontaire.
> Architecture obligatoire : hybride ARX + GRU (`predictor.HybridRuntimePredictor`).
> Les poids sont dans `agent/models/`. Avant d'accepter un job vc-uyr, appelle
> `predict_from_snapshot` et n'exécute le bundle que si `launch` est True.
> Lis `agent/README.md` et ne retire ni ARX ni GRU. Dépendances : `requirements.txt`.
> Valide avec `python test_hybrid_smoke.py`.

---

## 9. Contacts artefacts recherche (ne pas confondre)

| Besoin | Chemin |
|---|---|
| **Déploiement volontaire** | `agent/` (ce dossier) |
| Re-entraîner ARX | `research_models/linear_model/` |
| Re-entraîner GRU | `research_models/gru_model/` |
| Après re-train | recopier les poids dans `agent/models/` |

Laboratoire VC-UY1 — Master 2 Recherche (prédiction frugale de disponibilité).
