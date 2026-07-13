"""
Client HTTP pour le runtime vc-uyr (binaire Rust, écoute sur localhost:7070).

Remplace DockerManager comme couche d'exécution des tâches : toutes les
requêtes sont protégées par un timeout court et n'importe quelle erreur
réseau est convertie en valeur de retour "indisponible" (None/False) plutôt
que de remonter une exception, pour que le reste de l'application continue
de fonctionner si le runtime est hors ligne.
"""

import base64
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class RuntimeUnavailableError(Exception):
    """Le runtime vc-uyr ne répond pas (health check échoué)."""


class RuntimeBusyError(Exception):
    """Le runtime vc-uyr exécute déjà une tâche."""


class RuntimeClient:
    """Petit wrapper autour de l'API REST exposée par vc-uyr sur RUNTIME_URL."""

    def __init__(self):
        self.base_url = getattr(settings, 'RUNTIME_URL', 'http://localhost:7070')
        self.timeout = getattr(settings, 'RUNTIME_HEALTH_TIMEOUT', 5)

    def health(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/health", timeout=self.timeout)
            return resp.status_code == 200
        except Exception as e:
            logger.debug("Runtime vc-uyr injoignable (health): %s", e)
            return False

    def status(self) -> dict | None:
        try:
            resp = requests.get(f"{self.base_url}/api/status", timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.debug("Runtime vc-uyr injoignable (status): %s", e)
            return None

    def submit_task(self, task_id: str, bundle_bytes: bytes) -> bool:
        try:
            bundle_b64 = base64.b64encode(bundle_bytes).decode('utf-8')
            payload = {"task_id": task_id, "bundle_b64": bundle_b64}
            resp = requests.post(f"{self.base_url}/api/task", json=payload, timeout=30)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error("Echec soumission de la tâche %s au runtime: %s", task_id, e)
            return False

    def get_result(self) -> dict | None:
        try:
            resp = requests.get(f"{self.base_url}/api/result", timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ready"):
                    return data
            return None
        except Exception as e:
            logger.debug("Runtime vc-uyr injoignable (result): %s", e)
            return None

    def update_resources(self, cpu_percent: int, memory_mb: int, disk_total_mb: int) -> bool:
        try:
            payload = {
                "cpu_percent": int(cpu_percent),
                "memory_mb": int(memory_mb),
                "disk_total_mb": int(disk_total_mb),
            }
            resp = requests.post(f"{self.base_url}/api/resources", json=payload, timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error("Echec update_resources sur le runtime: %s", e)
            return False

    def pause(self) -> bool:
        try:
            resp = requests.post(f"{self.base_url}/api/control/pause", timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error("Echec pause du runtime: %s", e)
            return False

    def resume(self) -> bool:
        try:
            resp = requests.post(f"{self.base_url}/api/control/resume", timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error("Echec resume du runtime: %s", e)
            return False

    def shutdown(self) -> bool:
        try:
            resp = requests.post(f"{self.base_url}/api/control/shutdown", timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error("Echec shutdown du runtime: %s", e)
            return False

    def disk_quota(self) -> dict | None:
        try:
            resp = requests.get(f"{self.base_url}/api/disk", timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.debug("Runtime vc-uyr injoignable (disk): %s", e)
            return None

    def task_history(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/api/tasks/history", timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            logger.debug("Runtime vc-uyr injoignable (history): %s", e)
            return []
