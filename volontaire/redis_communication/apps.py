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
        # Essayer de charger et utiliser l'agent
        agent_module = load_agent_module()
        if agent_module and hasattr(agent_module, 'collect_initial_data'):
            logger.info("Utilisation de l'agent pour collecter les données statiques")
            static_data = agent_module.collect_initial_data()
            logger.info("Données statiques collectées avec succès via l'agent")
            return static_data
        
        # Fallback: collecter les informations manuellement
        logger.warning("Impossible d'utiliser l'agent, collecte manuelle des informations statiques")
        
        # Récupérer les adresses MAC
        macs = []
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family.name == 'AF_LINK' or snic.family == psutil.AF_LINK:
                    macs.append(snic.address)
        
        # Récupérer la résolution d'écran
        resolution = "unknown"
        try:
            import subprocess
            output = subprocess.check_output(['xrandr']).decode()
            for line in output.splitlines():
                if '*' in line:
                    resolution = line.split()[0]  # ex: '1920x1080'
        except Exception as e:
            logger.warning(f"Impossible de récupérer la résolution d'écran: {e}")
        
        # Informations sur le système d'exploitation
        os_info = {
            "nom": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "hostname": platform.node()
        }
        
        # Informations sur le processeur
        cpu_info = {
            "type": platform.processor(),
            "architecture": platform.machine(),
            "bits": "64-bit" if platform.machine().endswith('64') else "32-bit",
            "coeurs_physiques": psutil.cpu_count(logical=False) or 1,
            "coeurs_logiques": psutil.cpu_count(logical=True) or 1,
            "frequence": {
                "actuelle": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                "min": psutil.cpu_freq().min if psutil.cpu_freq() and hasattr(psutil.cpu_freq(), 'min') else None,
                "max": psutil.cpu_freq().max if psutil.cpu_freq() and hasattr(psutil.cpu_freq(), 'max') else None
            }
        }
        
        # Informations sur la mémoire
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        memory_info = {
            "ram": {
                "total": memory.total,
                "total_human": bytes_to_human_readable(memory.total),
                "disponible": memory.available,
                "disponible_human": bytes_to_human_readable(memory.available),
                "utilisee": memory.used,
                "utilisee_human": bytes_to_human_readable(memory.used),
                "pourcentage_utilise": memory.percent,
                "pourcentage_libre": 100 - memory.percent
            },
            "swap": {
                "total": swap.total,
                "total_human": bytes_to_human_readable(swap.total),
                "disponible": swap.free,
                "disponible_human": bytes_to_human_readable(swap.free),
                "utilisee": swap.used,
                "utilisee_human": bytes_to_human_readable(swap.used),
                "pourcentage_utilise": swap.percent,
                "pourcentage_libre": 100 - swap.percent
            },
            "cache": {
                "total": memory.cached if hasattr(memory, 'cached') else 0,
                "total_human": bytes_to_human_readable(memory.cached) if hasattr(memory, 'cached') else "Non disponible",
                "pourcentage": (memory.cached / memory.total * 100) if hasattr(memory, 'cached') and memory.total > 0 else 0
            }
        }
        
        # Informations sur le disque
        disk = psutil.disk_usage('/')
        disk_info = {
            "total": disk.total,
            "total_human": bytes_to_human_readable(disk.total),
            "disponible": disk.free,
            "disponible_human": bytes_to_human_readable(disk.free),
            "utilise": disk.used,
            "utilise_human": bytes_to_human_readable(disk.used),
            "pourcentage_utilise": disk.percent,
            "pourcentage_libre": 100 - disk.percent
        }
        
        # Construire le dictionnaire final
        static_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "os": os_info,
            "type_machine": get_machine_type(),
            "cpu": cpu_info,
            "memoire": memory_info,
            "disque": disk_info,
            "adresse_mac": macs[0] if macs else "00:00:00:00:00:00",
            "resolution_ecran": resolution,
            "interfaces_reseau": get_network_interfaces(),
            "partitions_disque": get_disk_partitions()
        }
        
        logger.info("Informations statiques collectées manuellement avec succès")
        return static_data
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
        # Essayer de charger et utiliser l'agent
        agent_module = load_agent_module()
        if agent_module and hasattr(agent_module, 'collect_variable_data'):
            logger.info("Utilisation de l'agent pour collecter les données variables")
            variable_data = agent_module.collect_variable_data()
            logger.info("Données variables collectées avec succès via l'agent")
            return variable_data
        
        # Fallback: collecter les informations manuellement
        logger.warning("Impossible d'utiliser l'agent, collecte manuelle des informations variables")
        
        # CPU
        cpu_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
        cpu_cores_data = []
        for i, usage in enumerate(cpu_per_core):
            cpu_cores_data.append({
                "core": i,
                "utilisation": usage,
                "libre": 100 - usage
            })
        
        # Température CPU
        cpu_temp = get_cpu_temperature()
        
        # Mémoire
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Disque
        disk = psutil.disk_usage('/')
        
        # GPU (si disponible)
        gpu_usage = get_gpu_usage()
        
        # Réseau
        net_io_counters = psutil.net_io_counters()
        
        # Connexion Internet
        internet_connected = is_internet_connected()
        
        # Nombre de processus
        process_count = len(psutil.pids())
        
        # Batterie
        battery_info = get_battery_percentage()
        
        # Uptime
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_str = str(timedelta(seconds=uptime_seconds))
        
        # Assembler les données variables
        variable_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu": {
                "global": sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0,
                "par_coeur": cpu_cores_data,
                "temperature": cpu_temp
            },
            "memoire": {
                "ram": {
                    "pourcentage_utilise": memory.percent,
                    "pourcentage_libre": 100 - memory.percent,
                    "utilisee": bytes_to_human_readable(memory.used),
                    "disponible": bytes_to_human_readable(memory.available)
                },
                "swap": {
                    "pourcentage_utilise": swap.percent,
                    "pourcentage_libre": 100 - swap.percent,
                    "utilisee": bytes_to_human_readable(swap.used),
                    "disponible": bytes_to_human_readable(swap.free)
                },
                "cache": {
                    "utilisee": bytes_to_human_readable(memory.cached) if hasattr(memory, 'cached') else "Non disponible"
                }
            },
            "disque": {
                "pourcentage_utilise": disk.percent,
                "pourcentage_libre": 100 - disk.percent
            },
            "gpu_utilisation": gpu_usage,
            "reseau": {
                "octets_envoyes": bytes_to_human_readable(net_io_counters.bytes_sent),
                "octets_recus": bytes_to_human_readable(net_io_counters.bytes_recv),
                "paquets_envoyes": net_io_counters.packets_sent,
                "paquets_recus": net_io_counters.packets_recv,
                "erreurs_reception": net_io_counters.errin,
                "erreurs_envoi": net_io_counters.errout,
                "paquets_supprimes_reception": net_io_counters.dropin,
                "paquets_supprimes_envoi": net_io_counters.dropout
            },
            "connexion_internet": internet_connected,
            "nombre_processus": process_count,
            "batterie": battery_info if battery_info else "Non disponible",
            "uptime": uptime_str,
            "uptime_seconds": int(uptime_seconds)
        }
        
        logger.info("Informations variables collectées manuellement avec succès")
        return variable_data
    except Exception as e:
        logger.error(f"Erreur lors de la collecte des informations variables: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

# Fonctions utilitaires pour la collecte manuelle des données
def bytes_to_human_readable(bytes_value):
    """
    Convertit un nombre d'octets en format lisible par un humain.
    """
    if bytes_value is None:
        return "Non disponible"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0 or unit == 'PB':
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0

def get_machine_type():
    """
    Détermine si la machine est un ordinateur de bureau, un portable, etc.
    """
    system = platform.system()
    if system == "Linux":
        # Vérifier si c'est un portable sur Linux
        if os.path.exists("/sys/class/power_supply/BAT0") or os.path.exists("/sys/class/power_supply/BAT1"):
            return "Portable"
        if "Macbook" in platform.node() or "MacBook" in platform.node():
            return "MacBook"
        return "PC de bureau"
    elif system == "Windows":
        # Vérifier si c'est un portable sur Windows
        if hasattr(psutil, "sensors_battery") and psutil.sensors_battery():
            return "Portable"
        return "PC de bureau"
    elif system == "Darwin":
        try:
            import subprocess
            model = subprocess.getoutput("sysctl -n hw.model")
            if "MacBook" in model:
                return "MacBook"
            elif "iMac" in model:
                return "iMac"
            else:
                return "Mac"
        except:
            return "Mac"
    else:
        return "Indéterminé"

def get_cpu_temperature():
    """
    Récupère la température du CPU si disponible.
    """
    try:
        if platform.system() == "Linux":
            try:
                # Essayer avec sensors
                output = subprocess.check_output(["sensors"], universal_newlines=True)
                for line in output.split("\n"):
                    if "Core" in line and "°C" in line:
                        return float(line.split("+")[1].split("°C")[0].strip())
            except:
                try:
                    # Essayer avec la lecture directe des fichiers système
                    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                        return float(f.read().strip()) / 1000.0
                except:
                    pass
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la température CPU: {e}")
    return None

def get_battery_percentage():
    """
    Récupère le pourcentage de batterie si disponible.
    """
    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secsleft": str(timedelta(seconds=battery.secsleft)) if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "Illimité"
            }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des informations de batterie: {e}")
    return None

