"""
Gestionnaires pour les tâches dans le module de communication Redis.
"""

import logging
import json
import os
import time
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import threading
import subprocess

from django.utils import timezone
from django.conf import settings

from .client import RedisClient
from .message import Message, MessageType

logger = logging.getLogger(__name__)

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
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        Task = apps.get_model('volontaire', 'Task')
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        data = message.data
        logger.info(f"Tâche reçue: {data.get('name', 'Sans nom')}")
        
        # Vérifier si la tâche est destinée à ce volontaire
        target_volunteer = data.get('volunteer_id')
        if target_volunteer != self.volunteer_id:
            logger.debug(f"Tâche ignorée: destinée au volontaire {target_volunteer}, pas à {self.volunteer_id}")
            return
        
        # Vérifier si la tâche existe déjà
        task_id = data.get('task_id')
        existing_task = Task.objects.filter(task_id=task_id).first()
        if existing_task:
            logger.warning(f"Tâche {task_id} déjà reçue, statut actuel: {existing_task.status}")
            
            # Si la tâche est déjà terminée ou a échoué, envoyer une mise à jour au manager
            if existing_task.status in ['completed', 'failed']:
                self._send_task_status_update(existing_task)
            return
        
        # Créer une nouvelle tâche
        task = Task(
            task_id=task_id,
            name=data.get('name', 'Tâche sans nom'),
            workflow_id=data.get('workflow_id', None),
            parameters=data.get('parameters', {}),
            status='pending',
            input_data=data.get('input_data', {}),
            estimated_execution_time=data.get('estimated_execution_time', 0),
            input_data_size=data.get('input_data_size', 0)
        )
        task.save()
        
        # Créer un événement de progression pour l'assignation
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
        
        # Télécharger les fichiers d'entrée si nécessaires
        if task.input_data and 'files' in task.input_data:
            self._download_input_files(task)
        
        # Envoyer une réponse d'acceptation
        self._accept_task(task)


        # lancer le processus de tâche
        
    
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
        self.redis_client.publish('task/status', {
            'task_id': task_id,
            'volunteer_id': self.volunteer_id,
            'status': 'cancelled',
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Tâche {task_id} annulée")
    
    def _accept_task(self, task):
        """
        Accepte une tâche et envoie une confirmation au manager.
        
        Args:
            task: Tâche à accepter
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Mettre à jour le statut de la tâche
        task.status = 'in_progress'
        task.start_date = timezone.now()
        task.save()
        
        # Créer un événement de progression pour l'acceptation
        TaskProgress.objects.create(
            task=task,
            progress_type='progress',
            percentage=5,
            message="Tâche acceptée par le volontaire",
            details={
                'volunteer_id': self.volunteer_id,
                'accepted_at': timezone.now().isoformat()
            }
        )
        
        # Envoyer une confirmation d'acceptation
        self.redis_client.publish('task/accept', {
            'task_id': task.task_id,
            'volunteer_id': self.volunteer_id,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Tâche {task.task_id} acceptée")
        
        # Démarrer la tâche dans un thread séparé
        self.task_thread = threading.Thread(target=self._execute_task, args=(task,))
        self.task_thread.daemon = True
        self.task_thread.start()
    
    def _execute_task(self, task):
        """
        Exécute une tâche dans un thread séparé.
        
        Args:
            task: Tâche à exécuter
        """
        # Import des modèles ici pour éviter les importations circulaires
        from django.apps import apps
        TaskProgress = apps.get_model('volontaire', 'TaskProgress')
        
        # Marquer la tâche comme démarrée
        task.status = 'in_progress'
        task.save()
        self.current_task = task
        
        # Créer un événement de progression pour le démarrage
        TaskProgress.objects.create(
            task=task,
            progress_type='start',
            percentage=10,
            message="Exécution de la tâche démarrée",
            details={
                'volunteer_id': self.volunteer_id,
                'started_at': timezone.now().isoformat()
            }
        )
        
        # Envoyer une mise à jour de statut
        self._send_task_status_update(task)
        
        try:
            # Préparer la commande
            # Utiliser les paramètres du modèle Task existant
            command = task.parameters.get('command', 'echo "Aucune commande spécifiée"')
            
            # Créer le répertoire de travail
            work_dir = os.path.join(TASKS_DIR, str(task.id))
            os.makedirs(work_dir, exist_ok=True)
            
            # Exécuter la commande
            logger.info(f"Exécution de la commande: {command}")
            self.task_process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Suivre la progression
            self._monitor_task_progress(task)
            
            # Attendre la fin de l'exécution
            stdout, stderr = self.task_process.communicate()
            
            # Vérifier le code de retour
            if self.task_process.returncode == 0:
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
                    message="Tâche terminée avec succès",
                    details={
                        'volunteer_id': self.volunteer_id,
                        'completed_at': timezone.now().isoformat(),
                        'execution_time': task.actual_execution_time,
                        'output_files': output_files
                    }
                )
                
                # Envoyer une mise à jour de statut
                self._send_task_completion(task)
                
                logger.info(f"Tâche {task.task_id} terminée avec succès")
            else:
                # Tâche échouée
                error = f"Code de retour: {self.task_process.returncode}\nStderr: {stderr[-1000:]}"
                
                task.status = 'failed'
                task.end_date = timezone.now()
                task.error_message = error
                task.error_code = str(self.task_process.returncode)
                task.save()
                
                # Créer un événement de progression pour l'échec
                TaskProgress.objects.create(
                    task=task,
                    progress_type='error',
                    percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage,
                    message="Tâche échouée",
                    details={
                        'volunteer_id': self.volunteer_id,
                        'error': error,
                        'error_code': self.task_process.returncode
                    }
                )
                
                # Envoyer une mise à jour de statut
                self._send_task_failure(task, error)
                
                logger.error(f"Tâche {task.task_id} échouée: {error}")
        
        except Exception as e:
            # Erreur lors de l'exécution
            import traceback
            error = f"Erreur lors de l'exécution: {str(e)}\n{traceback.format_exc()}"
            
            task.status = 'failed'
            task.end_date = timezone.now()
            task.error_message = error
            task.error_code = 'exception'
            task.save()
            
            # Créer un événement de progression pour l'erreur
            TaskProgress.objects.create(
                task=task,
                progress_type='error',
                percentage=TaskProgress.objects.filter(task=task).order_by('-timestamp').first().percentage if TaskProgress.objects.filter(task=task).exists() else 0,
                message="Erreur lors de l'exécution",
                details={
                    'volunteer_id': self.volunteer_id,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
            )
            
            # Envoyer une mise à jour de statut
            self._send_task_failure(task, error)
            
            logger.error(f"Erreur lors de l'exécution de la tâche {task.task_id}: {e}")
            logger.error(traceback.format_exc())
        
        finally:
            # Réinitialiser l'état
            self.task_process = None
            self.current_task = None
    
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
        """
        logger.info(f"Téléchargement des fichiers d'entrée pour la tâche {task.task_id}")
        
        # TODO: Implémenter le téléchargement des fichiers depuis le manager
        # Pour l'instant, on simule juste la création de fichiers vides
        for filename in task.input_files:
            file_path = task.get_input_file_path(filename)
            with open(file_path, 'w') as f:
                f.write('')
            logger.debug(f"Fichier d'entrée créé: {file_path}")
    
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
        
        self.redis_client.publish('task/status', {
            'task_id': task.task_id,
            'volunteer_id': self.volunteer_id,
            'status': task.status,
            'progress': progress_value,
            'timestamp': datetime.now().isoformat()
        })
    
    def _send_task_progress(self, task, progress):
        """
        Envoie une mise à jour de progression pour une tâche.
        
        Args:
            task: Tâche pour laquelle envoyer une mise à jour
            progress: Valeur de progression actuelle
        """
        self.redis_client.publish('task/progress', {
            'task_id': task.task_id,
            'volunteer_id': self.volunteer_id,
            'progress': progress,
            'timestamp': datetime.now().isoformat()
        })
    
    def _send_task_completion(self, task):
        """
        Envoie une notification de complétion pour une tâche.
        
        Args:
            task: Tâche terminée
        """
        # Sauvegarder le résultat dans un fichier
        result_file = self._save_result_to_file(task)
        
        # Envoyer la notification
        self.redis_client.publish('task/complete', {
            'task_id': task.task_id,
            'volunteer_id': self.volunteer_id,
            'result': task.results,
            'output_files': task.output_data.get('files', []) if task.output_data else [],
            'execution_time': task.actual_execution_time,
            'timestamp': datetime.now().isoformat()
        })
    
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
        self.redis_client.publish('task/status', {
            'task_id': task.task_id,
            'volunteer_id': self.volunteer_id,
            'status': 'failed',
            'error': error,
            'timestamp': datetime.now().isoformat()
        })

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
