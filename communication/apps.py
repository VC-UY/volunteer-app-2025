from django.apps import AppConfig




from django.apps import AppConfig
import threading
from volontaire.utils.regster_in_bd import register_in_bd
from communication.PubSub.redis import RedisPubSubManager  # Chemin vers ta classe


import os
import json
import requests
from django.utils import timezone
from volontaire.models import Task, Workflow  # adapte le chemin si besoin
from volontaire.docker_manager import DockerManager

INPUT_BASE_PATH = "input_data"
OUTPUT_BASE_PATH = "output_data"

def download_input_files(files, task_id):
    task_input_path = os.path.join(INPUT_BASE_PATH, str(task_id))
    os.makedirs(task_input_path, exist_ok=True)

    for file in files:
        filename = os.path.basename(file["url"])
        filepath = os.path.join(task_input_path, filename)
        try:
            response = requests.get(file["url"])
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
        except Exception as e:
            print(f"[ERROR] Failed to download {file['url']}: {e}")
    return task_input_path

def handle_task_assignment(message:dict):
    try:
        data = message.get("data")
        task = data.get("task")
        docker_data = data.get("docker_data")

        # 1. Récupération de la tâche depuis la base
        if task:
            workflow_info = task.get("workflow") # Supposons que les infos du workflow sont sous la clé "workflow"
            task_info = task # Le reste des infos dans "ask" sont pour la tâche

            # 2. Récupération de l'instance du workflow depuis la base de données
            try:
                workflow_instance = Workflow(
                    name=workflow_info.get("name", "Nouveau Workflow"),
                    description=workflow_info.get("description", ""),
                )
                workflow_instance.save()

                # 3. Création d'une nouvelle instance de la tâche liée à ce workflow
                task = Task(
                    task_id = task_info.get("id"),
                    workflow=workflow_instance, # Lier la tâche à l'instance du workflow
                    name=task_info.get("name"),
                    parameters=task_info.get("parameters", {}),
                    input_data=task_info.get("input_data", {}),
                    status=task_info.get("status", "pending"),
                    dependencies=task_info.get("dependencies", []),
                    execution_priority=task_info.get("execution_priority", 0),
                    estimated_execution_time=task_info.get("estimated_execution_time"),
                    input_data_size=task_info.get("input_data_size"),
                    output_data_size=task_info.get("output_data_size"),
                    docker_information=task_info.get("docker_information", {}),
                    docker_information = docker_data,
                    # N'incluez pas les champs du workflow ici, car ils sont stockés dans l'instance de Workflow
                )

                # 4. Enregistrement de la tâche dans la base de données
                task.save()

            except Exception as e: 
                print("une erreur c'est produit lors de la recuperation de la tache ")

        task_id = task.id
        image_name = docker_data.get("image")
        command = docker_data.get("command")
        input_files = docker_data.get("input_files", [])
        output_dir = os.path.join(OUTPUT_BASE_PATH, str(task_id))
        input_dir = os.path.join(INPUT_BASE_PATH, str(task_id))

        os.makedirs(output_dir, exist_ok=True)
        if input_files:
            download_input_files(input_files, task_id)

        # 2. Lancement du conteneur avec Docker
        docker_manager = DockerManager()
        container = docker_manager.run_container(
            image=image_name,
            command=command,
            volumes={
                input_dir: "/app/input",
                output_dir: "/app/output"
            },
            task_id=task_id
        )

        # 3. Mise à jour du statut
        task.status = "en_cours"
        task.start_date = timezone.now()
        task.save()

        print(f"[INFO] Tâche {task_id} lancée avec le conteneur {container.id}")

    except Task.DoesNotExist:
        print(f"[ERROR] Tâche avec id {task_id} non trouvée.")
    except Exception as e:
        print(f"[ERROR] Échec du traitement du message: {e}")



def handle_message(message):
    if not isinstance(dict, message) or not "channel" in message : 
        print("message recu pas correctement formate")
        return 
    
    channel = message.get("channel")

    if channel == "TASK_ASSIGNMENT" :
        return handle_task_assignment(message["data"])
    
    elif channel == "VOLUNTEER_REGISTRATION_RESPONSE":
        response = message['data']
        # recuperer request_id
        request_id = 'dd'
        if response['request_id']:
            register_in_bd()
        pass # Appel de la fonction de l'enregistrement

    else :
        print("canal non reconu")

    return 


class CommunicationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'communication'

    def ready(self):
        def start_redis_listener():
            manager = RedisPubSubManager(channels=["canal_1", "canal_2"])
            manager.connect()
            manager.subscribe(callback=handle_message)

        # Lancer dans un thread séparé pour ne pas bloquer Django
        threading.Thread(target=start_redis_listener, daemon=True).start()
    # creer une autre fonction qui verifi si le fichie volunteer_info.json du dossier .volunteer_app du personnel