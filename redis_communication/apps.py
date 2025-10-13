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
from .auth_client import save_volunteer_info, get_volunteer_info

# Configuration du logging pour afficher les messages dans la console
logger = logging.getLogger('redis_communication')
logger.setLevel(logging.DEBUG)

# Ajouter un gestionnaire de console si aucun n'existe déjà
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

# Répertoire pour stocker les informations du volontaire
VOLUNTEER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.volunteer')
os.makedirs(VOLUNTEER_DIR, exist_ok=True)

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

def convert_agent_data_to_legacy_format(agent_data):
    """
    Convertit les données de l'agent au format attendu par l'application legacy.
    
    Args:
        agent_data: Données provenant de l'agent
        
    Returns:
        dict: Données converties au format legacy
    """
    try:
        if not agent_data:
            return {}
            
        # Conversion des données statiques
        if 'cpu' in agent_data and 'memoire' in agent_data:
            # Format statique de l'agent -> format legacy
            return {
                'cpu_cores': agent_data.get('cpu', {}).get('coeurs_logiques', 1),
                'total_memory': agent_data.get('memoire', {}).get('ram', {}).get('total', '1 GB'),
                'total_disk': agent_data.get('disque', {}).get('total', '10 GB'),
                'hostname': agent_data.get('os', {}).get('hostname', socket.gethostname()),
                'os_name': agent_data.get('os', {}).get('nom', platform.system()),
                'machine_type': agent_data.get('type_machine', 'Indéterminé'),
                'raw_data': agent_data
            }
        else:
            # Format variable de l'agent -> format legacy
            return {
                'used_memory': 0,  # À calculer depuis le pourcentage
                'memory_usage': agent_data.get('memoire', {}).get('ram', {}).get('pourcentage_utilise', 0),
                'cache': 0,
                'swap_total': 0,
                'swap_used': 0,
                'swap_percentage': agent_data.get('memoire', {}).get('swap', {}).get('pourcentage_utilise', 0),
                'used_disk': 0,
                'disk_percentage': agent_data.get('disque', {}).get('pourcentage_utilise', 0),
                'cpu_usage_per_core': [core.get('utilisation', 0) for core in agent_data.get('cpu', {}).get('par_coeur', [])],
                'cpu_usage_average': agent_data.get('cpu', {}).get('global', 0),
                'gpu_usage_percentage': 0,
                'cpu_temperature': agent_data.get('cpu', {}).get('temperature', 0) or 0,
                'net_bytes_sent': 0,
                'net_bytes_received': 0,
                'battery_percentage': agent_data.get('batterie', {}).get('percent', 0) if isinstance(agent_data.get('batterie'), dict) else 0,
                'uptime': 0,
                'boot_time': time.time(),
                'internet_enabled': agent_data.get('connexion_internet', True),
                'timestamp': time.time(),
                'raw_data': agent_data
            }
    except Exception as e:
        logger.error(f"Erreur lors de la conversion des données: {e}")
        return {}

def handle_task_assignment(channel, message):
    """
    Gestionnaire pour les messages d'assignation de tâches.
    
    Args:
        channel: Canal sur lequel le message a été reçu
        message: Message reçu
    """
    logger.info(f"Message d'assignation de tâche reçu sur le canal {channel}")
    logger.debug(f"Contenu du message: {message.data}")
    
    try:
        # Vérifier si le message est destiné à ce volontaire
        volunteer_info = get_volunteer_info()
        volunteer_id = volunteer_info.get('volunteer_id')
        
        assignments = message.data.get('assignment', {})
        if volunteer_id in assignments:
            tasks = assignments[volunteer_id]
            logger.info(f"Tâches assignées à ce volontaire: {len(tasks)}")
            
            # Accepter chaque tâche
            for task in tasks:
                accept_task(task, volunteer_id, message.data.get('workflow_id'))
        else:
            logger.info("Aucune tâche assignée à ce volontaire")
    except Exception as e:
        logger.error(f"Erreur lors du traitement de l'assignation de tâche: {e}")
        import traceback
        logger.error(traceback.format_exc())

