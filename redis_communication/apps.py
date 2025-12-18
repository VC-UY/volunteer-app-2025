"""
Configuration de l'application Django pour le module de communication Redis du volontaire.
Ce module gère l'enregistrement, l'authentification et la communication du volontaire
avec le coordinateur en utilisant l'agent de collecte de données.
"""

from django.apps import AppConfig
import logging
import sys
import json
import os
import time
import platform
import socket
import uuid
import psutil
import threading
import importlib.util
import subprocess
from datetime import datetime, timedelta
from django.utils import timezone

# Import des fonctions d'authentification
from .auth_client import save_volunteer_info, get_volunteer_info, DATA_BASE_DIR

# Configuration du logging pour afficher les messages dans la console
logger = logging.getLogger('redis_communication')
logger.setLevel(logging.DEBUG)

# Ajouter un gestionnaire de console si aucun n'existe déjà
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

# Répertoire pour stocker les informations du volontaire (utiliser le chemin de auth_client)
VOLUNTEER_DIR = DATA_BASE_DIR
# Le répertoire est déjà créé par auth_client.py

# Chemin vers l'agent de collecte de données
AGENT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agent.py')

# Intervalle de collecte et d'envoi (en secondes)
COLLECTION_INTERVAL = 60  # Collecte chaque minute
SEND_INTERVAL = 300  # Envoi toutes les 5 minutes

