

# fonction qui verifie si le ficher exister 


import uuid
from volontaire.utils.get_info import get_statics_infos


def verifier_registration(pubsub):
    try:
        import os
        file = os.open('chemin vers ~/.volunteer_app/volunteer_info.json', 'r')
        if file:
            return
        else:
            static_info = get_statics_infos()
            request_id = uuid.uuid4()
            static_info['request_id'] = request_id
            # ecrire l'id dans un fichier ( ~/.volunteer_app/req.info)
            pubsub.publish(static_info, 'VOLUNTEER_REGISTRATION')
    except Exception as e:
        print('Une erreur s\'est produite!!'  )
        print(str(e))