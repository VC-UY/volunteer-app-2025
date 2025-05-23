"""
Utilitaires divers pour le module de communication Redis.
"""

import time
import json
import logging
from typing import Dict, Any, Optional
import jwt
from django.conf import settings
from django.utils import timezone
from .exceptions import NoLoginError
logger = logging.getLogger(__name__)

def generate_token(client_id: str, client_type: str, expiration_hours: int = 24) -> str:
    """
    Génère un token JWT pour l'authentification.
    
    Args:
        client_id: ID du client
        client_type: Type de client (coordinator, manager, volunteer)
        expiration_hours: Durée de validité en heures
        
    Returns:
        str: Token JWT
    """
    secret_key = getattr(settings, 'SECRET_KEY', 'default-secret-key')
    
    payload = {
        'client_id': client_id,
        'client_type': client_type,
        'exp': int(time.time()) + expiration_hours * 3600,
        'iat': int(time.time())
    }
    
    return jwt.encode(payload, secret_key, algorithm='HS256')

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Vérifie un token JWT.
    
    Args:
        token: Token JWT à vérifier
        
    Returns:
        Dict ou None: Payload du token si valide, None sinon
    """
    secret_key = getattr(settings, 'SECRET_KEY', 'default-secret-key')
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expiré")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du token: {e}")
        return None


def extract_machine_info(static_data: Dict[str, Any], name: str = '', ip_address: str = '', 
                        cpu_cores: int = 0, ram_mb: int = 0, disk_gb: int = 0, 
                        username: str = '', password: str = '') -> Dict[str, Any]:
    """
    Extrait les informations de static_data et les formate pour correspondre au modèle MachineInfo.
    
    Args:
        static_data: Données statiques collectées sur la machine
        name: Nom de la machine
        ip_address: Adresse IP de la machine
        cpu_cores: Nombre de cœurs CPU
        ram_mb: Quantité de RAM en MB
        disk_gb: Espace disque en GB
        username: Nom d'utilisateur
        password: Mot de passe
        
    Returns:
        Dict: Dictionnaire contenant les informations formatées pour le modèle MachineInfo
    """
    # Valeurs par défaut pour éviter les erreurs
    os_info = static_data.get('os', {})
    cpu_info = static_data.get('cpu', {})
    memory_info = static_data.get('memory', {})
    disk_info = static_data.get('disk', {})
    network_info = static_data.get('network', {})
    screen_info = static_data.get('screen', {})
    bios_info = static_data.get('bios', {})
    motherboard_info = static_data.get('motherboard', {})
    usb_info = static_data.get('usb_devices', [])
    users_info = static_data.get('users', [])
    
    # Extraction des adresses MAC
    mac_addresses = []
    for interface in network_info.get('interfaces', []):
        if 'mac' in interface and interface['mac']:
            mac_addresses.append(interface['mac'])
    
    # Formatage des informations pour le modèle MachineInfo
    machine_info = {
        # Identifiants
        'adresse_mac': mac_addresses,
        
        # Informations sur le système d'exploitation
        'os_name': os_info.get('name', ''),
        'os_version': os_info.get('version', ''),
        'os_release': os_info.get('release', ''),
        'os_architecture': os_info.get('architecture', ''),
        'hostname': os_info.get('hostname', name),
        
        # Type de machine
        'machine_type': static_data.get('machine_type', ''),
        
        # Informations sur le processeur
        'cpu_type': cpu_info.get('model', ''),
        'cpu_architecture': cpu_info.get('architecture', ''),
        'cpu_bits': cpu_info.get('bits', ''),
        'cpu_cores_physical': cpu_info.get('cores_physical', cpu_cores),
        'cpu_cores_logical': cpu_info.get('cores_logical', cpu_cores),
        'cpu_frequency_current': cpu_info.get('frequency_current', None),
        'cpu_frequency_min': cpu_info.get('frequency_min', None),
        'cpu_frequency_max': cpu_info.get('frequency_max', None),
        
        # Informations sur la mémoire
        'ram_total': memory_info.get('total_bytes', ram_mb * 1024 * 1024),
        'ram_total_human': memory_info.get('total_human', f"{ram_mb} MB"),
        'swap_total': memory_info.get('swap_total_bytes', 0),
        'swap_total_human': memory_info.get('swap_total_human', '0'),
        
        # Informations sur le disque
        'disk_total': disk_info.get('total_bytes', disk_gb * 1024 * 1024 * 1024),
        'disk_total_human': disk_info.get('total_human', f"{disk_gb} GB"),
        'partitions': disk_info.get('partitions', []),
        
        # Informations sur l'écran
        'screen_resolution': screen_info.get('resolution', ''),
        
        # Informations sur le réseau
        'network_interfaces': network_info.get('interfaces', []),
        
        # Informations sur le BIOS et la carte mère
        'bios_info': bios_info,
        'motherboard_info': motherboard_info,
        
        # Informations sur les périphériques USB
        'usb_devices': usb_info,
        
        # Informations sur les utilisateurs connectés
        'logged_users': users_info,
        
        # Métadonnées
        'last_update': timezone.now(),
        
        # Données brutes
        'raw_data': static_data
    }
    
    return machine_info

def format_timestamp(timestamp: float) -> str:
    """
    Formate un timestamp en chaîne ISO 8601.
    
    Args:
        timestamp: Timestamp UNIX
        
    Returns:
        str: Chaîne au format ISO 8601
    """
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).isoformat()


def get_manager_login_token():
    """
    Recuper le token stoker dans le json .manager/manager_login_info.json et provoque une erreur NoLoginError si le fichier n'est pas trouvé
    """
    try:
        with open('.manager/manager_login_info.json', 'r') as f:
            data = json.load(f)
            return data['token']
    except FileNotFoundError:
        raise NoLoginError("Le fichier .manager/manager_login_info.json n'a pas été trouvé")