def load_agent_module():
    """
    Charge dynamiquement le module agent.py pour utiliser ses fonctions.
    
    Returns:
        module: Le module agent chargé ou None en cas d'échec
    """
    try:
        if not os.path.exists(AGENT_PATH):
            logger.error(f"Le fichier agent.py n'existe pas à l'emplacement: {AGENT_PATH}")
            return None
        
        logger.info(f"Chargement du module agent depuis: {AGENT_PATH}")
        spec = importlib.util.spec_from_file_location("agent", AGENT_PATH)
        agent_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_module)
        logger.info("Module agent chargé avec succès")
        return agent_module
    except Exception as e:
        logger.error(f"Erreur lors du chargement du module agent: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def get_machine_info():
    """
    Récupère les informations statiques de la machine du volontaire en utilisant l'agent.
    
    Returns:
        dict: Informations statiques sur la machine
    """
    logger.info("Collecte des informations statiques de la machine via l'agent...")
    try:
        # Charger et utiliser l'agent
        agent_module = load_agent_module()
        if (agent_module and hasattr(agent_module, 'collect_initial_data')):
            logger.info("Utilisation de l'agent pour collecter les données statiques")
            static_data = agent_module.collect_initial_data()
            logger.info("Données statiques collectées avec succès via l'agent")
            return static_data
        else:
            logger.error("Impossible de charger l'agent ou fonction collect_initial_data manquante")
            return {}
    except Exception as e:
        logger.error(f"Erreur lors de la collecte des informations statiques: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

def get_machine_state():
    """
    Récupère l'état actuel de la machine du volontaire en utilisant l'agent.
    
    Returns:
        dict: État actuel de la machine
    """
    logger.info("Collecte de l'état actuel de la machine via l'agent...")
    try:
        # Charger et utiliser l'agent
        agent_module = load_agent_module()
        if (agent_module and hasattr(agent_module, 'collect_variable_data')):
            logger.info("Utilisation de l'agent pour collecter les données variables")
            variable_data = agent_module.collect_variable_data()
            logger.info("Données variables collectées avec succès via l'agent")
            return variable_data
        else:
            logger.error("Impossible de charger l'agent ou fonction collect_variable_data manquante")
            return {}
    except Exception as e:
        logger.error(f"Erreur lors de la collecte des informations variables: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

   
def _parse_size_to_bytes( size_str):
        """
        Convertit une chaîne de taille (ex: '8.00 GB') en octets.
        """
        try:
            parts = size_str.strip().split()
            if len(parts) >= 2:
                value = float(parts[0])
                unit = parts[1].upper()
                
                multipliers = {
                    'B': 1,
                    'KB': 1024,
                    'MB': 1024 ** 2,
                    'GB': 1024 ** 3,
                    'TB': 1024 ** 4
                }
                
                return int(value * multipliers.get(unit, 1))
        except:
            pass
        return 0


def collect_full_volunteer_info(existing_info=None):
    """Collecte toutes les informations du volontaire via l'agent"""
    static_data = get_machine_info()
    logger.info(f"Données statiques collectées via l'agent: OS={static_data.get('os', {}).get('nom')}, CPU={static_data.get('cpu', {}).get('coeurs_logiques')} cores")
    
    from .utils import get_local_ip
    ip_address = get_local_ip()
    hostname = static_data.get('os', {}).get('hostname', socket.gethostname())
    cpu_cores = int(static_data.get('cpu', {}).get('coeurs_logiques', 1))
    
    # Conversion mémoire RAM
    total_memory_str = static_data.get('memoire', {}).get('ram', {}).get('total', '1 GB')
    try:
        if 'GB' in total_memory_str:
            ram_mb = float(total_memory_str.split(' ')[0]) * 1024
        elif 'MB' in total_memory_str:
            ram_mb = float(total_memory_str.split(' ')[0])
        else:
            ram_mb = 1024  # Default 1GB
    except:
        ram_mb = 1024

    # Conversion disque
    total_disk_str = static_data.get('disque', {}).get('total', '10 GB')
    try:
        if 'GB' in total_disk_str:
            disk_gb = float(total_disk_str.split(' ')[0])
        elif 'TB' in total_disk_str:
            disk_gb = float(total_disk_str.split(' ')[0]) * 1024
        else:
            disk_gb = 10  # Default 10GB
    except:
        disk_gb = 10
    
    username = (existing_info.username if existing_info and hasattr(existing_info, 'username') and existing_info.username else f"volunteer_{uuid.uuid4().hex[:8]}")
    password = (existing_info.password if existing_info and hasattr(existing_info, 'password') and existing_info.password else uuid.uuid4().hex)
    
    return {
        'hostname': hostname,
        'ip_address': ip_address,
        'cpu_cores': cpu_cores,
        'ram_mb': ram_mb,
        'disk_gb': disk_gb,
        'username': username,
        'password': password,
        'machine_info': static_data
    }

def auth_volunteer_flow():

    from .auth_client import register_volunteer, login_volunteer
    from volontaire.models import MachineInfo
    logger.info("Vérification de l'enregistrement du volontaire...")
    volunteer_info = MachineInfo.objects.get_last_inserted()

    
    if volunteer_info and volunteer_info.volunteer_id:
        logger.info("Cas 1 : Volontaire déjà enregistré avec volunteer_id")
        # Enrichir les données locales avec l'agent
        full_info = collect_full_volunteer_info(volunteer_info)
        # Mettre à jour la BD locale si des champs sont incomplets
        updated = False
        for k, v in full_info.items():
            if hasattr(volunteer_info, k) and (getattr(volunteer_info, k) in [None, '', 0]):
                setattr(volunteer_info, k, v)
                updated = True
        if updated:
            volunteer_info.save()
        logger.info(f"Connexion volontaire avec username={full_info['username']}")
        success, data = login_volunteer(
            username=full_info['username'],
            password=full_info['password']
        )
        if success:
            logger.info("Volontaire authentifié avec succès")
            if not os.path.exists('.volunteer'):
                os.makedirs('.volunteer')
            with open('.volunteer/volunteer_auth_info.json', 'w') as f:
                json.dump({
                    'token': data.get('token'),
                    'refresh_token': data.get('refresh_token'),
                    'username': full_info['username'],  # Ajouté pour le rafraîchissement
                    'password': full_info['password'],  # Ajouté pour le rafraîchissement
                    'last_login': time.time()
                }, f)
            logger.debug("Volontaire authentifié avec succès")
            from .task_handlers import TaskManager
            task_manager = TaskManager.get_instance()
            task_manager.start(volunteer_info.volunteer_id)
        else:
            logger.error(f"Échec de l'authentification du volontaire: {data}")
            return False
    else:
        logger.info("Cas 2 ou 3 : Volontaire non enregistré ou sans volunteer_id")
        full_info = collect_full_volunteer_info(volunteer_info)
        logger.info(f"[ENREGISTREMENT] Données envoyées au coordinateur via l'agent : name={full_info['hostname']}, ip_address={full_info['ip_address']}, cpu_cores={full_info['cpu_cores']}, ram_mb={full_info['ram_mb']}, disk_gb={full_info['disk_gb']}, username={full_info['username']}, password={full_info['password']}")
        
        success, data = register_volunteer(
            name=full_info['hostname'],
            ip_address=full_info['ip_address'],
            cpu_cores=full_info['cpu_cores'],
            ram_mb=full_info['ram_mb'],
            disk_gb=full_info['disk_gb'],
            username=full_info['username'],
            password=full_info['password'],
            machine_info=full_info['machine_info'],
        )
        if success:
            logger.info("Volontaire enregistré auprès du coordinateur avec succès")
            # Mettre à jour la BD locale (création ou update)
            def machine_info_from_raw(raw, username, password, volunteer_id=None):
                # Extraction et mapping de tous les champs du modèle
                return {
                    'volunteer_id': volunteer_id,
                    'adresse_mac': raw.get('adresse_mac', ''),
                    'username': username,
                    'password': password,
                    'os_name': raw.get('os', {}).get('nom', ''),
                    'os_version': raw.get('os', {}).get('version', ''),
                    'os_release': raw.get('os', {}).get('release', ''),
                    'os_architecture': raw.get('os', {}).get('architecture', ''),
                    'hostname': raw.get('os', {}).get('hostname', ''),
                    'machine_tipe': raw.get('tipe_machine', ''),
                    'cpu_modele': raw.get('cpu', {}).get('modele', ''),
                    'cpu_architecture': raw.get('cpu', {}).get('architecture', ''),
                    'cpu_bits': raw.get('cpu', {}).get('bits', ''),
                    'cpu_cores_physical': raw.get('cpu', {}).get('coeurs_physiques', 1),
                    'cpu_cores_logical': raw.get('cpu', {}).get('coeurs_logiques', 1),
                    'cpu_frequency_current': raw.get('cpu', {}).get('frequence', {}).get('actuelle', None),
                    'cpu_frequency_min': raw.get('cpu', {}).get('frequence', {}).get('min', None),
                    'cpu_frequency_max': raw.get('cpu', {}).get('frequence', {}).get('max', None),
                    'ram_total': _parse_size_to_bytes(raw.get('memoire', {}).get('ram', {}).get('total', '0 GB')),
                    'ram_total_human': raw.get('memoire', {}).get('ram', {}).get('total', '0 GB'),
                    'swap_total': _parse_size_to_bytes(raw.get('memoire', {}).get('swap', {}).get('total', '0 GB')),
                    'swap_total_human': raw.get('memoire', {}).get('swap', {}).get('total', '0 GB'),
                    'disk_total': _parse_size_to_bytes(raw.get('disque', {}).get('total', '0 GB')),
                    'disk_total_human': raw.get('disque', {}).get('total', '0 GB'),
                    'partitions': raw.get('partitions_disque', []),
                    'screen_resolution': raw.get('resolution_ecran', ''),
                    'network_interfaces': raw.get('interfaces_reseau', []),
                    'bios_info': raw.get('bios_carte_mere', {}).get('BIOS', {}),
                    'motherboard_info': raw.get('bios_carte_mere', {}).get('mother_board', {}),
                    'usb_devices': raw.get('peripheriques_usb', []),
                    'logged_users': raw.get('utilisateurs_connectes', []),
                    'last_update': timezone.now(),
                    'registration_date': datetime.now(),
                    'raw_data': raw,
                }
                
            if not volunteer_info:
                # Création complète avec tous les champs
                MachineInfo.objects.create(**machine_info_from_raw(full_info['machine_info'], full_info['username'], full_info['password'], data.get('volunteer_id')))

            else:
                # Update
                for k, v in full_info.items():
                    setattr(volunteer_info, k, v)
                volunteer_info.volunteer_id = data.get('volunteer_id')
                volunteer_info.registration_date = datetime.now()
                volunteer_info.save()
            
            # Sauvegarde info dict
            save_volunteer_info({
                'volunteer_id': data.get('volunteer_id'),
                'username': full_info['username'],
                'password': full_info['password'],
                'registration_date': time.time(),
                'token': data.get('token'),
                'refresh_token': data.get('refresh_token'),
                'last_login': time.time(),
                'machine_info': full_info['machine_info']
            })
            # Login immédiat
            success, data = login_volunteer(
                username=full_info['username'],
                password=full_info['password']
            )
            if success:
                logger.info("Volontaire authentifié avec succès")
                if not os.path.exists('.volunteer'):
                    os.makedirs('.volunteer')
                with open('.volunteer/volunteer_auth_info.json', 'w') as f:
                    json.dump({
                        'token': data.get('token'),
                        'refresh_token': data.get('refresh_token'),
                        'username': full_info['username'],  # Ajouté pour le rafraîchissement
                        'password': full_info['password'],  # Ajouté pour le rafraîchissement
                        'last_login': time.time()
                    }, f)
                logger.debug("Volontaire authentifié avec succès")
                return True
                
            else:
                logger.error(f"Échec de l'authentification du volontaire: {data.get('message')}")
                return False
        else:
            logger.error(f"Échec de l'enregistrement du volontaire: {data.get('message')}")
            return False
            
    
def start_communication_threads():
    """
    Démarre les threads de communication pour la collecte et l'envoi des données.
    Note: Le TaskManager est déjà démarré par auth_volunteer_flow() après le login.
    Cette fonction ne fait que créer le thread wrapper si nécessaire.
    """
    try:
        # Vérifier si le TaskManager est déjà démarré (par auth_volunteer_flow)
        from .task_handlers import TaskManager
        task_manager = TaskManager.get_instance()
        
        if task_manager.running:
            logger.debug("TaskManager déjà en cours d'exécution, pas de redémarrage nécessaire")
            return None
        
        # Thread d'écoute des tâches (seulement si pas déjà démarré)
        def task_listener_loop():
            try:
                # S'abonner aux canaux de tâches
                from .utils import get_volunteer_id
                volunteer_id = get_volunteer_id()
                if volunteer_id:
                    from .task_handlers import start_task_manager
                    start_task_manager(volunteer_id)
                    logger.info(f"Gestionnaire de tâches démarré pour le volontaire {volunteer_id}")
                else:
                    logger.warning("Le volontaire n'est pas encore enregistré; le gestionnaire de tâches ne sera pas démarré")
                
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle d'écoute des tâches: {e}")
        
        # Démarrer le thread d'écoute des tâches
        task_listener_thread = threading.Thread(target=task_listener_loop)
        task_listener_thread.daemon = True
        task_listener_thread.start()
        logger.info("Thread d'écoute des tâches démarré")
        
        return task_listener_thread
    except Exception as e:
        logger.error(f"Erreur lors du démarrage des threads de communication: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False







class RedisAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'redis_communication'
    verbose_name = "Communication Redis"
    redis_client = None
    volunteer_id = None
    volunteer_token = None
    data_collection_thread = None
    data_sending_thread = None
    availability_thread = None
    task_listener_thread = None
    username = None
    password = None
    
    # Stockage des données collectées
    static_data = None
    dynamic_data_history = []
    last_collection_time = None
    last_send_time = None
    
    def ready(self):
        """
        Initialise la connexion Redis et les threads de communication lorsque l'application démarre.
        """
        # Ne pas exécuter si volunteer_daemon.py est utilisé (il gère tout lui-même)
        is_daemon = 'volunteer_daemon' in sys.argv[0] or any('volunteer_daemon' in arg for arg in sys.argv)
        if is_daemon:
            logger.debug("Exécution via volunteer_daemon.py - initialisation déléguée au daemon")
            return
        
        # Ne pas exécuter en mode commande (sauf pour runserver ou daphne)
        if 'runserver' not in sys.argv and 'daphne' not in sys.argv[0]:
            return
        
        logger.info("===== Initialisation du service de communication Redis pour le volontaire =====")
        
        try:
            # Importer ici pour éviter les importations circulaires
            from .client import RedisClient
            from .handlers import DEFAULT_HANDLERS
            
            # Récupérer ou créer l'instance du client
            self.redis_client = RedisClient.get_instance()
            if not self.redis_client.running:
                self.redis_client.start()
            
            # Enregistrer les gestionnaires par défaut
            for channel, handler in DEFAULT_HANDLERS.items():
                self.redis_client.subscribe(channel, handler)
            
            # Démarrer le flux d'authentification du volontaire
            auth_volunteer_flow()

            
            # Démarrer les threads de communication
            if self.redis_client and self.redis_client.running:
                self.task_listener_thread = start_communication_threads()
            


            # Lancer la collecte continue des données
            agent_module = load_agent_module()
            if not agent_module:
                logger.error("Impossible de charger l'agent pour la collecte continue des données")
                return
            if hasattr(agent_module, 'continuous_collection'):
                threading.Thread(target=agent_module.continuous_collection, daemon=True).start()
                logger.info("Collecte continue des données via l'agent démarrée")
            else:
                logger.warning("La fonction 'continuous_collection()' est manquante dans l'agent")
                        
            logger.info("Application Redis Communication initialisée avec succès avec l'agent de collecte")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'application Redis: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
