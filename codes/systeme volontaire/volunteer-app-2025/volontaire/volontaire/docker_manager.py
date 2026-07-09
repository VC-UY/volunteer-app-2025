import os
import sys
import docker
from docker.errors import NotFound, APIError, DockerException
from threading import Lock
import logging

logger = logging.getLogger(__name__)

class DockerManager:
    _instance = None
    _lock = Lock()

    def __init__(self):
        """
        Initialize Docker client with proper error handling.
        Skips initialization for Django management commands.
        """
        self.client = None
        self._available = False
        
        # Skip Docker initialization for management commands
        if self._is_management_command():
            logger.info("Skipping Docker initialization for management command")
            return

        # Try to initialize Docker client
        self._initialize_client()

    def _is_management_command(self):
        """Check if we're running a Django management command"""
        management_commands = [
            'makemigrations', 'migrate', 'shell', 'createsuperuser',
            'collectstatic', 'check', 'showmigrations', 'sqlmigrate'
        ]
        return (
            'manage.py' in sys.argv[0] and 
            len(sys.argv) > 1 and 
            sys.argv[1] in management_commands
        )

    def _initialize_client(self):
        """Initialize Docker client with fallback options"""
        try:
            # Method 1: Try explicit Unix socket
            logger.info("Attempting to connect to Docker via Unix socket...")
            self.client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            self.client.ping()
            self._available = True
            logger.info("✓ Docker client connected successfully via Unix socket")
            return
        except Exception as e:
            logger.warning(f"Failed to connect via Unix socket: {e}")

        try:
            # Method 2: Try from environment
            logger.info("Attempting to connect to Docker from environment...")
            self.client = docker.from_env()
            self.client.ping()
            self._available = True
            logger.info("✓ Docker client connected successfully from environment")
            return
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            logger.error("Docker operations will not be available")
            self.client = None
            self._available = False

    @classmethod
    def get_instance(cls):
        """Get singleton instance with thread safety"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = DockerManager()
        return cls._instance

    def is_available(self):
        """Check if Docker client is available and working"""
        if not self._available or self.client is None:
            return False
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def _ensure_available(self):
        """Raise exception if Docker is not available"""
        if not self.is_available():
            raise DockerException(
                "Docker client is not available. Please ensure Docker is running "
                "and you have the necessary permissions."
            )

    def pull_image(self, image_name):
        """Pull a Docker image"""
        self._ensure_available()
        try:
            print(f"Pulling image {image_name}...")
            image = self.client.images.pull(image_name)
            print("Image pulled successfully.")
            return image
        except APIError as e:
            print(f"Error pulling image: {e}")
            return None

    def run_container(self, image_name, task_id, cpu_limit=None, mem_limit=None, **kwargs):
        """Run a Docker container"""
        self._ensure_available()
        
        # Initialize tasks dict if not exists
        if not hasattr(self, 'tasks'):
            self.tasks = {}
            
        try:
            # Check if image exists locally, pull if not
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
                name=task_id,
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
        """Get container by task ID"""
        self._ensure_available()
        
        if not hasattr(self, 'tasks'):
            self.tasks = {}
            
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
        """Get status of a task"""
        if not self.is_available():
            return "docker unavailable"
        container = self.get_container_by_task(task_id)
        return container.status if container else "not found"

    def get_task_logs(self, task_id, tail=20):
        """Get logs from a task container"""
        self._ensure_available()
        container = self.get_container_by_task(task_id)
        if not container:
            return "No logs available."
        try:
            return container.logs(tail=tail).decode()
        except APIError as e:
            return f"Error getting logs: {e}"

    def pause_task(self, task_id):
        """Pause a running task"""
        self._ensure_available()
        container = self.get_container_by_task(task_id)
        if container:
            container.pause()
            print(f"Task {task_id} paused.")

    def resume_task(self, task_id):
        """Resume a paused task"""
        self._ensure_available()
        container = self.get_container_by_task(task_id)
        if container:
            container.unpause()
            print(f"Task {task_id} resumed.")

    def stop_task(self, task_id):
        """Stop a running task"""
        self._ensure_available()
        container = self.get_container_by_task(task_id)
        if container:
            container.stop()
            print(f"Task {task_id} stopped.")

    def update_task_limits(self, task_id, cpu_limit=None, mem_limit=None):
        """Update resource limits for a task"""
        self._ensure_available()
        container = self.get_container_by_task(task_id)
        if container:
            try:
                container.update(
                    cpu_quota=int(cpu_limit * 100000) if cpu_limit else None,
                    mem_limit=mem_limit
                )
                print(f"Limits updated for task {task_id}.")
                return True
            except APIError as e:
                import traceback
                traceback.print_exc()
                print(f"Error updating limits for task {task_id}: {e}")
                return False
        else:
            print(f"No container found for task {task_id}.")
            return False

    def remove_task(self, task_id):
        """Remove a task container"""
        self._ensure_available()
        
        if not hasattr(self, 'tasks'):
            self.tasks = {}
            
        container = self.get_container_by_task(task_id)
        if container:
            container.remove(force=True)
            print(f"Task {task_id} container removed.")
            self.tasks.pop(task_id, None)

    def update_limits(self, task_id, cpu_limit=None, mem_limit=None):
        """Update container limits (alias for update_task_limits)"""
        return self.update_task_limits(task_id, cpu_limit, mem_limit)

    def list_tasks(self):
        """List all managed tasks"""
        if not self.is_available():
            return []
            
        if not hasattr(self, 'tasks'):
            self.tasks = {}
            
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
        """Remove all managed task containers"""
        if not self.is_available():
            print("Docker not available - cannot purge tasks")
            return
            
        if not hasattr(self, 'tasks'):
            self.tasks = {}
            
        for task_id in list(self.tasks.keys()):
            self.remove_task(task_id)
        print("All tasks purged.")