def get_gpu_usage():
    """
    Récupère l'utilisation du GPU si disponible.
    """
    try:
        if platform.system() == "Windows":
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    return [{
                        "id": gpu.id,
                        "name": gpu.name,
                        "load": gpu.load * 100,
                        "memory_total": gpu.memoryTotal,
                        "memory_used": gpu.memoryUsed,
                        "temperature": gpu.temperature
                    } for gpu in gpus]
            except ImportError:
                pass
        elif platform.system() == "Linux":
            try:
                # Essayer avec nvidia-smi pour les GPU NVIDIA
                output = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"], universal_newlines=True)
                gpus = []
                for i, line in enumerate(output.strip().split("\n")):
                    values = line.split(", ")
                    if len(values) >= 4:
                        gpus.append({
                            "id": i,
                            "name": f"GPU {i}",
                            "load": float(values[0]),
                            "memory_used": float(values[1]),
                            "memory_total": float(values[2]),
                            "temperature": float(values[3])
                        })
                if gpus:
                    return gpus
            except:
                pass
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'utilisation GPU: {e}")
    return None

def is_internet_connected():
    """
    Vérifie si l'ordinateur est connecté à Internet.
    """
    try:
        # Tentative de connexion à Google DNS
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        pass
    return False

def get_network_interfaces():
    """
    Récupère les informations sur les interfaces réseau.
    """
    network_interfaces = []
    try:
        for interface_name, interface_addresses in psutil.net_if_addrs().items():
            interface_info = {
                "name": interface_name,
                "addresses": []
            }
            
            for addr in interface_addresses:
                address_info = {
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast
                }
                interface_info["addresses"].append(address_info)
            
            # Ajouter les statistiques de l'interface si disponibles
            if interface_name in psutil.net_if_stats():
                stats = psutil.net_if_stats()[interface_name]
                interface_info["isup"] = stats.isup
                interface_info["speed"] = stats.speed
                interface_info["duplex"] = stats.duplex
                interface_info["mtu"] = stats.mtu
            
            network_interfaces.append(interface_info)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des interfaces réseau: {e}")
    
    return network_interfaces

