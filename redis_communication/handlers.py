"""
Gestionnaires d'événements pour les messages Redis.
Inclut les gestionnaires pour l'authentification des managers et des volontaires.
"""

import logging
import json
import os
import time
from typing import Dict, Any, Optional
from django.conf import settings

from .message import Message

logger = logging.getLogger(__name__)

# Répertoire pour stocker les requêtes en attente
PENDING_REQUESTS_DIR = os.path.join(settings.BASE_DIR, 'pending_requests')
os.makedirs(PENDING_REQUESTS_DIR, exist_ok=True)

def save_pending_request(request_id: str, data: Dict[str, Any]):
    """
    Enregistre une requête en attente dans un fichier.
    
    Args:
        request_id: ID de la requête
        data: Données de la requête
    """
    filename = os.path.join(PENDING_REQUESTS_DIR, f"{request_id}.json")
    with open(filename, 'w') as f:
        json.dump({
            'data': data,
            'timestamp': time.time()
        }, f)
    
    logger.debug(f"Requête {request_id} enregistrée dans {filename}")

def get_pending_request(request_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère une requête en attente.
    
    Args:
        request_id: ID de la requête
        
    Returns:
        Dict ou None: Données de la requête si trouvée, None sinon
    """
    filename = os.path.join(PENDING_REQUESTS_DIR, f"{request_id}.json")
    if not os.path.exists(filename):
        return None
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors de la lecture de la requête {request_id}: {e}")
        return None

def delete_pending_request(request_id: str) -> bool:
    """
    Supprime une requête en attente.
    
    Args:
        request_id: ID de la requête
        
    Returns:
        bool: True si supprimée, False sinon
    """
    filename = os.path.join(PENDING_REQUESTS_DIR, f"{request_id}.json")
    if not os.path.exists(filename):
        return False
    
    try:
        os.remove(filename)
        logger.debug(f"Requête {request_id} supprimée")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la requête {request_id}: {e}")
        return False

# Gestionnaires génériques

def log_message_handler(channel: str, message: Message):
    """
    Gestionnaire simple qui journalise les messages reçus.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    logger.info(f"Message reçu sur {channel}: {message.request_id} de {message.sender}")
    logger.debug(f"Contenu: {message.data}")

def heartbeat_handler(channel: str, message: Message):
    """
    Gestionnaire pour les messages de heartbeat.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    sender_type = message.sender.get('type', 'unknown')
    sender_id = message.sender.get('id', 'unknown')
    logger.debug(f"Heartbeat reçu de {sender_type}:{sender_id}")

def error_handler(channel: str, message: Message):
    """
    Gestionnaire pour les messages d'erreur.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    error_data = message.data
    error_msg = error_data.get('message', 'Erreur inconnue')
    error_code = error_data.get('code', 0)
    
    logger.error(f"Erreur sur {channel}: [{error_code}] {error_msg}")
    logger.error(f"Détails: {error_data}")



def default_handler(channel: str, message: Message):
    logger.warning(f" (default_handler) - Message reçu sur le canal {channel}: {message}")

def volunteer_register_response_handler(channel: str, message: Message):
    """
    Gestionnaire pour les réponses d'enregistrement des volontaires.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    logger.info(f"Réponse d'enregistrement de volontaire reçue: {message.request_id}")
    logger.info(f"Statut: {message.data.get('status')}, Message: {message.data.get('message')}")
    
    # Récupérer la requête en attente
    request = get_pending_request(message.request_id)
    if not request:
        logger.warning(f"Aucune requête en attente trouvée pour l'ID {message.request_id}")
        return

def volunteer_login_response_handler(channel: str, message: Message):
    """
    Gestionnaire pour les réponses d'authentification des volontaires.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    logger.info(f"Réponse d'authentification de volontaire reçue: {message.request_id}")
    logger.info(f"Statut: {message.data.get('status')}, Message: {message.data.get('message')}")
    
    # Récupérer la requête en attente
    request = get_pending_request(message.request_id)
    if not request:
        logger.warning(f"Aucune requête en attente trouvée pour l'ID {message.request_id}")
        return

# Dictionnaire des gestionnaires par défaut
DEFAULT_HANDLERS = {
    # Canaux génériques
    "coord/heartbeat": heartbeat_handler,
    "coord/emergency": error_handler,
    "system/error": error_handler,
    
    # Canaux d'authentification
    "auth/volunteer_register_response": volunteer_register_response_handler,
    "auth/volunteer_login_response": volunteer_login_response_handler,
    
    # Canaux de tâches
    "task/assignment": log_message_handler,
    "task/status": log_message_handler
}
