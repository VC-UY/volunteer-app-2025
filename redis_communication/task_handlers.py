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

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


# Import des modèles à l'intérieur des fonctions pour éviter les importations circulaires

# Répertoire pour stocker les fichiers des tâches
TASKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tasks')
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
        self.running = False           
    
    def start(self, volunteer_id):
        """
        Démarre le gestionnaire de tâches.
        
        Args:
            volunteer_id: ID du volontaire
        """
        self.volunteer_id = volunteer_id
        self.running = True
        
        # S'abonner aux canaux de tâches
        self.redis_client.subscribe('task/assignment', self.handle_task_assignment)
        self.redis_client.subscribe('task/cancel', self.handle_task_cancel)
        
        logger.info(f"Gestionnaire de tâches démarré pour le volontaire {volunteer_id}")
    
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

        # Creer le workflow s'il n'existe pas
        from django.apps import apps
        Workflow = apps.get_model('volontaire', 'Workflow')
        workflow = Workflow.objects.filter(workflow_id=workflow_id).first()
        if not workflow:
            workflow = Workflow.objects.create(workflow_id=workflow_id, name="Workflow", description="Workflow")
        
        # Traiter chaque tâche assignée à ce volontaire
        for task_data in volunteer_tasks:
            task_id = task_data.get('task_id')
            
            # Vérifier si la tâche existe déjà
            from django.apps import apps
            Task = apps.get_model('volontaire', 'Task')
            existing_task = Task.objects.filter(task_id=task_id).first()
            if existing_task:
                logger.warning(f"Tâche {task_id} déjà reçue, statut actuel: {existing_task.status}")
                
                # Si la tâche est déjà terminée ou a échoué, envoyer une mise à jour au manager
                if existing_task.status in ['completed', 'failed']:
                    self._send_task_status_update(existing_task)
                continue
            # for task_data in volunteer_tasks
            # 
            # 
            #  afficher les informations dans le frontend
            # 
            # 
            # 
            # Créer une nouvelle tâche
            task = Task(
                task_id=str(task_id),
                name=task_data.get('name', 'Tâche sans nom'),
                workflow=workflow,
                parameters=task_data.get('parameters', {}),
                status='pending',
                input_data=task_data.get('input_data', {}),
                estimated_execution_time=task_data.get('estimated_execution_time', 0),
                input_data_size=task_data.get('input_data_size', 0),
                docker_information=task_data.get('docker_information', {}),
            )
            task.save()



            # Notifier les clients WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "task_updates",
                {
                    "type": "send_task_update",
                    "data": {
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status,
                        "estimated_execution_time": task.estimated_execution_time,
                    }
                }
            )




            
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
            
            # Télécharger les fichiers d'entrée si nécessaires
            if task.input_data and 'files' in task.input_data:
                self._download_input_files(task)
            
            # Exécuter la tâche dans un thread séparé
            self._execute_task(task)

            # config django channel

            # from asgiref.sync import async_to_sync
            # from channels.layers import get_channel_layer

            # channel_layer = get_channel_layer()

            # async_to_sync(channel_layer.group_send)(
            #     f"tasks_{self.volunteer_id}",
            #     {
            #         "type": "send_task",
            #         "task": {
            #             "id": task.task_id,
            #             "name": task.name,
            #             "status": task.status,
            #             "estimated_time": task.estimated_execution_time,
            #             "input_data": task.input_data,
            #         }
            #     }
            # )

        
    
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
        
        # Créer un événement de progression pour l'annulation
        TaskProgress.objects.create(
            task=task,
            progress_type='cancel',
            percentage=task.progress_events.last().percentage if task.progress_events.exists() else 0,
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
            if task.status != 'progress':
                logger.warning(f"Impossible de mettre en pause la tâche {task_id} car elle n'est pas en cours d'exécution")
                return False
            
            # Mettre à jour le statut de la tâche
            task.status = 'paused'
            task.save()
            
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
                'status': 'Paused',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
            )
            
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
            
            # Vérifier que la tâche est en pause
            if task.status != 'paused':
                logger.warning(f"Impossible de reprendre la tâche {task_id} car elle n'est pas en pause")
                return False
            
            # Mettre à jour le statut de la tâche
            task.status = 'progress'
            task.save()
            
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
                'status': 'Running',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
            )
            
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
            
            # Vérifier que la tâche est en cours d'exécution ou en pause
            if task.status not in ['progress', 'paused']:
                logger.warning(f"Impossible d'arrêter la tâche {task_id} car elle n'est pas en cours d'exécution ou en pause")
                return False
            
            # Mettre à jour le statut de la tâche
            task.status = 'Cancel'
            task.end_date = timezone.now()
            task.save()
            
            # Créer un événement de progression pour l'arrêt
            TaskProgress.objects.create(
                task=task,
                progress_type='progress',
                percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage,
                message="Tâche arrêtée"
            )
            
            # Arrêter le conteneur Docker
            docker_manager = DockerManager.get_instance()
            docker_manager.stop_task(task_id)
            
            # Envoyer une notification d'arrêt
            from redis_communication.utils import get_volunteer_auth_token
            self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'status': 'Cancel',
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
            )
            
            logger.info(f"Tâche {task_id} arrêtée")
            return True
        except Task.DoesNotExist:
            logger.error(f"Tâche {task_id} introuvable")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de la tâche {task_id}: {e}")
            return False
    
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
        
        # Créer un événement de progression pour le démarrage
        TaskProgress.objects.create(
            task=task,
            progress_type='progress',
            percentage=10,
            message="Exécution de la tâche démarrée"
        )
        
        # Envoyer une notification de démarrage
        self._send_task_status_update(task)
        
        try:
            # Récupérer l'instance unique de DockerManager
            docker_manager = DockerManager.get_instance()
            
            # Récupérer les informations Docker
            docker_info = task.docker_information or {}
            image_name = docker_info.get("name") or docker_info.get("image_name")
            
            if not image_name:
                raise ValueError("Nom d'image Docker manquant dans les informations de la tâche")
            
            # Définir les limites de ressources
            cpu_limit = docker_info.get("cpu_limit", 1.0)  # Par défaut, 1 CPU
            mem_limit = docker_info.get("memory_limit", "1g")  # Par défaut, 1GB
            
            # Préparer les volumes pour monter les fichiers d'entrée/sortie
            volumes = {}
            if hasattr(task, 'local_input_path') and task.local_input_path:
                volumes[task.local_input_path] = {'bind': '/app/input', 'mode': 'ro'}
            
            # Créer un répertoire de sortie
            import os
            from pathlib import Path
            output_dir = Path(f"{TASKS_DIR}/{task.task_id}/output")
            output_dir.mkdir(parents=True, exist_ok=True)
            volumes[str(output_dir)] = {'bind': '/app/output', 'mode': 'rw'}
            
            # Démarrer le conteneur Docker
            logger.info(f"Démarrage du conteneur Docker pour la tâche {task.task_id} avec l'image {image_name}")
            container = docker_manager.run_container(
                image_name=image_name,
                task_id=task.task_id,
                cpu_limit=cpu_limit,
                mem_limit=mem_limit,
                volumes=volumes
            )
            
            if not container:
                raise Exception(f"Impossible de démarrer le conteneur Docker pour la tâche {task.task_id}")
            
            # Suivre la progression
            self._monitor_task_progress(task)
            
            # Attendre que le conteneur soit terminé
            import time
            container = docker_manager.get_container_by_task(task.task_id)
            while container and container.status in ['created', 'running']:
                time.sleep(2)
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
                
                # Créer un événement de progression pour la complétion
                TaskProgress.objects.create(
                    task=task,
                    progress_type='complete',
                    percentage=100,
                    message="Tâche terminée avec succès"
                )
                
                # Envoyer une notification de complétion
                self._send_task_completion(task)
                
                logger.info(f"Tâche {task.task_id} terminée avec succès")
            else:
                # Tâche échouée
                error = f"Code de retour: {exit_code}\nStderr: {stderr}\nStdout: {stdout[-1000:]}"
                
                task.status = 'error'
                task.end_date = timezone.now()
                task.error_message = error
                task.error_code = str(exit_code)
                task.save()
                
                # Créer un événement de progression pour l'erreur
                TaskProgress.objects.create(
                    task=task,
                    progress_type='error',
                    percentage=100,
                    message="Tâche échouée"
                )
                
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
            
            # Créer un événement de progression pour l'erreur
            TaskProgress.objects.create(
                task=task,
                progress_type='error',
                percentage=100,
                message="Erreur lors de l'exécution",
                details={'error': str(e)}
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
        
        Args:
            task: Tâche à surveiller
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        start_time = time.time()
        last_update_time = start_time
        last_progress_value = 10  # Déjà à 10% après le démarrage
        
        # Simuler la progression (à remplacer par une vraie mesure de progression)
        while self.task_process and self.task_process.poll() is None:
            # Calculer la progression basée sur le temps écoulé et le temps estimé
            elapsed_time = time.time() - start_time
            if task.estimated_execution_time and task.estimated_execution_time > 0:
                progress = min(95.0, (elapsed_time / task.estimated_execution_time) * 100.0)
            else:
                # Si pas de temps estimé, incrémenter progressivement jusqu'à 95%
                progress = min(95.0, last_progress_value + 1.0)
            
            # Mettre à jour la progression seulement si elle a changé significativement
            if progress - last_progress_value >= 5.0:  # Mise à jour tous les 5%
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
            
            # Envoyer une mise à jour toutes les 5 secondes
            current_time = time.time()
            if current_time - last_update_time >= 5.0:
                self._send_task_progress(task, progress)
                last_update_time = current_time
            
            # Attendre un peu
            time.sleep(1.0)
    
    def _download_input_files(self, task):
        """
        Télécharge les fichiers d'entrée pour une tâche.
        
        Args:
            task: Tâche pour laquelle télécharger les fichiers
        
        Returns:
            bool: True si tous les fichiers ont été téléchargés avec succès, False sinon
        """
        import os
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
        
        # Créer un événement de progression pour le téléchargement
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        progress = TaskProgress.objects.create(
            task=task,
            progress_type='progress',
            percentage=0,
            message="Téléchargement des fichiers d'entrée"
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
                
                # Mettre à jour la progression
                progress.percentage = ((i + 1) / total_files) * 100
                progress.save()
                
            except Exception as e:
                logger.error(f"Erreur lors du téléchargement du fichier {file_url}: {e}")
                
                # Créer un événement d'erreur
                TaskProgress.objects.create(
                    task=task,
                    progress_type='error',
                    percentage=progress.percentage,
                    message=f"Erreur lors du téléchargement du fichier {file_path}",
                    details={'error': str(e)}
                )
        
        # Mettre à jour le statut de la tâche
        if len(downloaded_files) == total_files:
            # Tous les fichiers ont été téléchargés avec succès
            task.status = 'ready'
            task.local_input_path = str(input_dir)
            task.save()
            
            # Créer un événement de progression pour la fin du téléchargement
            TaskProgress.objects.create(
                task=task,
                progress_type='progress',
                percentage=100,
                message="Téléchargement des fichiers d'entrée terminé",
                details={'downloaded_files': downloaded_files}
            )
            
            logger.info(f"Téléchargement des fichiers d'entrée terminé pour la tâche {task.task_id}")
            return True
        else:
            # Certains fichiers n'ont pas pu être téléchargés
            task.status = 'error'
            task.save()
            
            # Créer un événement d'erreur
            TaskProgress.objects.create(
                task=task,
                progress_type='error',
                percentage=progress.percentage,
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
        output_dir = os.path.join(TASKS_DIR, str(task.id), 'output')
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
                'volunteer_id': self.volunteer_id,
                'progress': progress,
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
        )
    
    def _send_task_completion(self, task):
        """
        Envoie une notification de complétion pour une tâche.
        
        Args:
            task: Tâche terminée
        """
        # Sauvegarder le résultat dans un fichier
        result_file = self._save_result_to_file(task)
        
        # Envoyer la notification
        from redis_communication.utils import get_volunteer_auth_token
        self.redis_client.publish('task/complete', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'result': task.results,
                'output_files': task.output_data.get('files', []) if task.output_data else [],
                'execution_time': task.actual_execution_time,
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
            'request' 
        )
    
    def _save_result_to_file(self, task):
        """
        Sauvegarde le résultat de la tâche dans un fichier JSON.
        
        Args:
            task: Tâche dont il faut sauvegarder le résultat
            
        Returns:
            str: Chemin du fichier de résultat ou None si pas de résultat
        """
        if task.results:
            output_dir = os.path.join(TASKS_DIR, str(task.id), 'output')
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
    
    def _send_task_failure(self, task, error):
        """
        Envoie une notification d'échec pour une tâche.
        
        Args:
            task: Tâche échouée
            error: Message d'erreur
        """
        from redis_communication.utils import get_volunteer_auth_token
        self.redis_client.publish('task/status', {
                'task_id': task.task_id,
                'volunteer_id': self.volunteer_id,
                'status': 'Failed',
                'error': error,
                'timestamp': datetime.now().isoformat()
            },
            str(uuid.uuid4()),
            get_volunteer_auth_token() ,
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