def accept_task(task, volunteer_id, workflow_id):
    """
    Accepte une tâche assignée et envoie une notification au coordinateur.
    
    Args:
        task: Informations sur la tâche
        volunteer_id: ID du volontaire
        workflow_id: ID du workflow
    """
    task_id = task.get('task_id')
    task_name = task.get('task_name')
    
    logger.info(f"Acceptation de la tâche {task_name} (ID: {task_id})")
    
    try:
        from .client import RedisClient
        client = RedisClient.get_instance()
        
        # Envoyer un message d'acceptation
        client.publish('task/accept', {
            'task_id': task_id,
            'volunteer_id': volunteer_id,
            'workflow_id': workflow_id,
            'status': 'accepted',
            'timestamp': time.time()
        })
        
        logger.info(f"Message d'acceptation envoyé pour la tâche {task_name}")
        
        # Simuler l'exécution de la tâche (à remplacer par l'exécution réelle)
        logger.info(f"Début de l'exécution de la tâche {task_name}...")
        time.sleep(5)  # Simulation d'une exécution
        logger.info(f"Tâche {task_name} exécutée avec succès")
        
        # Envoyer un message de complétion
        client.publish('task/complete', {
            'task_id': task_id,
            'volunteer_id': volunteer_id,
            'workflow_id': workflow_id,
            'status': 'completed',
            'result': {
                'success': True,
                'execution_time': 5,
                'output': f"Tâche {task_name} exécutée avec succès"
            },
            'timestamp': time.time()
        })
        
        logger.info(f"Message de complétion envoyé pour la tâche {task_name}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'acceptation/exécution de la tâche {task_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def publish_availability(volunteer_id):
    """
    Publie la disponibilité du volontaire sur le canal approprié.
    
    Args:
        volunteer_id: ID du volontaire
    """
    logger.info(f"Publication de la disponibilité du volontaire {volunteer_id}...")
    
    try:
        from .client import RedisClient
        client = RedisClient.get_instance()
        
        # Récupérer les informations de la machine via l'agent
        machine_info = get_machine_info()
        machine_state = get_machine_state()
        
        # Extraire les informations nécessaires
        cpu_cores = machine_info.get('cpu', {}).get('coeurs_logiques', 1)
        
        # Convertir la mémoire totale en MB
        ram_total_str = machine_info.get('memoire', {}).get('ram', {}).get('total', '1 GB')
        try:
            if 'GB' in ram_total_str:
                ram_mb = int(float(ram_total_str.split()[0]) * 1024)
            elif 'MB' in ram_total_str:
                ram_mb = int(float(ram_total_str.split()[0]))
            else:
                ram_mb = 1024  # Default 1GB
        except:
            ram_mb = 1024
        
        # Convertir le disque total en GB
        disk_total_str = machine_info.get('disque', {}).get('total', '10 GB')
        try:
            if 'GB' in disk_total_str:
                disk_gb = int(float(disk_total_str.split()[0]))
            elif 'TB' in disk_total_str:
                disk_gb = int(float(disk_total_str.split()[0]) * 1024)
            else:
                disk_gb = 10  # Default 10GB
        except:
            disk_gb = 10
        
        # Construire le message de disponibilité
        availability_message = {
            'volunteer_id': volunteer_id,
            'status': 'available',
            'timestamp': time.time(),
            'resources': {
                'cpu_cores': cpu_cores,
                'ram_mb': ram_mb,
                'disk_gb': disk_gb,
                'gpu': False  # À modifier si nécessaire
            },
            'usage': {
                'cpu': machine_state.get('cpu', {}).get('global', 0),
                'ram': machine_state.get('memoire', {}).get('ram', {}).get('pourcentage_utilise', 0),
                'disk': machine_state.get('disque', {}).get('pourcentage_utilise', 0)
            }
        }
        
        # Publier le message
        from .utils import get_volunteer_auth_token
        token = get_volunteer_auth_token()
        client.publish( 
            'volunteer/available',
            availability_message, 
            str(uuid.uuid4()),
            token,
            'request'
        )
                    
        logger.info(f"Disponibilité publiée pour le volontaire {volunteer_id}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la publication de la disponibilité: {e}")
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
        # Ne pas exécuter en mode commande (sauf pour runserver)
        if 'runserver' not in sys.argv and 'daphne' not in sys.argv[0]:
            return
        
        logger.info("===== Initialisation du service de communication Redis pour le volontaire =====")
        
        try:
            # Importer ici pour éviter les importations circulaires
            from .client import RedisClient
            from .handlers import DEFAULT_HANDLERS
            from .auth_client import register_volunteer, login_volunteer
            
            # Récupérer ou créer l'instance du client
            self.redis_client = RedisClient.get_instance()
            if not self.redis_client.running:
                self.redis_client.start()
            
            # Enregistrer les gestionnaires par défaut
            for channel, handler in DEFAULT_HANDLERS.items():
                self.redis_client.subscribe(channel, handler)
            
            # ========== Unification de la collecte et de l'enregistrement volontaire ==========
            from volontaire.models import MachineInfo
            
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

            logger.info("Vérification de l'enregistrement du volontaire...")
            volunteer_info = MachineInfo.objects.get_last_inserted()

            # Cas 1 : Volontaire déjà enregistré (avec volunteer_id)
            if volunteer_info and volunteer_info.volunteer_id:
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
                self.load_volunteer_credentials()
                logger.info(f"Connexion volontaire avec username={full_info['username']}")
                success, data = login_volunteer(
                    username=full_info['username'],
                    password=full_info['password']
                )
                if success:
                    logger.info("Volontaire authentifié avec succès")
                    self.volunteer_token = data.get('token')
                    if not os.path.exists('.volunteer'):
                        os.makedirs('.volunteer')
                    with open('.volunteer/volunteer_auth_info.json', 'w') as f:
                        json.dump({
                            'token': data.get('token'),
                            'refresh_token': data.get('refresh_token'),
                            'last_login': time.time()
                        }, f)
                    logger.debug("Volontaire authentifié avec succès")
                    from .task_handlers import TaskManager
                    task_manager = TaskManager.get_instance()
                    task_manager.start(volunteer_info.volunteer_id)
                else:
                    logger.error(f"Échec de l'authentification du volontaire: {data}")
            else:
                # Cas 2 ou 3 : Volontaire non enregistré ou sans volunteer_id
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
                            'machine_type': raw.get('type_machine', ''),
                            'cpu_type': raw.get('cpu', {}).get('type', ''),
                            'cpu_architecture': raw.get('cpu', {}).get('architecture', ''),
                            'cpu_bits': raw.get('cpu', {}).get('bits', ''),
                            'cpu_cores_physical': raw.get('cpu', {}).get('coeurs_physiques', 1),
                            'cpu_cores_logical': raw.get('cpu', {}).get('coeurs_logiques', 1),
                            'cpu_frequency_current': raw.get('cpu', {}).get('frequence', {}).get('actuelle', None),
                            'cpu_frequency_min': raw.get('cpu', {}).get('frequence', {}).get('min', None),
                            'cpu_frequency_max': raw.get('cpu', {}).get('frequence', {}).get('max', None),
                            'ram_total': self._parse_size_to_bytes(raw.get('memoire', {}).get('ram', {}).get('total', '0 GB')),
                            'ram_total_human': raw.get('memoire', {}).get('ram', {}).get('total', '0 GB'),
                            'swap_total': self._parse_size_to_bytes(raw.get('memoire', {}).get('swap', {}).get('total', '0 GB')),
                            'swap_total_human': raw.get('memoire', {}).get('swap', {}).get('total', '0 GB'),
                            'disk_total': self._parse_size_to_bytes(raw.get('disque', {}).get('total', '0 GB')),
                            'disk_total_human': raw.get('disque', {}).get('total', '0 GB'),
                            'partitions': raw.get('partitions_disque', []),
                            'screen_resolution': raw.get('resolution_ecran', ''),
                            'network_interfaces': raw.get('interfaces_reseau', []),
                            'bios_info': raw.get('bios_carte_mere', {}).get('BIOS', {}),
                            'motherboard_info': raw.get('bios_carte_mere', {}).get('Carte mère', {}),
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
                    # Sauvegarde fichier local
                    if not os.path.exists('.volunteer'):
                        os.makedirs('.volunteer')
                    with open('.volunteer/volunteer_info.json', 'w') as f:
                        json.dump({
                            'volunteer_id': data.get('volunteer_id'),
                            'token': data.get('token'),
                            'refresh_token': data.get('refresh_token'),
                            'last_login': time.time()
                        }, f)
                    # Sauvegarde info dict
                    save_volunteer_info({
                        'volunteer_id': data.get('volunteer_id'),
                        'username': full_info['username'],
                        'password': full_info['password'],
                        'registration_date': time.time(),
                        'machine_info': full_info['machine_info']
                    })
                    self.volunteer_id = data.get('volunteer_id')
                    # Login immédiat
                    success, data = login_volunteer(
                        username=full_info['username'],
                        password=full_info['password']
                    )
                    if success:
                        logger.info("Volontaire authentifié avec succès")
                        self.volunteer_id = data.get('volunteer_id')
                        self.volunteer_token = data.get('token')
                        if not os.path.exists('.volunteer'):
                            os.makedirs('.volunteer')
                        with open('.volunteer/volunteer_auth_info.json', 'w') as f:
                            json.dump({
                                'token': data.get('token'),
                                'refresh_token': data.get('refresh_token'),
                                'last_login': time.time()
                            }, f)
                        logger.debug("Volontaire authentifié avec succès")
                        
                        from .task_handlers import TaskManager
                        task_manager = TaskManager.get_instance()
                        task_manager.start(self.volunteer_id)
                    else:
                        logger.error(f"Échec de l'authentification du volontaire: {data.get('message')}")
                else:
                    logger.error(f"Échec de l'enregistrement du volontaire: {data.get('message')}")
            
            # Charger les identifiants du volontaire (si enregistré)
            self.load_volunteer_credentials()
            
            # Démarrer les threads de communication
            self.start_communication_threads()
            
            # Initialiser le gestionnaire de tâches si le volontaire est enregistré
            if self.volunteer_id:
                from .task_handlers import start_task_manager
                self.task_manager = start_task_manager(self.volunteer_id)
                logger.info(f"Gestionnaire de tâches démarré pour le volontaire {self.volunteer_id}")
            

            # Lancer la collecte continue des données
            agent_module = load_agent_module()
            if not agent_module:
                logger.error("Impossible de charger l'agent pour la collecte continue des données")
                return
            if hasattr(agent_module, 'continuous_collection'):
                agent_module.continuous_collection()
                logger.info("Collecte continue des données via l'agent démarrée")
            else:
                logger.warning("La fonction 'continuous_collection()' est manquante dans l'agent")
                        
            logger.info("Application Redis Communication initialisée avec succès avec l'agent de collecte")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'application Redis: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _parse_size_to_bytes(self, size_str):
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
    
    def load_volunteer_credentials(self):
        """
        Charge les identifiants du volontaire depuis le fichier de configuration.
        """
        try:
            volunteer_info = get_volunteer_info()
            if volunteer_info:
                self.volunteer_id = volunteer_info.get('volunteer_id')
                self.volunteer_token = volunteer_info.get('token')
                self.volunteer_refresh_token = volunteer_info.get('refresh_token')
                self.username = volunteer_info.get('username')
                self.password = volunteer_info.get('password')
                logger.info(f"Identifiants du volontaire chargés avec succès: ID={self.volunteer_id}")
            else:
                logger.warning("Aucun identifiant de volontaire trouvé, l'enregistrement sera nécessaire")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des identifiants du volontaire: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    def collect_static_data(self):
        """
        Collecte les informations statiques de la machine via l'agent et les stocke dans la base de données.
        """
        try:
            logger.info("Collecte des informations statiques de la machine via l'agent...")
            self.static_data = get_machine_info()
            
            if not self.static_data:
                logger.error("Échec de la collecte des informations statiques via l'agent")
                return
            
            logger.info("Sauvegarde des informations statiques dans la base de données...")
            
            # Importer les modèles ici pour éviter les importations circulaires
            from volontaire.models import MachineInfo
            
            # Créer ou mettre à jour les informations de la machine
            if self.volunteer_id:
                machine_info, created = MachineInfo.objects.get_or_create(
                    volunteer_id=self.volunteer_id,
                    defaults={
                        'adresse_mac': self.static_data.get('adresse_mac', ''),
                        'machine_type': self.static_data.get('type_machine', 'Indéterminé'),
                        'system': self.static_data.get('os', {}).get('nom', ''),
                        'node_name': self.static_data.get('os', {}).get('hostname', ''),
                        'host_name': self.static_data.get('os', {}).get('hostname', ''),
                        'os_release': self.static_data.get('os', {}).get('release', ''),
                        'os_version': self.static_data.get('os', {}).get('version', ''),
                        'machine_arch': self.static_data.get('cpu', {}).get('architecture', ''),
                        'processor_name': self.static_data.get('cpu', {}).get('type', ''),
                        'cpu_type': self.static_data.get('cpu', {}).get('type', ''),
                        'cpu_cores': self.static_data.get('cpu', {}).get('coeurs_physiques', 1),
                        'cpu_logical_cores': self.static_data.get('cpu', {}).get('coeurs_logiques', 1),
                        'cpu_frequency': self.static_data.get('cpu', {}).get('frequence', {}).get('max', 0),
                        'total_memory': self._parse_size_to_bytes(self.static_data.get('memoire', {}).get('ram', {}).get('total', '0 GB')),
                        'screen_resolution': self.static_data.get('resolution_ecran', 'unknown'),
                        'total_disk': self._parse_size_to_bytes(self.static_data.get('disque', {}).get('total', '0 GB')),
                        'name': f"Volunteer-{self.static_data.get('os', {}).get('hostname', 'unknown')}",
                        'raw_data': self.static_data
                    }
                )
                
                if not created:
                    # Mettre à jour quelques champs qui peuvent changer
                    machine_info.host_name = self.static_data.get('os', {}).get('hostname', '')
                    machine_info.name = f"Volunteer-{self.static_data.get('os', {}).get('hostname', 'unknown')}"
                    machine_info.save(update_fields=['host_name', 'name'])
                
                logger.info(f"{'Créé' if created else 'Mis à jour'} les informations de la machine dans la base de données")
            else:
                logger.warning("Impossible de sauvegarder les informations de la machine sans volunteer_id")
        except Exception as e:
            logger.error(f"Erreur lors de la collecte et sauvegarde des informations statiques: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def collect_dynamic_data(self):
        """
        Collecte les données dynamiques de la machine via l'agent et les stocke dans la base de données.
        """
        try:
            logger.info("Collecte des données dynamiques de la machine via l'agent...")
            dynamic_data = get_machine_state()
            
            if not dynamic_data:
                logger.error("Échec de la collecte des données dynamiques via l'agent")
                return
            
            # Ajouter les données à l'historique
            self.dynamic_data_history.append(dynamic_data)
            
            # Limiter la taille de l'historique
            max_history_size = 60  # Conserver l'historique des 60 dernières minutes
            if len(self.dynamic_data_history) > max_history_size:
                self.dynamic_data_history = self.dynamic_data_history[-max_history_size:]
            
            # Mettre à jour le timestamp de dernière collecte
            self.last_collection_time = datetime.now()
            
            # Sauvegarder les données dans la base de données
            if self.volunteer_id:
                # Importer les modèles ici pour éviter les importations circulaires
                from volontaire.models import MachineInfo, EtatMachine
                
                try:
                    # Récupérer l'instance MachineInfo
                    machine_info = MachineInfo.objects.get(volunteer_id=self.volunteer_id)
                    
                    # Créer une nouvelle instance EtatMachine
                    etat = EtatMachine.objects.create(
                        machine=machine_info,
                        timestamp=timezone.now(),
                        cpu_usage=dynamic_data.get('cpu', {}).get('global', 0),
                        used_memory=0,  # À calculer si nécessaire
                        memory_usage=dynamic_data.get('memoire', {}).get('ram', {}).get('pourcentage_utilise', 0),
                        used_disk=dynamic_data.get('disque', {}).get('pourcentage_utilise', 0),
                        temperature=dynamic_data.get('cpu', {}).get('temperature', 0) or 0,
                        network_sent=dynamic_data.get('reseau', {}).get('octets_envoyes', '0 B'),
                        network_received=dynamic_data.get('reseau', {}).get('octets_recus', '0 B'),
                        is_online=dynamic_data.get('connexion_internet', False),
                        battery_level=dynamic_data.get('batterie', {}).get('percent', 0) if isinstance(dynamic_data.get('batterie'), dict) else 0,
                        uptime=0  # À calculer si nécessaire
                    )
                    
                    logger.info(f"Données dynamiques sauvegardées dans la base de données avec ID {etat.id}")
                except MachineInfo.DoesNotExist:
                    logger.error(f"Impossible de trouver la machine avec volunteer_id={self.volunteer_id}")
                except Exception as e:
                    logger.error(f"Erreur lors de la sauvegarde des données dynamiques: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.warning("Impossible de sauvegarder les données dynamiques sans volunteer_id")
            
            return dynamic_data
        except Exception as e:
            logger.error(f"Erreur lors de la collecte des données dynamiques: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def send_data_to_coordinator(self):
        """
        Envoie les données collectées au coordinateur via Redis.
        """
        try:
            if not self.redis_client or not self.volunteer_id or not self.volunteer_token:
                logger.warning("Impossible d'envoyer les données au coordinateur: client Redis ou identifiants manquants")
                return False
            
            # Préparer les données à envoyer
            data_to_send = {
                'volunteer_id': self.volunteer_id,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'dynamic_data': self.dynamic_data_history[-1] if self.dynamic_data_history else None
            }
            
            # Envoyer les données au coordinateur
            channel = "volunteer/data"
            from .utils import get_volunteer_auth_token
            success = self.redis_client.publish(channel, 
                                                json.dumps(data_to_send), 
                                                str(uuid.uuid4()), 
                                                get_volunteer_auth_token(),
                                                'request'
                                                )
            
            if success:
                logger.info(f"Données envoyées au coordinateur sur le canal {channel}")
                self.last_send_time = datetime.now()
                return True
            else:
                logger.error("Erreur lors de l'envoi des données au coordinateur")
                return False
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des données au coordinateur: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def start_communication_threads(self):
        """
        Démarre les threads de communication pour la collecte et l'envoi des données.
        """
        try:
            # Thread d'écoute des tâches
            def task_listener_loop():
                try:
                    if self.redis_client and self.volunteer_id:
                        # S'abonner aux canaux de tâches
                        from .task_handlers import task_assignment_handler, task_cancel_handler
                        
                        # Canal général d'assignation des tâches
                        self.redis_client.subscribe('task/assignment', task_assignment_handler)
                        logger.info("Abonné au canal d'assignation des tâches")
                        
                        # Canal d'annulation des tâches
                        self.redis_client.subscribe('task/cancel', task_cancel_handler)
                        logger.info("Abonné au canal d'annulation des tâches")
                    
                except Exception as e:
                    logger.error(f"Erreur dans la boucle d'écoute des tâches: {e}")
            
            # Démarrer le thread d'écoute des tâches
            self.task_listener_thread = threading.Thread(target=task_listener_loop)
            self.task_listener_thread.daemon = True
            self.task_listener_thread.start()
            logger.info("Thread d'écoute des tâches démarré")
            
            return True
        except Exception as e:
            logger.error(f"Erreur lors du démarrage des threads de communication: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
