"""
Utilitaires divers pour le module de communication Redis.
"""

import time
import json
import logging
import os
from typing import Dict, Any, Optional
import jwt
from django.conf import settings
from django.utils import timezone
from .exceptions import NoLoginError
from .auth_client import DATA_BASE_DIR

logger = logging.getLogger(__name__)


def get_volunteer_auth_token():
    """Récupère le token d'authentification du volontaire depuis le fichier de configuration."""
    # Utiliser DATA_BASE_DIR pour supporter les instances multiples
    auth_file = os.path.join(DATA_BASE_DIR, 'auth', 'volunteer_auth_info.json')
    try:
        with open(auth_file, 'r') as f:
            data = json.load(f)
            return data.get('token')
    except FileNotFoundError:
        logger.error(f"Le fichier {auth_file} n'a pas été trouvé")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la lecture du fichier d'auth: {e}")
        return None

def extract_machine_info(static_data: Dict[str, Any], name: str = '', ip_address: str = '', 
                        cpu_cores: int = 0, ram_mb: int = 0, disk_gb: int = 0, 
                        ) -> Dict[str, Any]:
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
        'machine_tipe': static_data.get('machine_tipe', ''),
        
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

def get_volunteer_id():
    """Récupère l'ID du volontaire depuis le fichier de configuration."""
    # Utiliser DATA_BASE_DIR pour supporter les instances multiples
    info_file = os.path.join(DATA_BASE_DIR, 'auth', 'volunteer_info.json')
    try:
        with open(info_file, 'r') as f:
            data = json.load(f)
            return data.get('volunteer_id')
    except FileNotFoundError:
        logger.error(f"Le fichier {info_file} n'a pas été trouvé donc pas de volunteer_id")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la lecture du fichier d'info: {e}")
        return None
    




def get_local_ip():
    try:
        # Connexion fictive pour obtenir l'IP utilisée sur le réseau local
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'IP locale : {e}")
        return None