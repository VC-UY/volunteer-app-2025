# Modeles embarques — hybride ARX + GRU (OBLIGATOIRE)

Les deux fichiers doivent etre presents pour demarrer l'agent :

| Fichier | Branche |
|---|---|
| `weights_arx_stay_15m.json` | ARX logistique 15D (stay_soft +15 min) |
| `gru_uy1_phase2.pt` | GRU (sequence 18D) |

Source de verite recherche :
- `research_models/linear_model/weights_arx_stay_15m.json`
- `research_models/gru_model/checkpoints/gru_uy1_phase2.pt`

Apres reentrainement, recopier ici puis rebuilder le binaire volontaire.
