"""
Fonctions client pour l'authentification des volontaires.
"""

import logging
import uuid
import time
import json
import os
from typing import Dict, Any, Optional, Callable, Tuple
from .client import RedisClient
from .message import Message

logger = logging.getLogger(__name__)

# Répertoire pour stocker les réponses
RESPONSES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.volunteer/temp_data')
os.makedirs(RESPONSES_DIR, exist_ok=True)

# Répertoire pour stocker les informations du volontaire
VOLUNTEER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.volunteer')
os.makedirs(VOLUNTEER_DIR, exist_ok=True)

def save_response(request_id: str, response: Dict[str, Any]):
    """
    Enregistre une réponse dans un fichier.
    
    Args:
        request_id: ID de la requête
        response: Données de la réponse
    """
    filename = os.path.join(RESPONSES_DIR, f"{request_id}.json")
    with open(filename, 'w') as f:
        json.dump({
            'response': response,
            'timestamp': time.time()
        }, f)
    
    logger.debug(f"Réponse {request_id} enregistrée dans {filename}")

def get_response(request_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère une réponse.
    
    Args:
        request_id: ID de la requête
        
    Returns:
        Dict ou None: Données de la réponse si trouvée, None sinon
    """
    filename = os.path.join(RESPONSES_DIR, f"{request_id}.json")
    if not os.path.exists(filename):
        return None
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors de la lecture de la réponse {request_id}: {e}")
        return None

def delete_response(request_id: str) -> bool:
    """
    Supprime une réponse.
    
    Args:
        request_id: ID de la requête
        
    Returns:
        bool: True si supprimée, False sinon
    """
    filename = os.path.join(RESPONSES_DIR, f"{request_id}.json")
    if not os.path.exists(filename):
        return False
    
    try:
        os.remove(filename)
        logger.debug(f"Réponse {request_id} supprimée")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la réponse {request_id}: {e}")
        return False


def register_volunteer(name: str, ip_address: str, cpu_cores: int, ram_mb: int, disk_gb: int,
                       username: str, password: str, machine_info: Optional[Dict[str, Any]] = None,
                       callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                       timeout: int = 30) -> Tuple[bool, Dict[str, Any]]:
    """
    Enregistre un nouveau volontaire auprès du coordinateur.
    
    Args:
        name: Nom du volontaire
        ip_address: Adresse IP du volontaire
        cpu_cores: Nombre de coeurs CPU
        ram_mb: RAM en Mo
        disk_gb: Espace disque en Go
        username: Nom d'utilisateur pour l'authentification
        password: Mot de passe pour l'authentification
        machine_info: Informations détaillées sur la machine (optionnel)
        callback: Fonction de rappel pour traiter la réponse
        timeout: Délai d'attente en secondes
        
    Returns:
        Tuple contenant un booléen indiquant le succès et les données de réponse
    """
    from .client import RedisClient
    from .exceptions import ChannelError, TimeoutError
    import time
    import uuid
    import json
    from datetime import datetime
    
    logger.info(f"Enregistrement du volontaire {name}")
    
    # Générer un ID de requête unique
    client = RedisClient.get_instance()
    request_id = str(uuid.uuid4())
    
    # Préparer les données de la requête
    request_data = {
        'action': 'register',
        'name': name,
        'ip_address': ip_address,
        'cpu_cores': cpu_cores,
        'ram_mb': ram_mb,
        'disk_gb': disk_gb,
        'username': username,
        'password': password,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Ajouter les informations détaillées de la machine si disponibles
    if machine_info:
        # Nettoyer les informations de la machine pour éviter les problèmes de taille
        cleaned_machine_info = clean_machine_info(machine_info)
        request_data['machine_info'] = cleaned_machine_info
        logger.debug(f"Taille du message après nettoyage: {len(json.dumps(request_data))} caractères")
    
    # Fonction de rappel pour traiter la réponse
    def handle_response(channel: str, message: Message):
        if message.request_id == request_id:
            # Enregistrer la réponse
            save_response(request_id, message.data)
            
            # Appeler le callback si fourni
            if callback:
                callback(message.data)
            
            # Se désabonner du canal
            client.unsubscribe('auth/volunteer_register_response', handle_response)
    
    # S'abonner au canal de réponse
    client.subscribe('auth/volunteer_register_response', handle_response)
    
    # Publier la requête
    client.publish('auth/volunteer_register', request_data, request_id=request_id)
    
    logger.info(f"Demande d'enregistrement envoyée pour {username} (request_id: {request_id})")
    
    # Attendre la réponse
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = get_response(request_id)
        if response:
            # Supprimer la réponse du fichier
            delete_response(request_id)
            
            # Vérifier le statut
            status = response.get('response', {}).get('status')
            if status == 'success':
                return True, response.get('response', {})
            else:
                return False, response.get('response', {})
        
        # Attendre un peu avant de vérifier à nouveau
        time.sleep(0.1)
    
    # Timeout
    logger.error(f"Timeout lors de l'enregistrement de {username}")
    return False, {'status': 'error', 'message': 'Timeout'}
    
    
def login_volunteer(username: str, password: str,
                     callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                     timeout: int = 30,
                    ) -> Tuple[bool, Dict[str, Any]]:
    """
    Authentifie un volontaire auprès du coordinateur.
    
    Args:
        username: Nom d'utilisateur du volontaire
        password: Mot de passe du volontaire
        callback: Fonction de rappel pour traiter la réponse
        timeout: Délai d'attente en secondes
        machine_info: Informations détaillées sur la machine (optionnel)
        
    Returns:
        Tuple contenant un booléen indiquant le succès et les données de réponse
    """
    from .client import RedisClient
    from .exceptions import ChannelError, TimeoutError
    import time
    import uuid
    import json
    from datetime import datetime
    
    logger.info(f"Authentification du volontaire avec username {username}")
    
    # Générer un ID de requête unique
    request_id = str(uuid.uuid4())
    
    # Préparer les données de la requête
    request_data = {
        'action': 'login',
        'username': username,
        'password': password,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    
    # Créer un gestionnaire de réponse
    response_received = False
    response_data = {}
    
    # Fonction de rappel pour traiter la réponse
    def handle_response(channel: str, message: Message):
        if message.request_id == request_id:
            # Enregistrer la réponse
            save_response(request_id, message.data)
            
            # Appeler le callback si fourni
            if callback:
                callback(message.data)
            
            # Se désabonner du canal
            client.unsubscribe('auth/volunteer_login_response', handle_response)
    
    # S'abonner au canal de réponse
    client = RedisClient.get_instance()
    client.subscribe('auth/volunteer_login_response', handle_response)
    
    try:
        # Vérifier que les données peuvent être sérialisées en JSON
        try:
            json.dumps(request_data)
        except (TypeError, ValueError) as e:
            logger.error(f"Erreur de sérialisation JSON: {e}")
            logger.error("Nettoyage des données pour éviter les erreurs de sérialisation")
            # Si la sérialisation échoue, supprimer les informations détaillées de la machine
            if 'machine_info' in request_data:
                del request_data['machine_info']
        
        # Publier la requête
        client.publish('auth/volunteer_login', request_data, request_id=request_id)
        
        # Attendre la réponse
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = get_response(request_id)
            if response:
                # Supprimer la réponse du fichier
                delete_response(request_id)
                
                # Vérifier le statut
                status = response.get('response', {}).get('status')
                if status == 'success':
                    return True, response.get('response', {})
                else:
                    return False, response.get('response', {})
            
            # Attendre un peu avant de vérifier à nouveau
            time.sleep(0.1)
        
        # Timeout
        logger.error(f"Timeout lors de l'authentification de {username}")
        return False, {'status': 'error', 'message': 'Timeout'}
        
    except Exception as e:
        logger.error(f"Erreur lors de l'authentification du volontaire: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, {'status': 'error', 'message': str(e)}


def clean_machine_info(machine_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nettoie les informations de la machine pour réduire la taille du message.
    
    Args:
        machine_info: Informations complètes de la machine
        
    Returns:
        Dict[str, Any]: Informations nettoyées de la machine
    """
    cleaned_info = {}
    
    # Informations essentielles du système d'exploitation
    if 'os' in machine_info:
        cleaned_info['os'] = {
            'nom': machine_info['os'].get('nom', 'Unknown'),
            'version': machine_info['os'].get('version', ''),
            'architecture': machine_info['os'].get('architecture', ''),
            'hostname': machine_info['os'].get('hostname', '')
        }
    
    # Informations essentielles du CPU
    if 'cpu' in machine_info:
        cleaned_info['cpu'] = {
            'type': machine_info['cpu'].get('type', ''),
            'coeurs_physiques': machine_info['cpu'].get('coeurs_physiques', 0),
            'coeurs_logiques': machine_info['cpu'].get('coeurs_logiques', 0),
            'frequence': {
                'min': machine_info['cpu']['frequence'].get('min', 0),
                'max': machine_info['cpu']['frequence'].get('max', 0)
            }
        }
    
    # Informations essentielles de la mémoire
    if 'memoire in machine_info' and 'ram' in machine_info['memoire']:
        cleaned_info['memoire'] = {
            'ram': {
                'total': machine_info['memoire']['ram'].get('total', '0 GB'),
            },
            'cache': {
                'total': machine_info['memoire']['cache'].get('total', '0 GB') if 'cache' in machine_info['memoire'] else '0 GB'
            },
            'swap': {
                'total': machine_info['memoire']['swap'].get('total', '0 GB'),
            }
        }
    
    # Informations essentielles du disque
    if 'disque' in machine_info:
        cleaned_info['disque'] = {
            'total': machine_info['disque'].get('total', '0 GB'),
        }
    
    # Informations essentielles du GPU
    if 'gpu' in machine_info:
        cleaned_info['gpu'] = {
            'disponible': machine_info['gpu'].get('Disponible', False)
        }
    
    # Carte mere et bios
    if 'bios_carte_mere' in machine_info:
        cleaned_info['bios_carte_mere'] = machine_info['bios_carte_mere']

    # Résolution d'écran
    if 'resolution_ecran' in machine_info:
        cleaned_info['resolution_ecran'] = machine_info['resolution_ecran']
    
    # Adresse MAC (juste une seule)
    if 'adresse_mac' in machine_info:
        cleaned_info['adresse_mac'] = machine_info['adresse_mac']
    
   
    # Nombre de partitions
    if 'partitions_disque' in machine_info:
        cleaned_info['partitions_disque'] = len(machine_info['partitions_disque'])

    # Nombre de cartes reseaux
    if 'interfaces_reseau' in machine_info:
        cleaned_info['interfaces_reseau'] = len(machine_info['interfaces_reseau'])
    
    # Peripheriques USB
    if 'peripheriques_usb' in machine_info:
        cleaned_info['peripheriques_usb'] = len(machine_info['peripheriques_usb'])
    
    
    return cleaned_info


def save_volunteer_info(info: Dict[str, Any]) -> bool:
    """
    Enregistre les informations du volontaire dans un fichier.
    
    Args:
        info: Informations à enregistrer
    
    Returns:
        bool: True si l'enregistrement a réussi, False sinon
    """
    try:
        # Fichier de configuration du volontaire
        config_file = os.path.join(VOLUNTEER_DIR, 'volunteer_info.json')
        
        # Enregistrer les informations
        with open(config_file, 'w') as f:
            json.dump(info, f, indent=2)
        
        logger.info(f"Informations du volontaire enregistrées dans {config_file}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement des informations du volontaire: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def get_volunteer_info() -> Optional[Dict[str, Any]]:
    """
    Récupère les informations du volontaire depuis le fichier de configuration.
    Si le fichier n'existe pas, retourne None.
    
    Returns:
        Dict ou None: Informations du volontaire ou None
    """
    try:
        # Fichier de configuration du volontaire
        config_file = os.path.join(VOLUNTEER_DIR, 'volunteer_info.json')
        
        # Vérifier si le fichier existe
        if not os.path.exists(config_file):
            logger.warning(f"Fichier de configuration du volontaire introuvable: {config_file}")
            return None
        
        # Lire les informations
        with open(config_file, 'r') as f:
            info = json.load(f)
        
        logger.info(f"Informations du volontaire chargées depuis")
        return info
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des informations du volontaire: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
    



def load_volunter_credentials() -> Optional[Dict[str, Any]]:
    """
    Récupère les identifiants du volontaire depuis le fichier de .volunteer/volunteer_auth_info.json 
    si le fichier existe sinon retourne None

    Returns:
        Dict ou None: Identifiants du volontaire ou None
    """

    try:
        volunteer_info_file = os.path.join(VOLUNTEER_DIR, 'volunteer_auth_info.json')   

        if not os.path.exists(volunteer_info_file):
            return None
        
        with open(volunteer_info_file, 'r') as f:
            return json.load(f)
        
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des identifiants du volontaire: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def save_volunteer_credentials(credentials: Dict[str, Any]) -> bool:
    """
    Sauvegarde les identifiants du volontaire dans le fichier .volunteer/volunteer_auth_info.json
    
    Args:
        credentials: Dictionnaire contenant les identifiants du volontaire
        
    Returns:
        bool: True si la sauvegarde a réussi, False sinon
    """
    try:
        volunteer_info_file = os.path.join(VOLUNTEER_DIR, 'volunteer_auth_info.json')
        
        with open(volunteer_info_file, 'w') as f:
            json.dump(credentials, f, indent=4)
        
        logger.info("Identifiants du volontaire sauvegardés avec succès")
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des identifiants du volontaire: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def refresh_token_if_needed(auth_info: Dict[str, Any]) -> Optional[str]:
    """
    Rafraîchit le token JWT si celui-ci est expiré ou va expirer bientôt.
    
    Args:
        auth_info: Informations d'authentification actuelles du volontaire
        
    Returns:
        str ou None: Nouveau token si le rafraîchissement a réussi, None sinon
    """
    try:
        from .client import RedisClient
        import datetime
        
        # Vérifier si nous avons les informations nécessaires pour le rafraîchissement
        if not auth_info.get('username') or not auth_info.get('password'):
            logger.error("Username ou password manquant pour le rafraîchissement du token")
            return None
        
        logger.info(f"Tentative de rafraîchissement du token pour l'utilisateur {auth_info['username']}")
        
        # Créer une requête de rafraîchissement
        client = RedisClient.get_instance()
        request_id = str(uuid.uuid4())
        
        request_data = {
            'action': 'refresh_token',
            'username': auth_info['username'],
            'password': auth_info['password'],
            'user_type': auth_info.get('user_type', 'volunteer'),
            'old_token': auth_info.get('token'),
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Fonction de rappel pour traiter la réponse
        def handle_refresh_response(channel: str, message: Message):
            if message.request_id == request_id:
                save_response(request_id, message.data)
                client.unsubscribe('auth/token_refresh_response', handle_refresh_response)
        
        # S'abonner au canal de réponse pour le rafraîchissement
        client.subscribe('auth/token_refresh_response', handle_refresh_response)
        
        # Publier la requête de rafraîchissement
        client.publish('auth/token_refresh', request_data, request_id=request_id)
        
        # Attendre la réponse avec timeout
        start_time = time.time()
        timeout = 30  # 30 secondes
        
        while time.time() - start_time < timeout:
            response = get_response(request_id)
            if response:
                delete_response(request_id)
                
                response_data = response.get('response', {})
                status = response_data.get('status')
                
                if status == 'success':
                    new_token = response_data.get('token')
                    if new_token:
                        # Mettre à jour les informations d'authentification
                        auth_info['token'] = new_token
                        auth_info['last_login'] = time.time()
                        
                        # Sauvegarder les nouvelles informations
                        if save_volunteer_credentials(auth_info):
                            logger.info("Token rafraîchi avec succès")
                            return new_token
                        else:
                            logger.error("Erreur lors de la sauvegarde du nouveau token")
                            return None
                    else:
                        logger.error("Token manquant dans la réponse de rafraîchissement")
                        return None
                else:
                    logger.error(f"Échec du rafraîchissement du token: {response_data.get('message', 'Erreur inconnue')}")
                    return None
            
            time.sleep(0.1)
        
        logger.error("Timeout lors du rafraîchissement du token")
        return None
        
    except Exception as e:
        logger.error(f"Erreur lors du rafraîchissement du token: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None