def get_disk_partitions():
    """
    Récupère les informations sur les partitions de disque.
    """
    partitions = []
    
    try:
        for part in psutil.disk_partitions(all=True):
            partition_info = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "opts": part.opts
            }
            
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partition_info.update({
                    "total": bytes_to_human_readable(usage.total),
                    "used": bytes_to_human_readable(usage.used),
                    "free": bytes_to_human_readable(usage.free),
                    "percent_used": usage.percent,
                    "percent_free": 100 - usage.percent
                })
            except (PermissionError, FileNotFoundError):
                # Certaines partitions peuvent ne pas être accessibles
                partition_info.update({
                    "total": "0.00 B",
                    "used": "0.00 B",
                    "free": "0.00 B",
                    "percent_used": 0.0,
                    "percent_free": 100.0
                })
            
            partitions.append(partition_info)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des partitions de disque: {e}")
    
    return partitions

def get_machine_state():
    """
    Récupère l'état actuel de la machine du volontaire.
    
    Returns:
        dict: État actuel de la machine
    """
    logger.info("Collecte de l'état actuel de la machine...")
    try:
        # Mémoire
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Disque
        disk = psutil.disk_usage("/")
        
        # CPU
        cpu_usage_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
        
        # Réseau
        net_io = psutil.net_io_counters()
        
        # Batterie
        battery_percentage = 0
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_percentage = battery.percent
        except:
            pass
        
        # Construire le dictionnaire d'état
        state = {
            "used_memory": mem.used,
            "memory_usage": mem.percent,
            "cache": mem.cached,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percentage": swap.percent,
            "used_disk": disk.used,
            "disk_percentage": disk.percent,
            "cpu_usage_per_core": cpu_usage_per_core,
            "cpu_usage_average": sum(cpu_usage_per_core) / len(cpu_usage_per_core),
            "gpu_usage_percentage": 0,  # À implémenter si nécessaire
            "cpu_temperature": 0,  # À implémenter si nécessaire
            "net_bytes_sent": net_io.bytes_sent,
            "net_bytes_received": net_io.bytes_recv,
            "battery_percentage": battery_percentage,
            "uptime": int(time.time() - psutil.boot_time()),
            "boot_time": psutil.boot_time(),
            "internet_enabled": True,  # Supposé vrai si on peut communiquer
            "timestamp": time.time()
        }
        
        logger.info("État de la machine collecté avec succès")
        return state
    except Exception as e:
        logger.error(f"Erreur lors de la collecte de l'état de la machine: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        token: Token du volontaire
    """
    logger.info(f"Publication de la disponibilité du volontaire {volunteer_id}...")
    
    try:
        from .client import RedisClient
        client = RedisClient.get_instance()
        
        # Récupérer les informations de la machine
        machine_info = get_machine_info()
        machine_state = get_machine_state()
        
        # Construire le message de disponibilité
        availability_message = {
            'volunteer_id': volunteer_id,
            'status': 'available',
            'timestamp': time.time(),
            'resources': {
                'cpu_cores': machine_info.get('cpu_cores', 1),
                'ram_mb': machine_info.get('total_memory', 1024) // (1024 * 1024),
                'disk_gb': machine_info.get('total_disk', 10 * 1024 * 1024 * 1024) // (1024 * 1024 * 1024),
                'gpu': False  # À modifier si nécessaire
            },
            'usage': {
                'cpu': machine_state.get('cpu_usage_average', 0),
                'ram': machine_state.get('memory_usage', 0),
                'disk': machine_state.get('disk_percentage', 0)
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
        if 'runserver' not in sys.argv and 'daphne' not in sys.argv[0]:
            return

        logger.info("===== Initialisation du service de communication Redis pour le volontaire =====")
        bootstrap = threading.Thread(
            target=self._bootstrap_redis_service,
            name='volunteer-redis-bootstrap',
            daemon=True,
        )
        bootstrap.start()

    def _bootstrap_redis_service(self):
        """Connexion coordinateur + enregistrement/auth en arrière-plan (ne bloque pas Daphne)."""
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
                static_data = get_machine_info()
                logger.info(f"Données statiques collectées: {static_data['disque']}, {static_data['memoire']}")
                from .utils import get_local_ip
                ip_address = get_local_ip()
                hostname = static_data.get('os', {}).get('hostname', socket.gethostname())
                cpu_cores = int(static_data.get('cpu', {}).get('coeurs_logiques', 1))
                total_memory = static_data.get('memoire', {}).get('ram', {}).get('total', '0 GB')
                try:
                    ram_mb = float(total_memory.split(' ')[0])
                except:
                    ram_mb = 1  # Default to 1 GB if parsing fails

                total_disk = static_data.get('disque', {}).get('total', '0 GB')
                try:
                    disk_gb = float(total_disk.split(' ')[0])
                except:
                    disk_gb = 10  # Default to 10 GB if parsing fails
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
                # Toujours enrichir les données locales si besoin
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
                logger.info(f"[ENREGISTREMENT] Données envoyées au coordinateur : name={full_info['hostname']}, ip_address={full_info['ip_address']}, cpu_cores={full_info['cpu_cores']}, ram_mb={full_info['ram_mb']}, disk_gb={full_info['disk_gb']}, username={full_info['username']}, password={full_info['password']}")
                
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
                    logger.info("Volontaire enregistré aupres du coordinateur avec succès")
                    # Mettre à jour la BD locale (création ou update)
                    def machine_info_from_raw(raw, username, password, volunteer_id=None):
                        # Extraction et mapping de tous les champs du modèle
                        return {
                            'volunteer_id': volunteer_id,
                            'adresse_mac': raw.get('reseau', {}).get('mac', []),
                            'username': username,
                            'password': password,
                            'os_name': raw.get('os', {}).get('nom', ''),
                            'os_version': raw.get('os', {}).get('version', ''),
                            'os_release': raw.get('os', {}).get('release', ''),
                            'os_architecture': raw.get('os', {}).get('architecture', ''),
                            'hostname': raw.get('hostname', ''),
                            'machine_type': raw.get('machine_type', ''),
                            'cpu_type': raw.get('cpu', {}).get('type', ''),
                            'cpu_architecture': raw.get('cpu', {}).get('architecture', ''),
                            'cpu_bits': raw.get('cpu', {}).get('bits', ''),
                            'cpu_cores_physical': raw.get('cpu', {}).get('coeurs_physiques', 1),
                            'cpu_cores_logical': raw.get('cpu', {}).get('coeurs_logiques', 1),
                            'cpu_frequency_current': raw.get('cpu', {}).get('frequence_courante', None),
                            'cpu_frequency_min': raw.get('cpu', {}).get('frequence_min', None),
                            'cpu_frequency_max': raw.get('cpu', {}).get('frequence_max', None),
                            'ram_total': float(raw.get('memoire', {}).get('ram', {}).get('total', 0).split(' ')[0]) * 1024 * 1024,
                            'ram_total_human': raw.get('memoire', {}).get('ram', {}).get('total_human', '0'),
                            'swap_total': float(raw.get('memoire', {}).get('swap', {}).get('total', 0).split(' ')[0]) * 1024 * 1024,
                            'swap_total_human': raw.get('memoire', {}).get('swap', {}).get('total_human', '0'),
                            'disk_total': float(raw.get('disque', {}).get('total', 0).split(' ')[0]) * 1024 * 1024,
                            'disk_total_human': raw.get('disque', {}).get('total_human', '0'),
                            'partitions': raw.get('disque', {}).get('partitions', []),
                            'screen_resolution': raw.get('ecran', {}).get('resolution', ''),
                            'network_interfaces': raw.get('reseau', {}).get('interfaces', []),
                            'bios_info': raw.get('bios', {}),
                            'motherboard_info': raw.get('carte_mere', {}),
                            'usb_devices': raw.get('usb', []),
                            'logged_users': raw.get('utilisateurs', []),
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
            
            logger.info("Application Redis Communication initialisée avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'application Redis: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
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
        Collecte les informations statiques de la machine et les stocke dans la base de données.
        """
        try:
            logger.info("Collecte des informations statiques de la machine...")
            self.static_data = get_machine_info()
            
            if not self.static_data:
                logger.error("Échec de la collecte des informations statiques")
                return
            
            logger.info("Sauvegarde des informations statiques dans la base de données...")
            
            # Importer les modèles ici pour éviter les importations circulaires
            from volontaire.models import MachineInfo
            
            # Créer ou mettre à jour les informations de la machine
            if self.volunteer_id:
                machine_info, created = MachineInfo.objects.get_or_create(
                    volunteer_id=self.volunteer_id,
                    defaults={
                        'adresse_mac': self.static_data.get('adresse_mac', []),
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
                        'total_memory': self.static_data.get('memoire', {}).get('ram', {}).get('total', 0),
                        'screen_resolution': self.static_data.get('resolution_ecran', 'unknown'),
                        'total_disk': self.static_data.get('disque', {}).get('total', 0),
                        'name': f"Volunteer-{self.static_data.get('os', {}).get('hostname', 'unknown')}",
                        'raw_data': self.static_data
                    }
                )
                
                if not created:
                    # Ne pas mettre à jour les caractéristiques statiques qui ne devraient pas changer
                    # Mais mettre à jour les caractéristiques qui pourraient changer (comme le nom d'hôte)
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
        Collecte les données dynamiques de la machine et les stocke dans la base de données.
        """
        try:
            logger.info("Collecte des données dynamiques de la machine...")
            dynamic_data = get_machine_state()
            
            if not dynamic_data:
                logger.error("Échec de la collecte des données dynamiques")
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
                        used_memory=dynamic_data.get('memoire', {}).get('ram', {}).get('utilisee', 0),
                        memory_usage=dynamic_data.get('memoire', {}).get('ram', {}).get('pourcentage_utilise', 0),
                        used_disk=dynamic_data.get('disque', {}).get('pourcentage_utilise', 0),
                        temperature=dynamic_data.get('cpu', {}).get('temperature', 0),
                        network_sent=dynamic_data.get('reseau', {}).get('octets_envoyes', '0 B'),
                        network_received=dynamic_data.get('reseau', {}).get('octets_recus', '0 B'),
                        is_online=dynamic_data.get('connexion_internet', False),
                        battery_level=dynamic_data.get('batterie', {}).get('percent', 0) if isinstance(dynamic_data.get('batterie'), dict) else 0,
                        uptime=dynamic_data.get('uptime_seconds', 0)
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
            # Thread de collecte des données
            def data_collection_loop():
                while True:
                    try:
                        # Collecter les données dynamiques
                        self.collect_dynamic_data()
                        
                        # Attendre l'intervalle de collecte
                        time.sleep(COLLECTION_INTERVAL)
                    except Exception as e:
                        logger.error(f"Erreur dans la boucle de collecte des données: {e}")
                        time.sleep(10)  # Attendre un peu avant de réessayer
            
            # Thread d'envoi des données
            def data_sending_loop():
                while True:
                    try:
                        # Envoyer les données au coordinateur
                        self.send_data_to_coordinator()
                        
                        # Attendre l'intervalle d'envoi
                        time.sleep(SEND_INTERVAL)
                    except Exception as e:
                        logger.error(f"Erreur dans la boucle d'envoi des données: {e}")
                        time.sleep(10)  # Attendre un peu avant de réessayer
            
            # Thread de publication de disponibilité
            def availability_loop():
                while True:
                    try:
                        if self.volunteer_id:
                            publish_availability(self.volunteer_id)
                        
                        # Attendre avant la prochaine publication
                        time.sleep(60)  # Publier toutes les minutes
                    except Exception as e:
                        logger.error(f"Erreur dans la boucle de publication de disponibilité: {e}")
                        time.sleep(10)  # Attendre un peu avant de réessayer
            
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
            
            # Démarrer les threads
            # self.data_collection_thread = threading.Thread(target=data_collection_loop)
            # self.data_collection_thread.daemon = True
            # self.data_collection_thread.start()
            # logger.info("Thread de collecte des données démarré")
            
            # self.data_sending_thread = threading.Thread(target=data_sending_loop)
            # self.data_sending_thread.daemon = True
            # self.data_sending_thread.start()
            # logger.info("Thread d'envoi des données démarré")
            
            # self.availability_thread = threading.Thread(target=availability_loop)
            # self.availability_thread.daemon = True
            # self.availability_thread.start()
            # logger.info("Thread de publication de disponibilité démarré")
            
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
