import docker
from docker.errors import NotFound, APIError


class DockerManager:
    def __init__(self):
        self.client = docker.from_env()

    def pull_image(self, image_name):
        try:
            print(f"Pulling image {image_name}...")
            image = self.client.images.pull(image_name)
            print("Image pulled successfully.")
            return image
        except APIError as e:
            print(f"Error pulling image: {e}")
            return None

    def run_container(self, image_name, name=None, cpu_limit=None, mem_limit=None, detach=True, **kwargs):
        try:
            print(f"Running container from image {image_name}...")
            container = self.client.containers.run(
                image=image_name,
                name=name,
                detach=detach,
                cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,  # e.g., 0.5 CPU => 50000
                mem_limit=mem_limit,
                **kwargs
            )
            print(f"Container started with ID {container.id}")
            return container
        except APIError as e:
            print(f"Error running container: {e}")
            return None

    def pause_container(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.pause()
            print("Container paused.")
        except NotFound:
            print("Container not found.")
        except APIError as e:
            print(f"Error pausing container: {e}")

    def resume_container(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.unpause()
            print("Container resumed.")
        except NotFound:
            print("Container not found.")
        except APIError as e:
            print(f"Error resuming container: {e}")

    def stop_container(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            print("Container stopped.")
        except NotFound:
            print("Container not found.")
        except APIError as e:
            print(f"Error stopping container: {e}")

    def remove_container(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
            print("Container removed.")
        except NotFound:
            print("Container not found.")
        except APIError as e:
            print(f"Error removing container: {e}")

    def set_limits(self, container_id, cpu_limit=None, mem_limit=None):
        try:
            container = self.client.containers.get(container_id)
            container.update(
                cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                mem_limit=mem_limit
            )
            print("Limits updated.")
        except NotFound:
            print("Container not found.")
        except APIError as e:
            print(f"Error updating limits: {e}")

    def purge_all(self):
        try:
            containers = self.client.containers.list(all=True)
            for container in containers:
                container.remove(force=True)
                print(f"Removed container: {container.id}")
            print("All containers purged.")
        except APIError as e:
            print(f"Error purging containers: {e}")

    def list_tasks(self):
        containers = self.client.containers.list(all=True)
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "image": c.image.tags
            } for c in containers
        ]

    def task_details(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            return {
                "id": container.id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags,
                "created": container.attrs['Created'],
                "started_at": container.attrs['State']['StartedAt'],
                "finished_at": container.attrs['State']['FinishedAt'],
                "logs": container.logs(tail=20).decode()
            }
        except NotFound:
            print("Container not found.")
            return None
        except APIError as e:
            print(f"Error getting details: {e}")
            return None


    def limit_cpu(self, container_id, cpu_quota):
            container = self.client.containers.get(container_id)
            container.update(cpu_quota=cpu_quota)
            return f"CPU limited for {container_id}."

    def limit_ram(self, container_id, mem_limit):
        container = self.client.containers.get(container_id)
        container.update(mem_limit=mem_limit)
        return f"RAM limited for {container_id}."