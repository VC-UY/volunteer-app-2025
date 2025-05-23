from docker_manager import DockerManager
import threading
manager = DockerManager.get_instance()

manager.purge_all()
manager.pull_image("python:3-slim")
# Démarrer un conteneur
def run_container(task_id):
    manager.run_container("python:3-slim", task_id, command="python -c 'import time; time.sleep(10)'")

thread = threading.Thread(target=run_container, args=("task-001",))
thread.start()

thread2 = threading.Thread(target=run_container, args=("task-002",))
thread2.start()

# Attendre que le conteneur soit démarré
thread.join()
thread2.join()

# Récupérer son statut
print("manager.get_task_status('task-001'):", manager.get_task_status("task-001"))

# Voir les logs
print("manager.get_task_logs('task-001'):", manager.get_task_logs("task-001"))

# Lister les tâches
print("manager.list_tasks():", manager.list_tasks())

# Arrêter le conteneur
manager.stop_task("task-001")

# Supprimer le conteneur
manager.remove_task("task-001")

print("manager.list_tasks():", manager.list_tasks())

# Purger toutes les tâches
manager.purge_all()

print("manager.list_tasks():", manager.list_tasks())

