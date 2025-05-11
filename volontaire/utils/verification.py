import uuid
from volontaire.utils.get_info import get_statics_infos
import os
import json
import platform
from pathlib import Path


# fonction qui verifie si le ficher exister 





def verifier_registration(pubsub):
    home_dir = Path.home()
    volunteer_dir = home_dir / '.volunteer_app'
    volunteer_dir.mkdir(parents=True, exist_ok=True)

    info_path = volunteer_dir / 'volunteer_info.json'

    # Vérification du fichier selon l'OS
    if not info_path.exists():
        print("[INFO] Le fichier volunteer_info.json est introuvable.")
    else:
        try:
            with open(info_path, 'r') as f:
                data = json.load(f)
                if 'volunteer_id' in data:
                    print("[INFO] Clé d'identification trouvée, aucune action nécessaire.")
                    return
        except json.JSONDecodeError:
            print("[WARN] Fichier volunteer_info.json invalide, on passe à la génération d'une requête.")

    # Sinon, générer les informations et publier la demande d'enregistrement
    static_info = get_statics_infos()
    request_id = str(uuid.uuid4())
    static_info['request_id'] = request_id

    # Écrire le request_id dans ~/.volunteer_app/req.info
    req_info_path = volunteer_dir / 'req.info'
    with open(req_info_path, 'w') as f:
        f.write(request_id)

    # Publie la demande sur le canal Redis
    pubsub.publish(static_info, 'VOLUNTEER_REGISTRATION')
    print(f"[INFO] Requête d'enregistrement publiée avec ID {request_id}.")























# def verifier_registration(pubsub):
#     try:
#         file = os.open('chemin vers ~/.volunteer_app/volunteer_info.json', 'r')
#         if file:
#             return
#         else:
#             static_info = get_statics_infos()
#             request_id = uuid.uuid4()
#             static_info['request_id'] = request_id
#             # ecrire l'id dans un fichier ( ~/.volunteer_app/req.info)
#             pubsub.publish(static_info, 'VOLUNTEER_REGISTRATION')
#     except Exception as e:
#         print('Une erreur s\'est produite!!'  )
#         print(str(e))