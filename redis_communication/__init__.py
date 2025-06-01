"""
Module de communication Redis universel.
Permet la communication entre les différents composants du système (coordinateur, managers, volontaires).
"""

default_app_config = 'redis_communication.apps.RedisCommunicationConfig'

# Importer les gestionnaires de tâches
from .task_handlers import task_assignment_handler, task_cancel_handler, start_task_manager, stop_task_manager
from .file_server import start_file_server, stop_file_server
