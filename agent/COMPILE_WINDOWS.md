# Compilation de l'Agent VC-UY1 (hybride ARX + GRU)

L'agent embarque **obligatoirement** les deux branches dans `models/` :
- `weights_arx_stay_15m.json`
- `gru_uy1_phase2.pt`

## Prérequis
- Python 3.10+
- Depuis `agent/` :

```bash
pip install -r requirements.txt pyinstaller
```

## Test rapide (avant build)

```bash
python test_hybrid_smoke.py
```

Doit afficher `OK hybride ARX+GRU` avec des scores `linear`, `gru`, `hybrid` distincts.

## Linux

```bash
cd agent
pyinstaller vc-agent-linux.spec
# → dist/vc-agent-linux
```

## Windows

```powershell
cd agent
pip install -r requirements.txt pyinstaller
pyinstaller vc-agent.spec
# → dist/vc-agent.exe
```

Les poids sous `models/` sont inclus via le `.spec` (`datas=[('models','models')]`).

## Lancement développement

```bash
cd agent
python main.py --setup
python main.py
```

Sans ARX ou sans GRU / sans torch → l'agent **refuse de démarrer**.
