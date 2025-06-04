# import json
# from django.db.utils import OperationalError, ProgrammingError
# from django.core.exceptions import ImproperlyConfigured

# def initialize_machine_info():
#     try:
#         # Importation des modèles et fonctions nécessaires
#         from .models import MachineInfo, EtatMachine
#         from volontaire.utils.get_info import get_static_infos, get_dynamic_infos

#         # Étape 1 : Vérifier si la base contient déjà une machine
#         if not MachineInfo.objects.exists():
#             # Si aucune machine n'est enregistrée, on récupère les infos statiques
#             static_infos = get_static_infos()
#             if static_infos:
#                 # On retire les données brutes si présentes (non utilisées ici)
#                 static_infos.pop("raw_data", None)
#                 # On crée une nouvelle entrée MachineInfo en base
#                 machine = MachineInfo.objects.create(**static_infos)
#                 print("[INFO] Informations statiques de la machine insérées dans la base.")
#             else:
#                 print("[WARN] Aucune information statique récupérée.")
#                 return  # On arrête ici car on ne peut pas créer l'état sans machine
#         else:
#             # Si une machine existe déjà, on la récupère (la première)
#             machine = MachineInfo.objects.first()

#         # Étape 2 : Vérifier si cette machine a déjà un état dynamique enregistré
#         if not EtatMachine.objects.filter(machine=machine).exists():
#             # Récupération des informations dynamiques de la machine
#             dynamic_infos = get_dynamic_infos()
#             if dynamic_infos:
#                 # Création d'une entrée EtatMachine liée à la machine existante
#                 EtatMachine.objects.create(machine=machine, **dynamic_infos)
#                 print("[INFO] Informations dynamiques de la machine insérées dans la base.")
#             else:
#                 print("[WARN] Aucune information dynamique récupérée.")
    
#     # Gestion des erreurs liées à la base de données ou aux migrations incomplètes
#     except (OperationalError, ProgrammingError, ImproperlyConfigured) as e:
#         print(f"[INFO] Initialisation ignorée : {e}")
    
#     # Gestion des autres exceptions inattendues
#     except Exception as e:
#         print(f"[ERROR] Erreur d'initialisation des infos machine : {e}")





import json
from django.db.utils import OperationalError, ProgrammingError
from django.core.exceptions import ImproperlyConfigured

def initialize_machine_info():
    try:
        from .models import MachineInfo, EtatMachine
        from volontaire.utils.get_info import get_static_infos, get_dynamic_infos

        # Vérifie si une machine est déjà enregistrée
        if not MachineInfo.objects.exists():
            # Récupère les infos statiques
            infos = get_static_infos()
            if infos:
                infos.pop("raw_data", None)  # On enlève les données brutes si présentes
                machine = MachineInfo.objects.create(**infos)  # Création de l'objet MachineInfo
                print("[INFO] Informations machine insérées dans la base.")

                # ➕ Ajout : Récupération et sauvegarde des infos dynamiques
                dynamic_data = get_dynamic_infos(  )  # On passe l'objet machine
                if dynamic_data:
                    EtatMachine.objects.create(machine=machine, **dynamic_data)
                    print("[INFO] Informations dynamiques insérées dans la base.")
                else:
                    print("[WARN] Aucune information dynamique récupérée.")
            else:
                print("[WARN] Aucune information machine récupérée.")
    except (OperationalError, ProgrammingError, ImproperlyConfigured) as e:
        print(f"[INFO] Initialisation ignorée (BD non prête ?) : {e}")
    except Exception as e:
        print(f"[ERROR] Erreur d'initialisation des infos machine : {e}")





'''


import json
from django.db.utils import OperationalError, ProgrammingError
from django.core.exceptions import ImproperlyConfigured

def initialize_machine_info():
    try:
        from .models import MachineInfo
        from volontaire.utils.get_info import get_static_infos  

        if not MachineInfo.objects.exists():
            infos = get_static_infos()
            if infos:
                infos.pop("raw_data", None)
                MachineInfo.objects.create(**infos)
                print("[INFO] Informations machine insérées dans la base.")
            else:
                print("[WARN] Aucune information machine récupérée.")
    except (OperationalError, ProgrammingError, ImproperlyConfigured) as e:
        print(f"[INFO] Initialisation ignorée : {e}")
    except Exception as e:
        print(f"[ERROR] Erreur d'initialisation des infos machine : {e}")

'''


