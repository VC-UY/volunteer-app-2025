# import os
import docker
from docker.errors import NotFound, APIError
from threading import Lock

class DockerManager:
    _instance = None
    _lock = Lock()

    def __init__(self):

        # os.environ["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"
        self.client = docker.from_env()
        self.tasks = {}  # task_id: container_id

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = DockerManager()
        return cls._instance

    def pull_image(self, image_name):
        try:
            print(f"Pulling image {image_name}...")
            image = self.client.images.pull(image_name)
            print("Image pulled successfully.")
            return image
        except APIError as e:
            print(f"Error pulling image: {e}")
            return None

    def run_container(self, image_name, task_id, cpu_limit=None, mem_limit=None, **kwargs):
        try:
            # Vérifie d'abord si l'image est présente localement
            try:
                self.client.images.get(image_name)
                print(f"Using local image {image_name}")
            except docker.errors.ImageNotFound:
                print(f"Local image {image_name} not found. Attempting to pull...")
                self.client.images.pull(image_name)
                
            print(f"Running container for task {task_id}...")
            container = self.client.containers.run(
                image=image_name,
                detach=True,
                cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                mem_limit=mem_limit,
                **kwargs
            )
            self.tasks[task_id] = container.id
            print(f"Container started for task {task_id}: {container.id}")
            return container
        except APIError as e:
            print(f"Error running container for task {task_id}: {e}")
            return None

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
                    "container_id": container.id,
                    "status": container.status,
                    "image": container.image.tags,
                })
            except NotFound:
                result.append({
                    "task_id": task_id,
                    "container_id": container_id,
                    "status": "not found",
                    "image": [],
                })
        return result

    def purge_all(self):
        for task_id in list(self.tasks.keys()):
            self.remove_task(task_id)
        print("All tasks purged.")
