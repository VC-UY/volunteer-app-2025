import os
import django
import json
import time
from uuid import UUID
import redis

<<<<<<< HEAD
#  Configuration Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")  # remplace par ton vrai nom de projet
django.setup()

# Import après setup Django
from volontaire.models import MachineInfo  # type: ignore
from django.utils import timezone

#  Initialiser Redis
=======
# ⚙️ Configuration Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")  # remplace par ton vrai nom de projet
django.setup()

# 📦 Import après setup Django
from volontaire.models import MachineInfo  # type: ignore
from django.utils import timezone

# 🔌 Initialiser Redis
>>>>>>> 786acc5b158bf5aef3b8865c29bf1cf491ec0800
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
pubsub = redis_client.pubsub()

def publier_disponibilite(volunteer_id):
    message = {
        "volunteer_id": str(volunteer_id),
        "status": "available",
        "timestamp": time.time()
    }

    redis_client.publish("VOLUNTEER_AVAILABLE", json.dumps(message))
    print(f"[OK] Disponibilité publiée pour le volontaire {volunteer_id}")

def ecouter_taches():
    pubsub.subscribe("TASK_ASSIGNMENT")
    print("En attente d'une tâche...")

    for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                print(f" Tâche reçue : {data}")
<<<<<<< HEAD
                #  Tu peux lancer ici une fonction d'exécution de la tâche
=======
                # 👉 Tu peux lancer ici une fonction d'exécution de la tâche
>>>>>>> 786acc5b158bf5aef3b8865c29bf1cf491ec0800
            except Exception as e:
                print(f" Erreur : {e}")

if __name__ == "__main__":
    machine = MachineInfo.objects.first()
    if not machine:
        print("[ERREUR] Aucune machine enregistrée.")
        exit(1)

    publier_disponibilite(machine.volunteer_id)
    ecouter_taches()



# utilisation

# python volunteer_listener.py
