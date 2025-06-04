
import threading
import time
import docker
import http.server
import socketserver
from communication.PubSub.redis import RedisPubSubManager

def calculate_cpu_percent(stats):
    cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
    if system_delta > 0.0:
        cpu_count = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []))
        return (cpu_delta / system_delta) * cpu_count * 100.0
    return 0.0

class TaskProgressTracker:
    def __init__(self, container_id, task_id, workflow_id,
                 duration_estimate=60, redis_host='localhost',
                 redis_port=6379, output_dir=None, server_port=8001):
        self.container_id = container_id
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.duration_estimate = duration_estimate
        self.output_dir = output_dir
        self.server_port = server_port
        self.client = docker.from_env()
        # channel task_progress for both updates and final message
        self.redis = RedisPubSubManager(
            host=redis_host, port=redis_port, channels=['task_progress']
        )
        self.redis.connect()

    def start(self, interval=1):
        thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        thread.start()
        return thread

    def _run(self, interval):
        try:
            container = self.client.containers.get(self.container_id)
            start_time = time.time()

            # Monitor until container stops
            while container.status == 'running':
                stats = container.stats(stream=False)
                mem_used = stats['memory_stats']['usage']
                mem_limit = stats['memory_stats'].get('limit', mem_used)
                ram_pct = (mem_used / mem_limit) * 100 if mem_limit else 0
                cpu_pct = calculate_cpu_percent(stats)
                elapsed = time.time() - start_time
                time_pct = min(100, (elapsed / self.duration_estimate) * 100)

                progress = int((time_pct * 0.5)  + (cpu_pct * 0.3) + (ram_pct * 0.2))
                message = {
                    'task_id': self.task_id,
                    'workflow_id': self.workflow_id,
                    'status': 'running',
                    'progress': progress,
                    'elapsed_time': round(elapsed, 2),
                    'cpu_percent': round(cpu_pct, 2),
                    'ram_percent': round(ram_pct, 2)
                }
                self.redis.publish('task_progress', str(message))
                time.sleep(interval)
                container.reload()

            # Container finished:
            # 1. Launch file server if output_dir provided
            if self.output_dir:
                handler = http.server.SimpleHTTPRequestHandler
                httpd = socketserver.TCPServer(("", self.server_port), handler)
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                server_info = f"http://localhost:{self.server_port}/"
            else:
                server_info = None

            # 2. Publish final status
            exit_code = container.wait().get('StatusCode')
            final_message = {
                'task_id': self.task_id,
                'workflow_id': self.workflow_id,
                'status': 'finished',
                'progress': 100,
                'exit_code': exit_code,
                'server': server_info
            }
            self.redis.publish('task_finished', str(final_message))

        except Exception as e:
            error_msg = {
                'task_id': self.task_id,
                'workflow_id': self.workflow_id,
                'status': 'error',
                'error': str(e)
            }
            self.redis.publish('task_progress', str(error_msg))
            print(f"[ERROR] Progress tracker failed: {e}")
class DockerManager:
    def run_and_track(self, image, command, name=None,
                      duration_estimate=60, output_dir=None,
                      server_port=8001, **kwargs):
        # Lancer le conteneur en détaché
        container = self.client.containers.run(
            image, command, name=name, detach=True, **kwargs
        )
        # Démarrer le tracker avec publication de progression  fin
        tracker = TaskProgressTracker(
            container.id,
            duration_estimate=duration_estimate,
            output_dir=output_dir,
            server_port=server_port
        )
        tracker.start(interval=2)
        return container
    def run_and_track(self, image, command, task_id, workflow_id,
                      name=None, duration_estimate=60,
                      output_dir=None, server_port=8001, **kwargs):
        # Lancer le conteneur en détaché
        container = self.client.containers.run(
            image, command, name=name, detach=True, **kwargs
        )
        # Démarrer le tracker avec publication de progression  fin
        tracker = TaskProgressTracker(
            container.id,
            task_id=task_id,
            workflow_id=workflow_id,
            duration_estimate=duration_estimate,
            output_dir=output_dir,
            server_port=server_port
        )
        tracker.start(interval=2)
        return container
