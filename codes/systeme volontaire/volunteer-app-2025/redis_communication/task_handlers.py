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
                "Le gestionnaire de tâches est déjà en cours d'exécution (volunteer_id=%s)",
                self.volunteer_id,
            )
            # Republier un heartbeat même si déjà démarré
            self._send_heartbeat()
            return
        self.running = True
        
        # S'abonner aux canaux de tâches
        self.redis_client.subscribe('task/assignment', self.handle_task_assignment)
        self.redis_client.subscribe('task/cancel', self.handle_task_cancel)

        # Présence: heartbeat immédiat puis périodique
        self._send_heartbeat()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"volunteer-heartbeat-{self.volunteer_id[:8]}",
            daemon=True,
        )
        self.heartbeat_thread.start()
        
        logger.info(f"Gestionnaire de tâches démarré pour le volontaire {volunteer_id}")

    def _send_heartbeat(self):
        """Signale au manager/coordinateur que ce volontaire est en ligne."""
        if not self.volunteer_id:
            return
        try:
            from redis_communication.utils import get_volunteer_auth_token
            import uuid as _uuid
            from volontaire.preferences_payload import build_preferences_payload
            from volontaire.services.runtime_client import RuntimeClient

            prefs = build_preferences_payload()

            # Le runtime vc-uyr ne tient pas compte des créneaux horaires
            # configurés dans l'app (is_available_now) : la disponibilité
            # annoncée au coordinateur reflète uniquement ce que le runtime
            # demande réellement — health + état Ready/Executing/Paused.
            rt_status = RuntimeClient().status()
            rt_state = rt_status.get("state") if rt_status else None
            if self.current_task or rt_state in ("Executing", "Paused"):
                availability_status = "busy"
            elif rt_state == "Ready":
                availability_status = "available"
            else:
                availability_status = "offline"

            payload = {
                "volunteer_id": self.volunteer_id,
                "status": availability_status,
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
                str(_uuid.uuid4()),
                token,
                "request",
            )
            # Alias historique
            self.redis_client.publish(
                "coord/heartbeat",
                payload,
                str(_uuid.uuid4()),
                token,
                "request",
            )
        except Exception as exc:
            logger.warning("Echec heartbeat volontaire: %s", exc)

    def _heartbeat_loop(self):
        while self.running:
            self._send_heartbeat()
            time.sleep(20)
    
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

        # Signaler la déconnexion
        if self.volunteer_id:
            try:
                from redis_communication.utils import get_volunteer_auth_token
                import uuid as _uuid
                self.redis_client.publish(
                    "volunteer/disconnect",
                    {
                        "volunteer_id": self.volunteer_id,
                        "timestamp": timezone.now().isoformat(),
                    },
                    str(_uuid.uuid4()),
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

        from volontaire.preferences_payload import (
            build_preferences_payload,
            task_matches_preferences,
        )
        prefs = build_preferences_payload()

        # Creer le workflow s'il n'existe pas
        from django.apps import apps
        Workflow = apps.get_model('volontaire', 'Workflow')
        workflow = Workflow.objects.filter(workflow_id=workflow_id).first()
        if not workflow:
            workflow = Workflow.objects.create(workflow_id=workflow_id, name="Workflow", description="Workflow")
        
        # Traiter chaque tâche assignée à ce volontaire
        for task_data in volunteer_tasks:
            task_id = task_data.get('task_id')

            ok, reason = task_matches_preferences(task_data, prefs)
            if not ok:
                logger.warning(
                    "Tâche %s refusée (préférences): %s", task_id, reason
                )
                try:
                    from redis_communication.utils import get_volunteer_auth_token
                    import uuid as _uuid
                    self.redis_client.publish(
                        "task/status",
                        {
                            "task_id": str(task_id),
                            "volunteer_id": self.volunteer_id,
                            "workflow_id": workflow_id,
                            "status": "failed",
                            "error_type": "preference_mismatch",
                            "error_message": reason,
                        },
                        str(_uuid.uuid4()),
                        get_volunteer_auth_token(),
                        "request",
                    )
                except Exception:
                    pass
                continue
            
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
                logger.info(
                    "Tâche %s déjà reçue (statut %s) — mise à jour et reprise",
                    task_id,
                    existing_task.status,
                )
                existing_task.name = task_data.get('name', existing_task.name)
                existing_task.workflow = workflow
                existing_task.command = task_data.get('command', existing_task.command)
                existing_task.parameters = task_data.get('parameters', existing_task.parameters or {})
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
                task = Task(
                    task_id=str(task_id),
                    name=task_data.get('name', 'Tâche sans nom'),
                    workflow=workflow,
                    command=task_data.get('command'),
                    parameters=task_data.get('parameters', {}),
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
            
            # Exécuter la tâche dans un thread séparé
            import threading    
            thread = threading.Thread(target=self._execute_task, args=(task,))
            thread.setDaemon(True)
            thread.start()
        
    
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
        # Statuts normalisés: 'pending', 'progress', 'paused', 'completed', 'failed', 'cancelled'
        if task.status in ['in_progress', 'pending', 'started', 'progress']:
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

        Le runtime vc-uyr n'exécute qu'une seule tâche à la fois et n'expose
        qu'un contrôle global (POST /api/control/pause) : cette action n'est
        donc possible que si task_id correspond à la tâche actuellement
        exécutée par le runtime.

        Args:
            task_id: ID de la tâche à mettre en pause

        Returns:
            bool: True si la tâche a été mise en pause avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.services.runtime_client import RuntimeClient

        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)

            # Vérifier que la tâche est en cours d'exécution
            if task.status != 'progress':
                logger.warning(f"Impossible de mettre en pause la tâche {task_id} car elle n'est pas en cours d'exécution")
                return False

            if not (self.current_task and self.current_task.task_id == task_id):
                logger.warning(
                    "Impossible de mettre en pause la tâche %s: ce n'est pas la tâche en cours sur le runtime", task_id
                )
                return False

            if not RuntimeClient().pause():
                logger.error(f"Le runtime vc-uyr n'a pas pu mettre en pause la tâche {task_id}")
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
        Reprend l'exécution d'une tâche en pause (POST /api/control/resume du runtime).

        Args:
            task_id: ID de la tâche à reprendre

        Returns:
            bool: True si la tâche a été reprise avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.services.runtime_client import RuntimeClient

        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)

            # Vérifier que la tâche est en pause
            if task.status != 'paused':
                logger.warning(f"Impossible de reprendre la tâche {task_id} car elle n'est pas en pause")
                return False

            if not (self.current_task and self.current_task.task_id == task_id):
                logger.warning(
                    "Impossible de reprendre la tâche %s: ce n'est pas la tâche en cours sur le runtime", task_id
                )
                return False

            if not RuntimeClient().resume():
                logger.error(f"Le runtime vc-uyr n'a pas pu reprendre la tâche {task_id}")
                return False

            # Mettre à jour le statut de la tâche
            task.status = 'progress'
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

        Le runtime vc-uyr n'expose pas d'annulation par tâche : la seule
        façon d'interrompre l'exécution en cours est d'arrêter le processus
        du runtime (POST /api/control/shutdown). Il devra être relancé
        (start_with_runtime.sh) pour accepter une prochaine tâche.

        Args:
            task_id: ID de la tâche à arrêter

        Returns:
            bool: True si la tâche a été arrêtée avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        from volontaire.services.runtime_client import RuntimeClient

        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)

            # Vérifier que la tâche est en cours d'exécution ou en pause
            if task.status not in ['progress', 'paused']:
                logger.warning(f"Impossible d'arrêter la tâche {task_id} car elle n'est pas en cours d'exécution ou en pause")
                return False

            if not (self.current_task and self.current_task.task_id == task_id):
                logger.warning(
                    "Impossible d'arrêter la tâche %s: ce n'est pas la tâche en cours sur le runtime", task_id
                )
                return False

            RuntimeClient().shutdown()

            # Mettre à jour le statut de la tâche ('stopped', pas 'Cancel' —
            # cohérent avec le badge/filtre frontend et task_matches_preferences)
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
        """Met à jour les limites de ressources sur le runtime vc-uyr (POST /api/resources).

        Args:
            task_id: ID de la tâche à mettre à jour
            cpu_limit: Nouvelle limite CPU. Interprétée comme un quota Docker
                (ex: 50000 = 5%) si > 100, sinon comme un pourcentage direct.
            memory_limit: Nouvelle limite mémoire (str, ex: '512m', '1g', ou nombre de Mo)
        Returns:
            bool: True si les limites ont été mises à jour avec succès, False sinon
        """

        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        from volontaire.services.runtime_client import RuntimeClient
        from volontaire.preferences_payload import _machine_resources

        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)

            # Vérifier que la tâche est en cours d'exécution
            if task.status not in ['progress', 'paused']:
                logger.warning(f"Impossible de mettre à jour les limites de la tâche {task_id} car elle n'est pas en cours d'exécution ou en pause")
                return False

            cpu_percent = None
            if cpu_limit is not None:
                cpu_val = float(cpu_limit)
                # Un quota Docker (cpu_quota) est exprimé en millionièmes de seconde CPU
                # par période de 100000 (ex: 50000 = 5%). Une valeur <= 100 est déjà un %.
                cpu_percent = int(cpu_val / 1000) if cpu_val > 100 else int(cpu_val)

            memory_mb = None
            if memory_limit is not None:
                if isinstance(memory_limit, (int, float)):
                    memory_mb = int(memory_limit)
                else:
                    mem_str = str(memory_limit).strip().lower()
                    if mem_str.endswith('g'):
                        memory_mb = int(float(mem_str[:-1]) * 1024)
                    elif mem_str.endswith('m'):
                        memory_mb = int(float(mem_str[:-1]))
                    else:
                        memory_mb = int(float(mem_str))

            machine = _machine_resources()
            success = RuntimeClient().update_resources(
                cpu_percent=cpu_percent if cpu_percent is not None else 80,
                memory_mb=memory_mb if memory_mb is not None else machine["ram_mb"],
                disk_total_mb=machine["disk_gb"] * 1024,
            )


            if not success:
                logger.warning(f"Échec de la mise à jour des limites pour la tâche {task_id}")
                return False

            # Mettre à jour les informations de la tâche
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
        Marque une tâche comme terminée et démarre un serveur de fichiers pour les fichiers de sortie.
        
        Args:
            task_id: ID de la tâche terminée
            
        Returns:
            bool: True si la tâche a été marquée comme terminée avec succès, False sinon
        """
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        from redis_communication.file_server import start_task_file_server
        import os

        try:
            # Récupérer la tâche
            task = Task.objects.get(task_id=task_id)

            # Déterminer le chemin des fichiers de sortie
            output_dir = os.path.join(TASKS_DIR, str(task.task_id), 'output')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Récupérer les fichiers de sortie depuis task.output_data ou lister le répertoire
            output_files = []
            if task.output_data and 'files' in task.output_data:
                output_files = task.output_data['files']
                logger.info(f"Fichiers de sortie depuis task.output_data: {output_files}")

            # Si pas de fichiers dans output_data, lister le répertoire
            if not output_files:
                output_files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
                logger.info(f"Fichiers de sortie depuis le répertoire: {output_files}")

            # Log pour debug - liste détaillée des fichiers
            if os.path.exists(output_dir):
                files_with_sizes = []
                for f in os.listdir(output_dir):
                    filepath = os.path.join(output_dir, f)
                    if os.path.isfile(filepath):
                        files_with_sizes.append(f"{f} ({os.path.getsize(filepath)} bytes)")
                logger.info(f"Contenu du répertoire de sortie {output_dir}: {files_with_sizes}")
            else:
                logger.warning(f"Le répertoire de sortie {output_dir} n'existe pas!")

            logger.info(f"Fichiers à servir: {output_files}")

            # Preferer l'upload HTTP vers le manager (fonctionne derriere NAT)
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
    
    def _apply_runtime_resources(self, runtime):
        """Pousse les préférences de ressources du volontaire vers le runtime vc-uyr."""
        try:
            from volontaire.preferences_payload import build_preferences_payload

            prefs = build_preferences_payload()
            cpu_percent = int(prefs.get("cpu_max_utilisation") or 80)
            memory_mb = int((prefs.get("max_ram_gb") or 1) * 1024)
            disk_total_mb = int((prefs.get("max_disk_gb") or 1) * 1024)
            runtime.update_resources(cpu_percent, memory_mb, disk_total_mb)
        except Exception as e:
            logger.warning("Impossible d'appliquer les préférences de ressources au runtime: %s", e)

    def _locate_bundle(self, task):
        """
        Localise le bundle .tar.gz de la tâche parmi les fichiers déjà
        téléchargés par _download_input_files (task.local_input_path).
        """
        import os

        input_path = getattr(task, 'local_input_path', None)
        if not input_path or not os.path.isdir(input_path):
            return None

        candidates = sorted(os.listdir(input_path))
        for name in candidates:
            if name.endswith('.tar.gz') or name.endswith('.tgz'):
                return os.path.join(input_path, name)
        # Aucun fichier .tar.gz explicite: utiliser le premier fichier du dossier d'entrée
        for name in candidates:
            full_path = os.path.join(input_path, name)
            if os.path.isfile(full_path):
                return full_path
        return None

    def _poll_runtime_until_done(self, runtime, task, poll_interval=2, timeout_secs=3600):
        """
        Poll GET /api/status toutes les `poll_interval` secondes jusqu'à ce que
        l'état ne soit plus "Executing", puis récupère GET /api/result.

        Le scheduler interne du runtime tourne sur son propre tick (plusieurs
        secondes) : juste après la soumission, /api/status peut encore
        renvoyer "Ready" (état de la tâche PRÉCÉDENTE) avant que la nouvelle
        tâche ne soit effectivement prise en charge. Pour éviter de renvoyer
        par erreur le résultat d'une tâche antérieure, on n'accepte le
        résultat de /api/result que si son task_id correspond bien à la
        tâche soumise ici.

        Retourne la charge utile complète de /api/result, c'est-à-dire
        {"ready": true, "result": {task_id, success, exit_code, ...}, "files": [...]}
        — "result" et "files" sont deux clés SŒURS au premier niveau, pas
        imbriquées l'une dans l'autre (cf. RuntimeClient.get_result()).
        """
        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            status = runtime.status()
            if status is None:
                time.sleep(poll_interval)
                continue

            state = status.get("state")
            if state == "Executing" and status.get("task_id") == task.task_id:
                time.sleep(poll_interval)
                continue
            if state == "Executing":
                # Le runtime n'exécute qu'une tâche à la fois : ne devrait pas
                # arriver, mais on attend que ça se libère plutôt que de
                # renvoyer un faux résultat.
                time.sleep(poll_interval)
                continue

            # État != Executing : soit notre tâche n'a pas encore été prise en
            # charge par le scheduler (résultat encore absent ou appartenant à
            # une tâche précédente), soit elle est terminée. On ne considère
            # que le résultat dont le task_id correspond à celui soumis ici.
            result = runtime.get_result()
            if result is not None:
                result_task_id = (result.get('result') or {}).get('task_id')
                if result_task_id == task.task_id:
                    return result
            time.sleep(poll_interval)
        return None

    def _write_runtime_result_files(self, task, result):
        """Décode les fichiers base64 renvoyés par GET /api/result (clé "files" au
        premier niveau) dans le dossier de sortie."""
        import base64
        import os

        output_dir = os.path.join(TASKS_DIR, str(task.task_id), 'output')
        os.makedirs(output_dir, exist_ok=True)

        output_files = []
        for f in (result.get('files') or []):
            name = f.get('name')
            content_b64 = f.get('content_b64')
            if not name or content_b64 is None:
                continue
            with open(os.path.join(output_dir, name), 'wb') as out:
                out.write(base64.b64decode(content_b64))
            output_files.append(name)
        return output_files

    def _execute_task(self, task):
        """
        Exécute une tâche dans un thread séparé en utilisant le runtime vc-uyr
        (localhost:7070) à la place de Docker.

        Args:
            task: Tâche à exécuter
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        import traceback
        from volontaire.services.runtime_client import (
            RuntimeClient,
            RuntimeUnavailableError,
            RuntimeBusyError,
        )

        TaskProgress = apps.get_model('volontaire', 'TaskProgress')

        # Marquer la tâche comme démarrée.
        # IMPORTANT: garder 'progress' (déjà utilisé par _accept_task) et non
        # 'Running' — pause_task/resume_task/stop_task/update_limits ci-dessous
        # comparent task.status à 'progress'/'paused' (comparaison sensible à
        # la casse) ; un statut différent ferait échouer silencieusement pause/
        # reprise/arrêt/limites sur une tâche pourtant bien en cours.
        task.status = 'progress'
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
            runtime = RuntimeClient()

            if not runtime.health():
                raise RuntimeUnavailableError(
                    "Le runtime vc-uyr (localhost:7070) ne répond pas. "
                    "Vérifiez qu'il est démarré (start_with_runtime.sh)."
                )

            current_status = runtime.status()
            if current_status and current_status.get("state") == "Executing":
                raise RuntimeBusyError(
                    f"Le runtime exécute déjà la tâche {current_status.get('task_id')}"
                )

            self._apply_runtime_resources(runtime)

            bundle_path = self._locate_bundle(task)
            if not bundle_path:
                raise ValueError(
                    f"Bundle introuvable pour la tâche {task.task_id} "
                    f"(aucun fichier téléchargé dans {task.local_input_path})"
                )

            with open(bundle_path, 'rb') as bundle_file:
                bundle_bytes = bundle_file.read()

            logger.info(
                "Soumission du bundle %s (%d octets) au runtime vc-uyr pour la tâche %s",
                bundle_path, len(bundle_bytes), task.task_id,
            )
            if not runtime.submit_task(task.task_id, bundle_bytes):
                raise RuntimeError(f"Échec de soumission du bundle au runtime pour la tâche {task.task_id}")

            # Démarrer le monitoring de progression dans un thread séparé
            import threading
            monitor_thread = threading.Thread(target=self._monitor_task_progress, args=(task,))
            monitor_thread.daemon = True
            monitor_thread.start()

            # Poller GET /api/status toutes les 2s jusqu'à ce que l'exécution se termine,
            # puis récupérer GET /api/result (ne jamais l'appeler tant que state == "Executing")
            result = self._poll_runtime_until_done(runtime, task)
            if result is None:
                raise TimeoutError(f"Timeout en attendant la fin d'exécution du runtime pour la tâche {task.task_id}")

            task_result_data = result.get('result') or {}
            exit_code = task_result_data.get('exit_code', task_result_data.get('return_code', -1))
            stdout = task_result_data.get('stdout', '')
            logger.info(f"Code de sortie du runtime pour la tâche {task.task_id}: {exit_code}")

            if exit_code == 0:
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
                task_result = {
                    'stdout': stdout[-1000:] if stdout else '',
                    'return_code': 0,
                }

                # Décoder les fichiers de sortie renvoyés par le runtime (base64)
                output_files = self._write_runtime_result_files(task, result)
                logger.info(f"Fichiers de sortie décodés pour {task.task_id}: {output_files}")

                # Marquer la tâche comme terminée
                task.status = 'completed'
                task.end_date = timezone.now()
                task.results = task_result
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
                error = f"Code de retour: {exit_code}\nStdout: {stdout[-1000:] if stdout else ''}"

                task.status = 'error'
                task.end_date = timezone.now()
                task.error_message = error
                task.error_code = str(exit_code)
                task.save()

                # Notifier le frontend de l'échec
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
        except (RuntimeUnavailableError, RuntimeBusyError) as runtime_error:
            # Erreur runtime spécifique - marquer avec un type d'erreur clair
            error = str(runtime_error)
            error_type = 'runtime'

            task.status = 'failed'
            task.end_date = timezone.now()
            task.error_message = error
            task.save()

            # Notifier le frontend de l'échec runtime
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
                        "error_type": error_type,
                    }
                }
            )

            # Envoyer une notification d'échec avec le type d'erreur
            self._send_task_failure(task, error, error_type=error_type)

            logger.error(f"Erreur runtime vc-uyr pour la tâche {task.task_id}: {error}")
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

        # Attendre un peu pour laisser le runtime démarrer l'exécution
        time.sleep(2)

        start_time = time.time()
        last_progress_value = 2  # Déjà à 2% après le démarrage

        from volontaire.services.runtime_client import RuntimeClient
        runtime = RuntimeClient()

        logger.info(f"Démarrage du monitoring de progression pour la tâche {task.task_id}")

        # Boucle de surveillance de la progression
        while True:
            try:
                # Récupérer l'état actuel du runtime
                runtime_status = runtime.status()

                # Le runtime est injoignable ou n'exécute plus cette tâche: fin du monitoring
                if not runtime_status:
                    logger.info(f"Monitoring terminé pour la tâche {task.task_id}: runtime injoignable")
                    break

                if runtime_status.get('state') not in ('Executing', 'Paused'):
                    logger.info(
                        "Monitoring terminé pour la tâche %s: état runtime %s",
                        task.task_id, runtime_status.get('state'),
                    )
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
        server_path = file_server.get('path', '')  # Chemin additionnel sur le serveur (ex: /files/input_xxx/)

        if not base_url:
            logger.error(f"URL du serveur de fichiers manquante pour la tâche {task.task_id}")
            return False

        logger.info(f"Serveur de fichiers: base_url={base_url}, path={server_path}")

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
                
            # Construire l'URL complète avec le chemin du serveur
            # server_path peut être vide ou contenir un chemin comme "/files/input_xxx/"
            if server_path:
                # S'assurer que le chemin se termine par /
                if not server_path.endswith('/'):
                    server_path = server_path + '/'
                file_url = f"{base_url}{server_path}{file_path}"
            else:
                file_url = f"{base_url}/{file_path}"
            
            # Déterminer le chemin local
            local_path = input_dir / Path(file_path).name
            
            try:
                # Télécharger le fichier
                logger.info(f"Téléchargement du fichier {file_url} vers {local_path}")
                response = requests.get(file_url, stream=True, timeout=30)
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
                logger.warning(f"Échec téléchargement via proxy {file_url}: {e}")

                # Fallback: essayer l'URL originale si disponible (quand le proxy est inaccessible)
                original_base_url = file_server.get('_original_base_url')
                if original_base_url:
                    try:
                        # Construire l'URL originale (sans le path du proxy)
                        fallback_url = f"{original_base_url}/{file_path}"
                        logger.info(f"Tentative fallback vers URL originale: {fallback_url}")

                        response = requests.get(fallback_url, stream=True, timeout=30)
                        response.raise_for_status()

                        with open(local_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)

                        downloaded_files.append({
                            'remote_path': file_path,
                            'local_path': str(local_path)
                        })
                        logger.info(f"Fichier téléchargé via fallback: {fallback_url}")
                        continue  # Succès, passer au fichier suivant

                    except Exception as fallback_error:
                        logger.error(f"Échec fallback {fallback_url}: {fallback_error}")

                logger.error(f"Impossible de télécharger le fichier {file_path}")
                
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
        if 'runtime' in str(error).lower():
            error_type = 'runtime'
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
