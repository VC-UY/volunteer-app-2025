"""
Gestionnaires pour les tâches dans le module de communication Redis.
"""

import logging
import json
import os
import time
import uuid
from datetime import datetime
import threading

from django.utils import timezone

from .client import RedisClient
from .message import Message

logger = logging.getLogger(__name__)


def _normalize_status(status) -> str:
    return str(status or "").lower().strip()


def _is_running_status(status) -> bool:
    return _normalize_status(status) in (
        "progress", "running", "started", "in_progress"
    )


def _is_pausable_status(status) -> bool:
    return _is_running_status(status)


def _is_stoppable_status(status) -> bool:
    return _normalize_status(status) in (
        "progress", "running", "started", "in_progress", "paused", "assigned", "pending"
    )


# Import des modèles à l'intérieur des fonctions pour éviter les importations circulaires

# Répertoire pour stocker les fichiers des tâches
TASKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.volunteer', 'tasks')
os.makedirs(TASKS_DIR, exist_ok=True)

class TaskManager:
    """
    Gestionnaire des tâches pour le volontaire.
    """
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        Récupère l'instance unique du gestionnaire de tâches.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def __init__(self):
        """
        Initialise le gestionnaire de tâches.
        """
        self.redis_client = RedisClient.get_instance()
        self.volunteer_id = None
        self.current_task = None
        self.task_process = None
        self.task_thread = None
        self.heartbeat_thread = None
        self.running = False           
    
    def start(self, volunteer_id):
        """
        Démarre le gestionnaire de tâches.
        
        Args:
            volunteer_id: ID du volontaire
        """
        self.volunteer_id = str(volunteer_id)
        if self.running:
            logger.warning(
                "Gestionnaire de tâches déjà actif (volunteer_id=%s) — republication heartbeat",
                self.volunteer_id,
            )
            self._send_heartbeat()
            self._request_pending_assignments()
            return
        
        self.running = True
        
        # S'abonner aux canaux de tâches
        self.redis_client.subscribe('task/assignment', self.handle_task_assignment)
        self.redis_client.subscribe('task/cancel', self.handle_task_cancel)

        # Présence coordinateur : heartbeat immédiat puis toutes les 20s
        self._send_heartbeat()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"volunteer-heartbeat-{self.volunteer_id[:8]}",
            daemon=True,
        )
        self.heartbeat_thread.start()

        # Demander au coordinateur de renvoyer les tâches ASSIGNED non démarrées
        self._request_pending_assignments()
        
        logger.info(f"Gestionnaire de tâches démarré pour le volontaire {volunteer_id}")

    def _request_pending_assignments(self):
        """Demande au coordinateur de republier les assignations en attente."""
        try:
            from .utils import get_volunteer_auth_token
            token = get_volunteer_auth_token()
            self.redis_client.publish(
                'coordinator/assign_request',
                {
                    'volunteer_id': self.volunteer_id,
                    'action': 'republish',
                },
                str(uuid.uuid4()),
                token,
                'request',
            )
            logger.info("Demande de republication des assignations envoyée au coordinateur")
        except Exception as exc:
            logger.warning("Republication assignations impossible: %s", exc)

    def _has_active_tasks(self) -> bool:
        try:
            from django.apps import apps
            Task = apps.get_model('volontaire', 'Task')
            return Task.objects.filter(
                status__in=['pending', 'assigned', 'in_progress', 'running', 'started']
            ).exists()
        except Exception:
            return bool(self.current_task)

    def _start_next_assigned_task(self) -> bool:
        """
        Démarre une seule tâche en attente (stratégie 1 tâche à la fois).
        """
        if self.current_task is not None:
            return False
        try:
            from django.apps import apps
            Task = apps.get_model('volontaire', 'Task')
            next_task = (
                Task.objects.filter(status='assigned')
                .select_related('workflow')
                .order_by('start_date', 'id')
                .first()
            )
            if not next_task:
                return False
            logger.info("Démarrage FIFO de la tâche assignée %s", next_task.task_id)
            thread = threading.Thread(target=self._execute_task, args=(next_task,), daemon=True)
            thread.start()
            return True
        except Exception as exc:
            logger.warning("Impossible de démarrer la prochaine tâche assignée: %s", exc)
            return False

    def _send_heartbeat(self):
        """Signale au coordinateur que ce volontaire est en ligne."""
        if not self.volunteer_id:
            return
        try:
            from .utils import get_volunteer_auth_token
            from preferences_payload import (
                build_preferences_payload,
                is_available_now,
            )

            prefs = build_preferences_payload()
            busy = bool(self.current_task) or self._has_active_tasks()
            available_now = is_available_now(prefs) and not busy
            payload = {
                "volunteer_id": self.volunteer_id,
                "status": "busy" if busy else ("available" if available_now else "offline"),
                "timestamp": timezone.now().isoformat(),
                "preferences": prefs,
                "resources": {
                    "cpu_cores": prefs.get("max_cpu_cores") or prefs.get("machine_cpu_cores") or 1,
                    "memory_mb": int((prefs.get("max_ram_gb") or 1) * 1024),
                    "disk_space_mb": int((prefs.get("max_disk_gb") or 1) * 1024),
                    "gpu": False,
                },
            }
            token = get_volunteer_auth_token()
            self.redis_client.publish(
                "volunteer/heartbeat",
                payload,
                str(uuid.uuid4()),
                token,
                "request",
            )
            self.redis_client.publish(
                "coord/heartbeat",
                payload,
                str(uuid.uuid4()),
                token,
                "request",
            )
            logger.info(
                "Heartbeat envoyé (volunteer_id=%s, status=%s)",
                self.volunteer_id,
                payload["status"],
            )
        except Exception as exc:
            logger.warning("Échec heartbeat volontaire: %s", exc)

    def _heartbeat_loop(self):
        while self.running:
            time.sleep(20)
            if self.running:
                self._send_heartbeat()
    
    def stop(self):
        """
        Arrête le gestionnaire de tâches.
        """
        self.running = False
        
        # Arrêter la tâche en cours si elle existe
        if self.task_process:
            try:
                self.task_process.terminate()
            except:
                pass

        if self.volunteer_id:
            try:
                from .utils import get_volunteer_auth_token
                self.redis_client.publish(
                    "volunteer/disconnect",
                    {
                        "volunteer_id": self.volunteer_id,
                        "timestamp": timezone.now().isoformat(),
                    },
                    str(uuid.uuid4()),
                    get_volunteer_auth_token(),
                    "request",
                )
            except Exception:
                pass
        
        # Se désabonner des canaux
        self.redis_client.unsubscribe('task/assignment')
        self.redis_client.unsubscribe('task/cancel')
        
        logger.info("Gestionnaire de tâches arrêté")

    def handle_task_assignment(self, channel: str, message: Message):
        """
        Gère l'assignation d'une tâche.
        
        Args:
            channel: Canal sur lequel le message a été reçu
            message: Message reçu
        """
        logger.info(f"Message d'assignation de tâche reçu: {message.to_dict()}")
            
        # Récupérer les données du message
        data = message.data
        
        # Vérifier si le message contient des assignations pour ce volontaire
        assignments = data.get('assignments', {})
        workflow_id = data.get('workflow_id')
        
        if not assignments:
            logger.warning(f"Aucune assignation de tâche dans le message: {message.to_dict()}")
            return
        
        # Vérifier si des tâches sont assignées à ce volontaire
        volunteer_tasks = assignments.get(self.volunteer_id, [])
        
        if not volunteer_tasks:
            logger.info(f"Aucune tâche assignée au volontaire {self.volunteer_id} dans ce message")
            return
        
        logger.info(f"{len(volunteer_tasks)} tâches assignées au volontaire {self.volunteer_id}")

        from django.apps import apps
        Workflow = apps.get_model('volontaire', 'Workflow')
        wf_name = (
            data.get("workflow_name")
            or (volunteer_tasks[0].get("workflow_name") if volunteer_tasks else None)
            or data.get("workflow_type")
            or f"Workflow {str(workflow_id)[:8]}"
        )
        wf_desc = data.get("workflow_description") or ""
        wf_type = data.get("workflow_type") or (
            volunteer_tasks[0].get("workflow_type") if volunteer_tasks else ""
        )
        if not wf_desc and volunteer_tasks:
            wf_desc = volunteer_tasks[0].get("description") or ""
        if wf_type and wf_desc and not wf_desc.startswith("["):
            wf_desc = f"[{wf_type}] {wf_desc}"
        elif wf_type and not wf_desc:
            wf_desc = f"Type: {wf_type}"

        workflow = Workflow.objects.filter(workflow_id=workflow_id).first()
        if not workflow:
            workflow = Workflow.objects.create(
                workflow_id=workflow_id,
                name=wf_name,
                description=wf_desc,
            )
        else:
            changed = False
            if wf_name and workflow.name in ("Workflow", "", None):
                workflow.name = wf_name
                changed = True
            if wf_desc and workflow.description in ("Workflow", "", None):
                workflow.description = wf_desc
                changed = True
            if changed:
                workflow.save()
        
        # Traiter chaque tâche assignée à ce volontaire
        for task_data in volunteer_tasks:
            task_id = task_data.get('task_id')
            
            # Vérifier si la tâche existe déjà
            from django.apps import apps
            Task = apps.get_model('volontaire', 'Task')
            existing_task = Task.objects.filter(task_id=task_id).first()
            if existing_task:
                st = (existing_task.status or '').lower()
                if st in ('completed', 'complete', 'in_progress', 'running', 'started'):
                    logger.info(
                        "Tâche %s déjà %s — pas de réexécution",
                        task_id,
                        existing_task.status,
                    )
                    continue
                # Réassignation : mettre à jour et relancer
                logger.info(
                    "Tâche %s déjà reçue (statut %s) — mise à jour et reprise",
                    task_id,
                    existing_task.status,
                )
                existing_task.name = task_data.get('name', existing_task.name)
                existing_task.workflow = workflow
                params = task_data.get('parameters', existing_task.parameters or {})
                if isinstance(params, list):
                    params = {}
                params['command'] = task_data.get('command', params.get('command', ''))
                params['description'] = task_data.get('description', params.get('description', ''))
                params['workflow_type'] = wf_type or params.get('workflow_type', '')
                existing_task.parameters = params
                existing_task.status = 'assigned'
                existing_task.input_data = task_data.get('input_data', existing_task.input_data or {})
                existing_task.estimated_execution_time = task_data.get(
                    'estimated_execution_time', existing_task.estimated_execution_time or 0
                )
                existing_task.input_data_size = task_data.get(
                    'input_data_size', existing_task.input_data_size or 0
                )
                existing_task.docker_information = task_data.get(
                    'docker_information', existing_task.docker_information or {}
                )
                existing_task.end_date = None
                existing_task.save()
                task = existing_task
            else:
                # Créer une nouvelle tâche
                params = task_data.get('parameters', {}) or {}
                if isinstance(params, list):
                    params = {}
                params['command'] = task_data.get('command', params.get('command', ''))
                params['description'] = task_data.get('description', params.get('description', ''))
                params['workflow_type'] = wf_type or params.get('workflow_type', '')
                task = Task(
                    task_id=str(task_id),
                    name=task_data.get('name', 'Tâche sans nom'),
                    workflow=workflow,
                    parameters=params,
                    status='assigned',
                    input_data=task_data.get('input_data', {}),
                    estimated_execution_time=task_data.get('estimated_execution_time', 0),
                    input_data_size=task_data.get('input_data_size', 0),
                    docker_information=task_data.get('docker_information', {}),
                )
                task.save()



            # Notifier les clients WebSocket
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_add_task",
                    "data": {
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                        "estimated_execution_time": task.estimated_execution_time,
                    }
                }
            )

            logger.info(f"Envoi de l'événement add_task pour la tâche {task.task_id}")




            
            # Créer un événement de progression pour l'assignation
            from django.apps import apps
            TaskProgress = apps.get_model('volontaire', 'TaskProgress')
            TaskProgress.objects.create(
                task=task,
                progress_type='start',
                percentage=0,
                message="Tâche assignée au volontaire",
                details={
                    'volunteer_id': self.volunteer_id,
                    'channel': channel
                }
            )
            
            # Envoyer une réponse d'acceptation
            self._accept_task(task)

            # Notifier le frontend de l'acceptation
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "accepted",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                        "estimated_execution_time": task.estimated_execution_time,
                    }
                }
            )
            
            # Télécharger les fichiers d'entrée si nécessaires
            if task.input_data and 'files' in task.input_data:
                self._download_input_files(task)
            
            # Exécution séquentielle: une seule tâche active à la fois.
            if self.current_task is None:
                thread = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
                thread.start()
            else:
                logger.info(
                    "Tâche %s mise en attente locale (tâche active: %s)",
                    task.task_id,
                    getattr(self.current_task, 'task_id', 'unknown'),
                )
        
    
    def handle_task_cancel(self, channel: str, message: Message):
        """
        Gère l'annulation d'une tâche.
        
        Args:
            channel: Canal sur lequel le message a été reçu
            message: Message reçu
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        data = message.data
        task_id = data.get('task_id')
        
        # Vérifier si la tâche existe
        task = Task.objects.filter(task_id=task_id).first()
        if not task:
            logger.warning(f"Demande d'annulation pour une tâche inconnue: {task_id}")
            return
        
        # Vérifier si la tâche est en cours d'exécution
        if task.status in ['in_progress', 'pending', 'started']:
            # Arrêter le processus
            if self.task_process and self.current_task and self.current_task.id == task.id:
                try:
                    self.task_process.terminate()
                    logger.info(f"Tâche {task_id} arrêtée")
                except:
                    logger.error(f"Erreur lors de l'arrêt de la tâche {task_id}")
        
        # Marquer la tâche comme annulée
        task.status = "cancelled"
        task.end_date = timezone.now()
        task.save()
        
        # Notifier le frontend de l'annulation
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {
                "type": "send_task_update",
                "data": {
                    "event": "cancelled",
                    "task_id": task.task_id,
                    "name": task.name,
                    "status": task.status,
                }
            }
        )
        
        # Créer un événement de progression pour l'annulation
        TaskProgress.objects.create(
            task=task,
            progress_type='cancel',
            percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage if task.progress_events.exists() else 0,
            message="Tâche annulée",
            details={
                'reason': data.get('reason', 'Annulée par le manager'),
                'cancelled_by': data.get('cancelled_by', 'manager')
            }
        )
        
        # Envoyer une confirmation d'annulation
        from redis_communication.utils import get_volunteer_auth_token
        self.redis_client.publish('task/status', {
                'task_id': task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'Cancel',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
        )
        
        logger.info(f"Tâche {task_id} annulée")
    
    def _accept_task(self, task):
        """
        Accepte une tâche et envoie une confirmation au manager.
        
        Args:
            task: Tâche à accepter
        
        Returns:
            Task: La tâche acceptée
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Mettre à jour le statut de la tâche
        task.status = 'progress'
        task.start_date = timezone.now()
        task.save()
        
        # Notifier le frontend de l'acceptation
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {
                "type": "send_task_update",
                "data": {
                    "event": "accepted",
                    "task_id": task.task_id,
                    "name": task.name,
                    "status": task.status,
                }
            }
        )
        
        # Créer un événement de progression pour l'acceptation
        TaskProgress.objects.create(
            task=task,
            progress_type='progress',
            percentage=2,
            message="Tâche acceptée par le volontaire",
            details={
                'volunteer_id': self.volunteer_id,
                'accepted_at': timezone.now().isoformat()
            }
        )
        
        # Envoyer une confirmation d'acceptation
        from redis_communication.utils import get_volunteer_auth_token
        auth_token = get_volunteer_auth_token()
        self.redis_client.publish('task/accept', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            auth_token,
            'request'
        )
        
        logger.info(f"Tâche {task.task_id} acceptée")
        return task
    
    def pause_task(self, task_id):
        """
        Met en pause une tâche en cours d'exécution.
        
        Args:
            task_id: ID de la tâche à mettre en pause
        
        Returns:
            bool: True si la tâche a été mise en pause avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.docker_manager import DockerManager
        
        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)
            
            # Vérifier que la tâche est en cours d'exécution
            if not _is_pausable_status(task.status):
                logger.warning(
                    "Impossible de mettre en pause la tâche %s (statut=%s)",
                    task_id,
                    task.status,
                )
                return False
            
            # Mettre à jour le statut de la tâche
            task.status = 'paused'
            task.save()
            
            # Notifier le frontend de la pause
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "paused",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                    }
                }
            )
            
            # Créer un événement de progression pour la pause
            TaskProgress.objects.create(
                task=task,
                progress_type='progress',
                percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage,
                message="Tâche mise en pause"
            )
            
            # Mettre en pause le conteneur Docker
            docker_manager = DockerManager.get_instance()
            docker_manager.pause_task(task_id)
            from redis_communication.utils import get_volunteer_auth_token
            
            # Envoyer une notification de pause
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'paused',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token(),
            'request')
            
            logger.info(f"Tâche {task_id} mise en pause")
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la mise en pause de la tâche {task_id}: {e}")
            return False
    
    def resume_task(self, task_id):
        """
        Reprend l'exécution d'une tâche en pause.
        
        Args:
            task_id: ID de la tâche à reprendre
        
        Returns:
            bool: True si la tâche a été reprise avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.docker_manager import DockerManager
        
        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)
            
            # Reprendre une tâche en pause ou démarrer une tâche assignée/en attente
            st = _normalize_status(task.status)
            if st in ('pending', 'queued', 'assigned', 'created', 'accepted'):
                if self.current_task is not None:
                    logger.warning("Une autre tâche est déjà en cours (%s)", self.current_task)
                    return False
                logger.info("Démarrage manuel de la tâche %s", task_id)
                thread = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
                thread.start()
                return True

            if st != 'paused':
                logger.warning(
                    "Impossible de reprendre la tâche %s (statut=%s)",
                    task_id,
                    task.status,
                )
                return False
            
            # Mettre à jour le statut de la tâche
            task.status = 'running'
            task.save()
            
            # Notifier le frontend de la reprise
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "resumed",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                    }
                }
            )
            
            # Créer un événement de progression pour la reprise
            TaskProgress.objects.create(
                task=task,
                progress_type='progress',
                percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage,
                message="Tâche reprise"
            )
            
            # Reprendre le conteneur Docker
            docker_manager = DockerManager.get_instance()
            docker_manager.resume_task(task_id)
            from redis_communication.utils import get_volunteer_auth_token
            
            # Envoyer une notification de reprise
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'progress',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token(),
            'request')
            
            logger.info(f"Tâche {task_id} reprise")
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la reprise de la tâche {task_id}: {e}")
            return False
    
    def stop_task(self, task_id):
        """
        Arrête l'exécution d'une tâche.
        
        Args:
            task_id: ID de la tâche à arrêter
        
        Returns:
            bool: True si la tâche a été arrêtée avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.docker_manager import DockerManager
        
        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)
            
            # Vérifier que la tâche peut être arrêtée
            if not _is_stoppable_status(task.status):
                logger.warning(
                    "Impossible d'arrêter la tâche %s (statut=%s)",
                    task_id,
                    task.status,
                )
                return False

            prev_status = task.status
            
            # Mettre à jour le statut de la tâche
            task.status = 'stopped'
            task.end_date = timezone.now()
            task.save()
            
            # Notifier le frontend de l'arrêt
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "stopped",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                    }
                }
            )
            
            # Créer un événement de progression pour l'arrêt
            TaskProgress.objects.create(
                task=task,
                progress_type='progress',
                percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage,
                message="Tâche arrêtée"
            )
            
            # Arrêter le conteneur Docker si actif
            docker_manager = DockerManager.get_instance()
            if _is_running_status(prev_status) or _normalize_status(prev_status) == 'paused':
                docker_manager.stop_task(task_id)

            if self.current_task and str(getattr(self.current_task, 'task_id', '')) == str(task_id):
                self.current_task = None
                self.task_process = None
                self._start_next_assigned_task()
            
            # Envoyer une notification d'arrêt
            from redis_communication.utils import get_volunteer_auth_token
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'stopped',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token(),
            'request')
            
            logger.info(f"Tâche {task_id} arrêtée")
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de la tâche {task_id}: {e}")
            return False
        


    def update_limits(self, task_id, cpu_limit=None, memory_limit=None):
        """        Met à jour les limites de ressources d'une tâche en cours d'exécution.
        Args:
            task_id: ID de la tâche à mettre à jour
            cpu_limit: Nouvelle limite CPU (float)
            memory_limit: Nouvelle limite mémoire (str, ex: '512m', '1g')
        Returns:
            bool: True si les limites ont été mises à jour avec succès, False sinon
        """

        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        from volontaire.docker_manager import DockerManager
        
        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)
            
            # Vérifier que la tâche est en cours d'exécution
            if task.status not in ['progress', 'paused']:
                logger.warning(f"Impossible de mettre à jour les limites de la tâche {task_id} car elle n'est pas en cours d'exécution ou en pause")
                return False
            
            # Mettre à jour les limites de ressources
            docker_manager = DockerManager.get_instance()
            success = docker_manager.update_task_limits(task_id, cpu_limit, memory_limit)
            

            if not success:
                logger.warning(f"Échec de la mise à jour des limites pour la tâche {task_id}")
                return False
            
            # Mettre à jour les informations Docker de la tâche
            if cpu_limit is not None:
                task.docker_information['cpu_limit'] = cpu_limit
            if memory_limit is not None:
                task.docker_information['memory_limit'] = memory_limit
            task.save()
            
            # Notifier le frontend de la mise à jour des limites
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "limits_updated",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                        "cpu_limit": cpu_limit,
                        "memory_limit": memory_limit,
                    }
                }
            )
            
            logger.info(f"Limites mises à jour pour la tâche {task_id}: CPU={cpu_limit}, Mémoire={memory_limit}")

            # Créer un événement de progression pour la mise à jour des limites
            from django.apps import apps
            TaskProgress = apps.get_model('volontaire', 'TaskProgress')
            TaskProgress.objects.create(
                task_id=task_id,
                progress_type='update_limits',
                percentage=100,
                message="Limites mises à jour"
            )

            # Envoyer une pubsub de mise à jour des limites
            from redis_communication.utils import get_volunteer_auth_token
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'limits_updated',
                'timestamp': datetime.now().isoformat(),
                'cpu_limit': cpu_limit,
                'memory_limit': memory_limit
            }, str(uuid.uuid4()), get_volunteer_auth_token(), 'request')
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des limites de la tâche {task_id}: {e}")
            return False
    
    def complete_task(self, task_id):
        """
        Marque une tâche comme terminée, pousse les sorties vers le manager,
        puis notifie la completion (fallback serveur de fichiers local).
        
        Args:
            task_id: ID de la tâche terminée
            
        Returns:
            bool: True si la tâche a été marquée comme terminée avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        from volontaire.docker_manager import DockerManager
        from redis_communication.file_server import start_task_file_server
        import os
        
        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)
            
            
            # Arrêter le conteneur Docker si nécessaire
            docker_manager = DockerManager.get_instance()
            docker_manager.stop_task(task_id)
            
            # Déterminer le chemin des fichiers de sortie
            output_dir = os.path.join(TASKS_DIR, str(task.task_id), 'output')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            output_files = [
                f for f in os.listdir(output_dir)
                if os.path.isfile(os.path.join(output_dir, f))
            ]

            # Preferer l'upload HTTP vers le manager (fonctionne derriere NAT / Docker)
            uploaded = False
            upload_url = None
            if isinstance(task.input_data, dict):
                upload_url = task.input_data.get('result_upload_url')
            if upload_url and output_files:
                try:
                    import requests
                    files_payload = []
                    opened = []
                    for name in output_files:
                        handle = open(os.path.join(output_dir, name), 'rb')
                        opened.append(handle)
                        files_payload.append(('files', (name, handle)))
                    response = requests.post(upload_url, files=files_payload, timeout=120)
                    for handle in opened:
                        handle.close()
                    if response.status_code < 300:
                        uploaded = True
                        logger.info(
                            "Sorties de la tache %s poussees vers %s (%s)",
                            task_id,
                            upload_url,
                            response.status_code,
                        )
                    else:
                        logger.error(
                            "Echec upload sorties tache %s: HTTP %s %s",
                            task_id,
                            response.status_code,
                            response.text[:300],
                        )
                except Exception as upload_error:
                    logger.error("Erreur upload sorties tache %s: %s", task_id, upload_error)

            file_server_info = {
                'uploaded': uploaded,
                'output_files': output_files,
            }
            if not uploaded:
                # Fallback: serveur de fichiers local (LAN uniquement)
                port = start_task_file_server(task_id, output_dir)
                from redis_communication.utils import get_local_ip
                file_server_info.update({
                    'host': get_local_ip(),
                    'port': port,
                    'path': '/files/',
                })
            
            # Envoyer une notification de complétion avec les informations du serveur de fichiers
            from redis_communication.utils import get_volunteer_auth_token
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'completed',
                'timestamp': datetime.now().isoformat(),
                'file_server': file_server_info,
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token(),
            'request')
            
            # Notifier le frontend de la complétion
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "completed",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                    }
                }
            )
            
            # S'abonner au canal task/terminate pour recevoir la notification de fin de tâche
            self.redis_client.subscribe('task/terminate', self._handle_task_terminate)
            
            logger.info(f"Tâche {task_id} terminée et serveur de fichiers démarré sur le port {port}")
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la complétion de la tâche {task_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _handle_task_terminate(self, channel, message):
        """
        Gère la notification de fin de tâche envoyée par le manager.
        
        Args:
            channel: Canal de la notification
            message: Message reçu
        """
        try:
            data = message.data
            task_id = data.get('task_id')
            
            if not task_id:
                logger.error("Message de fin de tâche sans ID de tâche")
                return
            
            logger.info(f"Notification de fin de tâche reçue pour la tâche {task_id}")
            
            # Arrêter le serveur de fichiers
            from redis_communication.file_server import stop_task_file_server
            stop_task_file_server(task_id)
            
            # Nettoyer les fichiers si nécessaire
            import shutil
            import os
            output_dir = os.path.join(os.getcwd(), 'task_outputs', task_id)
            if os.path.exists(output_dir) and data.get('clean_files', False):
                shutil.rmtree(output_dir)
                logger.info(f"Fichiers de sortie de la tâche {task_id} supprimés")
            
            # Mettre à jour le statut de la tâche
            from django.apps import apps
            Task = apps.get_model('volontaire', 'Task')
            try:
                task = Task.objects.get(task_id=task_id)
                task.status = 'terminated'
                task.save()

                # Notifier le frontend de la fin de la tache

                logger.info(f"Tâche {task_id} marquée comme terminée")
            except Task.DoesNotExist:
                logger.error(f"Tâche {task_id} introuvable")
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la notification de fin de tâche: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _execute_task(self, task):
        """
        Exécute une tâche dans un thread séparé en utilisant Docker.
        
        Args:
            task: Tâche à exécuter
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        import traceback
        from volontaire.docker_manager import DockerManager
        
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Marquer la tâche comme démarrée
        task.status = 'Running'
        task.save()
        self.current_task = task
        
        # Notifier le frontend du démarrage
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {
                "type": "send_task_update",
                "data": {
                    "event": "started",
                    "task_id": task.task_id,
                    "name": task.name,
                    "status": task.status,
                }
            }
        )
        
        # Créer un événement de progression pour le démarrage
        TaskProgress.objects.create(
            task=task,
            progress_type='progress',
            percentage=2,
            message="Exécution de la tâche démarrée"
        )
        
        # Envoyer une notification de démarrage
        self._send_task_status_update(task)
        
        try:
            # Récupérer l'instance unique de DockerManager
            docker_manager = DockerManager.get_instance()
            
            # Récupérer les informations Docker
            docker_info = task.docker_information or {}
            image_name = (
                docker_info.get("image_name")
                or docker_info.get("name")
                or docker_info.get("image")
            )
            tag = docker_info.get("tag", "latest")
            if image_name and ":" not in image_name:
                image_name = f"{image_name}:{tag}"

            if not image_name:
                raise ValueError("Nom d'image Docker manquant dans les informations de la tâche")

            # Définir les limites de ressources
            cpu_limit = docker_info.get("cpu_limit", 1.0)  # Par défaut, 1 CPU
            mem_limit = docker_info.get("memory_limit", "1g")  # Par défaut, 1GB

            import os
            from pathlib import Path

            # Préparer les volumes pour monter les fichiers d'entrée/sortie
            volumes = {}
            if hasattr(task, 'local_input_path') and task.local_input_path:
                # Monter le dossier parent du fichier d'entree pour exposer data.pkl / scenario.xml
                input_path = task.local_input_path
                if os.path.isfile(input_path):
                    input_path = os.path.dirname(input_path)
                volumes[input_path] = {'bind': '/input', 'mode': 'ro'}

            # Créer un répertoire de sortie
            output_dir = Path(f"{TASKS_DIR}/{task.task_id}/output")
            output_dir.mkdir(parents=True, exist_ok=True)
            volumes[str(output_dir)] = {'bind': '/output', 'mode': 'rw'}

            # Démarrer le conteneur Docker
            logger.error(f"Démarrage du conteneur Docker pour la tâche {task.task_id} avec l'image {image_name}")
            container = docker_manager.run_container(
                image_name=image_name,
                task_id=task.task_id,
                cpu_limit=cpu_limit,
                mem_limit=mem_limit,
                volumes=volumes,
            )
            
            if not container:
                raise Exception(f"Impossible de démarrer le conteneur Docker pour la tâche {task.task_id}")
            
            # Démarrer le monitoring de progression dans un thread séparé
            import threading
            monitor_thread = threading.Thread(target=self._monitor_task_progress, args=(task,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Attendre que le conteneur soit terminé
            import time
            container = docker_manager.get_container_by_task(task.task_id)
            while container and container.status in ['created', 'running']:
                time.sleep(5)
                container = docker_manager.get_container_by_task(task.task_id)
            
            if not container:
                raise Exception(f"Conteneur Docker perdu pour la tâche {task.task_id}")
            
            # Récupérer les logs
            logs = container.logs().decode('utf-8', errors='replace')
            stdout = logs
            stderr = ""
            
            # Vérifier le code de retour
            exit_code = container.attrs.get('State', {}).get('ExitCode', -1)
            
            if exit_code == 0:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                        "task_updates",
                        {
                            "type": "send_task_progress",
                            "data": {
                                "event": "progress",
                                "task_id": task.task_id,
                                "name": task.name,
                                "status": task.status,
                                "progress": 100,
                            }
                        }
                    )
                # Tâche réussie
                result = {
                    'stdout': stdout[-1000:],  # Limiter la taille de la sortie
                    'return_code': 0
                }
                
                # Collecter les fichiers de sortie
                output_files = self._collect_output_files(task)
                
                # Marquer la tâche comme terminée
                task.status = 'completed'
                task.end_date = timezone.now()
                task.results = result
                task.output_data = {'files': output_files}
                task.actual_execution_time = (task.end_date - task.start_date).total_seconds() if task.start_date else 0
                task.save()
                
                # Notifier le frontend de la complétion
                
                async_to_sync(channel_layer.group_send)(
                    "task_updates",
                    {
                        "type": "send_task_update",
                        "data": {
                            "event": "completed",
                            "task_id": task.task_id,
                            "name": task.name,
                            "status": task.status,
                        }
                    }
                )
                
                # Créer un événement de progression pour la complétion
                TaskProgress.objects.create(
                    task=task,
                    progress_type='complete',
                    percentage=100,
                    message="Tâche terminée avec succès"
                )

                # Lancer le server d'ecoute pour les fichiers de sortie
                self.complete_task(task.task_id)
                
                
                
                logger.info(f"Tâche {task.task_id} terminée avec succès")
            else:
                # Tâche échouée
                error = f"Code de retour: {exit_code}\nStderr: {stderr}\nStdout: {stdout[-1000:]}"
                
                task.status = 'error'
                task.end_date = timezone.now()
                task.error_message = error
                task.error_code = str(exit_code)
                task.save()
                
                # Notifier le frontend de l'échec
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "task_updates",
                    {
                        "type": "send_task_update",
                        "data": {
                            "event": "error",
                            "task_id": task.task_id,
                            "name": task.name,
                            "status": task.status,
                            "error_message": error,
                        }
                    }
                )
                
                # Créer un événement de progression pour l'erreur
                
                
                # Envoyer une notification d'échec
                self._send_task_failure(task, error)
                
                logger.error(f"Tâche {task.task_id} échouée: {error}")
        except Exception as e:
            # Erreur lors de l'exécution
            error = f"Erreur lors de l'exécution: {str(e)}"
            
            task.status = 'failed'
            task.end_date = timezone.now()
            task.error_message = error
            task.save()
            
            # Notifier le frontend de l'échec
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "event": "error",
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                        "error_message": error,
                    }
                }
            )
            
            # Envoyer une notification d'échec
            self._send_task_failure(task, error)
            
            logger.error(f"Erreur lors de l'exécution de la tâche {task.task_id}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self.current_task = None
            self.task_process = None
            self._start_next_assigned_task()
    
    def _monitor_task_progress(self, task):
        """
        Surveille la progression d'une tâche et envoie des mises à jour périodiques.
        Cette fonction est conçue pour être exécutée dans un thread séparé.
        
        Args:
            task: Tâche à surveiller
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Attendre un peu pour laisser le conteneur démarrer
        time.sleep(2)
        
        start_time = time.time()
        last_progress_value = 2  # Déjà à 2% après le démarrage
    
        from volontaire.docker_manager import DockerManager
        docker_manager = DockerManager.get_instance()
        
        logger.info(f"Démarrage du monitoring de progression pour la tâche {task.task_id}")
        
        # Boucle de surveillance de la progression
        while True:
            try:
                # Récupérer l'état actuel du conteneur
                container = docker_manager.get_container_by_task(task.task_id)
                
                # Vérifier si le conteneur existe et s'il est toujours en cours d'exécution
                if not container:
                    logger.info(f"Monitoring terminé pour la tâche {task.task_id}: conteneur non trouvé")
                    break
                    
                if container.status not in ['created', 'running']:
                    logger.info(f"Monitoring terminé pour la tâche {task.task_id}: conteneur {container.status}")
                    break
                
                # Calculer la progression basée sur le temps écoulé et le temps estimé
                elapsed_time = time.time() - start_time
                if task.estimated_execution_time and task.estimated_execution_time > 0:
                    progress = round(min(98.0, (elapsed_time / task.estimated_execution_time) * 100.0), 2)
                else:
                    # Si pas de temps estimé, incrémenter progressivement jusqu'à 95%
                    progress = min(98.0, last_progress_value + 2.0)  # Augmenter de 2% à chaque fois
                
                # Mettre à jour la progression seulement si elle a changé significativement
                if progress - last_progress_value >= 2.0 and progress < 100:  # Mise à jour tous les 2%
                    # Créer un événement de progression
                    TaskProgress.objects.create(
                        task=task,
                        progress_type='progress',
                        percentage=progress,
                        message=f"Progression: {int(progress)}%",
                        details={
                            'elapsed_time': elapsed_time,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    last_progress_value = progress
                    
                    # Notifier le frontend de la progression
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        "task_updates",
                        {
                            "type": "send_task_progress",
                            "data": {
                                "event": "progress",
                                "task_id": task.task_id,
                                "name": task.name,
                                "status": task.status,
                                "progress": progress,
                            }
                        }
                    )
                    
                    # Envoyer la progression au manager
                    self._send_task_progress(task, progress)
                    logger.info(f"Progression de la tâche {task.name}: {int(progress)}%")
                
                # Vérifier le statut de la tâche dans la base de données
                try:
                    Task = apps.get_model('volontaire', 'Task')
                    updated_task = Task.objects.get(task_id=task.task_id)
                    if updated_task.status not in ['Running', 'progress']:
                        logger.info(f"Monitoring arrêté pour la tâche {task.name}: statut {updated_task.status}")
                        break
                except Exception as e:
                    logger.error(f"Erreur lors de la vérification du statut de la tâche: {e}")
            except Exception as e:
                logger.error(f"Erreur dans le monitoring de la tâche {task.task_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # Attendre avant la prochaine vérification
            time.sleep(3.0)
    
    def _download_input_files(self, task):
        """
        Télécharge les fichiers d'entrée pour une tâche.
        
        Args:
            task: Tâche pour laquelle télécharger les fichiers
        
        Returns:
            bool: True si tous les fichiers ont été téléchargés avec succès, False sinon
        """
        
        import requests
        from pathlib import Path
        
        logger.info(f"Téléchargement des fichiers d'entrée pour la tâche {task.task_id}")
        
        # Vérifier si les informations du serveur de fichiers sont disponibles
        if not task.input_data or 'files' not in task.input_data or 'file_server' not in task.input_data:
            logger.warning(f"Aucune information de fichier d'entrée pour la tâche {task.task_id}")
            return False
        
        # Récupérer les informations du serveur de fichiers
        file_server = task.input_data.get('file_server', {})
        base_url = file_server.get('base_url')
        
        if not base_url:
            logger.error(f"URL du serveur de fichiers manquante pour la tâche {task.task_id}")
            return False
        
        # Récupérer la liste des fichiers à télécharger
        files = task.input_data.get('files', [])
        
        if not files:
            logger.warning(f"Aucun fichier à télécharger pour la tâche {task.task_id}")
            return False
        
        # Créer le répertoire de travail pour la tâche
        task_dir = Path(f"{TASKS_DIR}/{task.task_id}")
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # Créer le répertoire d'entrée
        input_dir = task_dir / "input"
        input_dir.mkdir(exist_ok=True)
        
        # Mettre à jour le statut de la tâche
        task.status = 'downloading'
        task.save()

        # Notifier le frontend du téléchargement
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {
                "type": "send_task_update",
                "data": {
                    "event": "downloading",
                    "task_id": task.task_id,
                    "name": task.name,
                    "status": task.status,
                }
            }
        )
        
        # Télécharger chaque fichier
        downloaded_files = []
        total_files = len(files)
        
        for i, file_info in enumerate(files):
            # Gérer les deux formats possibles : chaîne ou dictionnaire
            if isinstance(file_info, dict):
                file_path = file_info.get('path')
            else:
                # Si c'est une chaîne, utiliser directement
                file_path = file_info
                
            file_url = f"{base_url}/{file_path}"
            
            # Déterminer le chemin local
            local_path = input_dir / Path(file_path).name
            
            try:
                # Télécharger le fichier
                logger.info(f"Téléchargement du fichier {file_url} vers {local_path}")
                response = requests.get(file_url, stream=True)
                response.raise_for_status()
                
                # Écrire le fichier sur le disque
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                downloaded_files.append({
                    'remote_path': file_path,
                    'local_path': str(local_path)
                })
                
               
                
            except Exception as e:
                logger.error(f"Erreur lors du téléchargement du fichier {file_url}: {e}")
                
                # Créer un événement d'erreur
                from django.apps import apps
                TaskProgress = apps.get_model('volontaire', 'TaskProgress')
                # Enregistrer l'erreur dans la base de données
                TaskProgress.objects.create(
                    task=task,
                    progress_type='error',
                    percentage=0,
                    message=f"Erreur lors du téléchargement du fichier {file_path}",
                    details={'error': str(e)}
                )
        
        # Mettre à jour le statut de la tâche
        if len(downloaded_files) == total_files:
            # Tous les fichiers ont été téléchargés avec succès
            task.status = 'ready'
            task.local_input_path = str(input_dir)
            task.save()
            
            logger.info(f"Téléchargement des fichiers d'entrée terminé pour la tâche {task.task_id}")
            return True
        else:
            # Certains fichiers n'ont pas pu être téléchargés
            task.status = 'error'
            task.save()
            
            # Créer un événement d'erreur
            from django.apps import apps
            TaskProgress = apps.get_model('volontaire', 'TaskProgress')
            TaskProgress.objects.create(
                task=task,
                progress_type='error',
                percentage=0,
                message=f"Téléchargement incomplet: {len(downloaded_files)}/{total_files} fichiers téléchargés",
                details={'downloaded_files': downloaded_files}
            )
            
            logger.error(f"Téléchargement incomplet pour la tâche {task.task_id}: {len(downloaded_files)}/{total_files} fichiers téléchargés")
            return False
    
    def _collect_output_files(self, task):
        """
        Collecte les fichiers de sortie d'une tâche.
        
        Args:
            task: Tâche pour laquelle collecter les fichiers
            
        Returns:
            list: Liste des noms de fichiers de sortie
        """
        output_dir = os.path.join(TASKS_DIR, str(task.task_id), 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # Lister tous les fichiers dans le répertoire de sortie
        output_files = []
        for filename in os.listdir(output_dir):
            if os.path.isfile(os.path.join(output_dir, filename)):
                output_files.append(filename)
        
        return output_files
    
    def _send_task_status_update(self, task):
        """
        Envoie une mise à jour de statut pour une tâche.
        
        Args:
            task: Tâche pour laquelle envoyer une mise à jour
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Récupérer la dernière progression enregistrée
        latest_progress = TaskProgress.objects.filter(task=task).order_by('-timestamp').first()
        progress_value = latest_progress.percentage if latest_progress else 0
        from redis_communication.utils import get_volunteer_auth_token
        self.redis_client.publish('task/status', {
                    'task_id': task.task_id,
                    'volunteer_id': self.volunteer_id,
                    'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                    'status': task.status,
                    'progress': progress_value,
                    'timestamp': datetime.now().isoformat()
                },
                str(uuid.uuid4()),
                get_volunteer_auth_token() ,
                'request' 
                )
    
    def _send_task_progress(self, task, progress):
        """
        Envoie une mise à jour de progression pour une tâche.
        
        Args:
            task: Tâche pour laquelle envoyer une mise à jour
            progress: Valeur de progression actuelle
        """
        from redis_communication.utils import get_volunteer_auth_token
        self.redis_client.publish('task/progress', {
                'task_id': task.task_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'volunteer_id': self.volunteer_id,
                'progress': progress,
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
        )

        logger.info(f"Publication de la progression pour la tâche {task.name}: {progress}")
    
    
    def _save_result_to_file(self, task):
        """
        Sauvegarde le résultat de la tâche dans un fichier JSON.
        
        Args:
            task: Tâche dont il faut sauvegarder le résultat
            
        Returns:
            str: Chemin du fichier de résultat ou None si pas de résultat
        """
        if task.results:
            output_dir = os.path.join(TASKS_DIR, str(task.task_id), 'output')
            os.makedirs(output_dir, exist_ok=True)
            result_file = os.path.join(output_dir, 'result.json')
            
            with open(result_file, 'w') as f:
                json.dump(task.results, f, indent=2)
            
            # Mettre à jour les fichiers de sortie dans les données de sortie
            output_data = task.output_data or {}
            output_files = output_data.get('files', [])
            if 'result.json' not in output_files:
                output_files.append('result.json')
                output_data['files'] = output_files
                task.output_data = output_data
                task.save(update_fields=['output_data'])
            
            return result_file
        return None
    
    def _send_task_failure(self, task, error, error_type='unknown'):
        """
        Envoie une notification d'échec pour une tâche avec le type d'erreur.
        
        Args:
            task: Tâche échouée
            error: Message d'erreur
            error_type: Type d'erreur (docker, user_pause, user_stop, etc.)
        """
        from redis_communication.utils import get_volunteer_auth_token
        
        # Déterminer le type d'erreur si non spécifié
        if 'docker' in str(error).lower():
            error_type = 'docker'
        elif hasattr(task, 'status') and task.status == 'paused':
            error_type = 'user_pause'
        elif hasattr(task, 'status') and task.status == 'stopped':
            error_type = 'user_stop'
        
        logger.info(f"Envoi de notification d'échec pour la tâche {task.task_id} - Type: {error_type}")
        
        self.redis_client.publish(
            'task/status', 
            {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'workflow_id': task.workflow.workflow_id if hasattr(task, 'workflow') and task.workflow else None,
                'status': 'Failed',
                'error': str(error),
                'error_type': error_type,
                'error_message': str(error),
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token(),
            'request'
        )

# Gestionnaire pour les messages d'assignation de tâches
def task_assignment_handler(channel: str, message: Message):
    """
    Gestionnaire pour les messages d'assignation de tâches.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    task_manager = TaskManager.get_instance()
    task_manager.handle_task_assignment(channel, message)

# Gestionnaire pour les messages d'annulation de tâches
def task_cancel_handler(channel: str, message: Message):
    """
    Gestionnaire pour les messages d'annulation de tâches.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    task_manager = TaskManager.get_instance()
    task_manager.handle_task_cancel(channel, message)

# Fonction pour démarrer le gestionnaire de tâches
def start_task_manager(volunteer_id):
    """
    Démarre le gestionnaire de tâches.
    
    Args:
        volunteer_id: ID du volontaire
    """
    task_manager = TaskManager.get_instance()
    task_manager.start(volunteer_id)
    return task_manager

# Fonction pour arrêter le gestionnaire de tâches
def stop_task_manager():
    """
    Arrête le gestionnaire de tâches.
    """
    task_manager = TaskManager.get_instance()
    task_manager.stop()
