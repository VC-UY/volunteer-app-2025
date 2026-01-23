import os
import docker
from docker.errors import NotFound, APIError, DockerException
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class DockerNotAvailableError(Exception):
    """Exception levée quand Docker n'est pas disponible."""
    pass


class DockerImageNotFoundError(Exception):
    """Exception levée quand l'image Docker n'est pas trouvée."""
    pass

class DockerManager:
    _instance = None
    _lock = Lock()

    def __init__(self):
        self.client = None
        self.tasks = {}  # task_id: container_id
        self._connected = False
        self._try_connect()
    
    def _try_connect(self):
        """Tente de se connecter à Docker sans bloquer l'application"""
        try:
            # Essayer le socket rootless d'abord
            if os.path.exists("/run/user/1000/docker.sock"):
                os.environ["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"
            
            self.client = docker.from_env()
            self._connected = True
            logger.info("Connexion Docker établie")
        except DockerException as e:
            logger.warning(f"Docker non disponible: {e}")
            self._connected = False
            self.client = None
    
    def is_connected(self):
        """Vérifie si Docker est disponible"""
        if not self._connected or self.client is None:
            self._try_connect()
        return self._connected

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = DockerManager()
        return cls._instance

    def pull_image(self, image_name):
        if not self.is_connected():
            logger.error("Docker non disponible pour pull_image")
            return None
        try:
            print(f"Pulling image {image_name}...")
            image = self.client.images.pull(image_name)
            print("Image pulled successfully.")
            return image
        except APIError as e:
            print(f"Error pulling image: {e}")
            return None

    def run_container(self, image_name, task_id, cpu_limit=None, mem_limit=None, command=None, **kwargs):
        """
        Démarre un conteneur Docker pour une tâche.

        Args:
            image_name: Nom de l'image Docker
            task_id: ID de la tâche
            cpu_limit: Limite CPU (optionnel)
            mem_limit: Limite mémoire (optionnel)
            **kwargs: Arguments supplémentaires pour Docker

        Returns:
            Container: Le conteneur démarré

        Raises:
            DockerNotAvailableError: Si Docker n'est pas disponible
            DockerImageNotFoundError: Si l'image n'est pas trouvée et ne peut pas être téléchargée
            APIError: Si une erreur Docker se produit
        """
        if not self.is_connected():
            error_msg = "Docker n'est pas disponible. Vérifiez que Docker est installé et en cours d'exécution."
            logger.error(error_msg)
            raise DockerNotAvailableError(error_msg)

        try:
            # Vérifie d'abord si l'image est présente localement
            try:
                self.client.images.get(image_name)
                logger.info(f"Utilisation de l'image locale {image_name}")
            except docker.errors.ImageNotFound:
                logger.info(f"Image locale {image_name} non trouvée. Téléchargement en cours...")
                try:
                    self.client.images.pull(image_name)
                    logger.info(f"Image {image_name} téléchargée avec succès")
                except APIError as pull_error:
                    error_msg = f"Impossible de télécharger l'image {image_name}: {pull_error}"
                    logger.error(error_msg)
                    raise DockerImageNotFoundError(error_msg)

            logger.info(f"Démarrage du conteneur pour la tâche {task_id}...")
            container = self.client.containers.run(
                image=image_name,
                detach=True,
                name=task_id,
                cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                mem_limit=mem_limit,
                command=command,
                **kwargs
            )
            self.tasks[task_id] = container.id
            logger.info(f"Conteneur démarré pour la tâche {task_id}: {container.id}")
            return container
        except (DockerNotAvailableError, DockerImageNotFoundError):
            raise  # Re-lever les exceptions personnalisées
        except APIError as e:
            error_msg = f"Erreur Docker lors du démarrage du conteneur pour la tâche {task_id}: {e}"
            logger.error(error_msg)
            raise

    def get_container_by_task(self, task_id):
        container_id = self.tasks.get(task_id)
        if not container_id:
            print(f"No container found for task {task_id}")
            return None
        try:
            return self.client.containers.get(container_id)
        except NotFound:
            print(f"Container for task {task_id} not found.")
            return None

    def get_task_status(self, task_id):
        container = self.get_container_by_task(task_id)
        return container.status if container else "not found"

    def get_task_logs(self, task_id, tail=20):
        container = self.get_container_by_task(task_id)
        if not container:
            return "No logs available."
        try:
            return container.logs(tail=tail).decode()
        except APIError as e:
            return f"Error getting logs: {e}"

    def pause_task(self, task_id):
        container = self.get_container_by_task(task_id)
        if container:
            container.pause()
            print(f"Task {task_id} paused.")

    def resume_task(self, task_id):
        container = self.get_container_by_task(task_id)
        if container:
            container.unpause()
            print(f"Task {task_id} resumed.")

    def stop_task(self, task_id):
        container = self.get_container_by_task(task_id)
        if container:
            container.stop()
            print(f"Task {task_id} stopped.")

    def update_task_limits(self, task_id, cpu_limit=None, mem_limit=None):
        container = self.get_container_by_task(task_id)
        if container:
            try:
                container.update(
                    cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                    mem_limit=mem_limit
                )
                print(f"Limits updated for task {task_id}.")
            except APIError as e:
                import traceback
                traceback.print_exc()
                print(f"Error updating limits for task {task_id}: {e}")
                return False
            return True
        else:
            print(f"No container found for task {task_id}.")
            return False

    def remove_task(self, task_id):
        container = self.get_container_by_task(task_id)
        if container:
            container.remove(force=True)
            print(f"Task {task_id} container removed.")
            self.tasks.pop(task_id, None)

    def update_limits(self, task_id, cpu_limit=None, mem_limit=None):
        container = self.get_container_by_task(task_id)
        if container:
            container.update(
                cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                mem_limit=mem_limit
            )
            print(f"Limits updated for task {task_id}.")

    def list_tasks(self):
        result = []
        for task_id, container_id in self.tasks.items():
            try:
                container = self.client.containers.get(container_id)
                result.append({
                    "task_id": task_id,
                    "name": task_id,
                    "container_id": container.id,
                    "status": container.status,
                    "image": container.image.tags,
                })
            except NotFound:
                result.append({
                    "task_id": task_id,
                    "name": task_id,
                    "container_id": container_id,
                    "status": "not found",
                    "image": [],
                })
        return result

    def purge_all(self):
        for task_id in list(self.tasks.keys()):
            self.remove_task(task_id)
        print("All tasks purged.")
