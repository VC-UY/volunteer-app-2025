#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent de surveillance système - Collecte de données
Écrit par Delibes
Fonctionne sur Kali Linux et Windows
"""

import socket
import json
import platform
import os
import time
import uuid
import psutil
from datetime import datetime, timedelta
import subprocess
import shutil
import logging
import glob
import gzip
import backoff
import traceback
from typing import Dict, Any, List, Optional

try:
    import GPUtil
    GPU_UTIL_AVAILABLE = True
except ImportError:
    GPU_UTIL_AVAILABLE = False

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='system_monitor.log'
)

# Configuration
SERVER_HOST = os.getenv('COORDINATOR_HOST', 'localhost')
SERVER_PORT = os.getenv('COORDINATOR_PORT', 12345)
COLLECTION_INTERVAL = os.getenv('COLLECTION_INTERVAL', 2)
SEND_INTERVAL = os.getenv('SEND_INTERVAL', 30)
DATA_DIR = "data"
ID_FILE = "machine_id.txt"
RESOURCE_THRESHOLD = 80
STORAGE_LIMIT = 200 * 1024 * 1024  # 200 Mo
FILES_PER_BATCH = int(os.getenv('FILES_PER_BATCH', 5))
BATCH_PAUSE = int(os.getenv('BATCH_PAUSE', 3))  # Pause de 3s toutes les 5 fichiers

# Création du répertoire de données
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Variables globales
file_counter = 1
initial_data_saved = False
system_boot_time = datetime.fromtimestamp(psutil.boot_time())
script_start_time = datetime.now()
last_shutdown_time = None

def check_dependencies():
    """Vérifie les dépendances système."""
    required_commands = ['dmidecode', 'xrandr', 'sensors']
    missing = [cmd for cmd in required_commands if shutil.which(cmd) is None]
    if missing:
        logging.warning(f"Dépendances manquantes: {', '.join(missing)}")

def get_machine_id() -> Optional[str]:
    """Récupère l'ID machine depuis le fichier."""
    try:
        if os.path.exists(ID_FILE):
            with open(ID_FILE, 'r') as f:
                return f.read().strip()
        return None
    except Exception as e:
        logging.error(f"Erreur lecture ID machine: {e}\n{traceback.format_exc()}")
        return None

def save_machine_id(machine_id: str):
    """Sauvegarde l'ID machine dans un fichier."""
    try:
        with open(ID_FILE, 'w') as f:
            f.write(machine_id)
        logging.info(f"ID machine {machine_id} sauvegardé dans {ID_FILE}")
    except Exception as e:
        logging.error(f"Erreur sauvegarde ID machine: {e}\n{traceback.format_exc()}")

def get_next_filename() -> str:
    """Trouve le prochain nom de fichier disponible."""
    global file_counter
    while os.path.exists(f"{DATA_DIR}/{file_counter}.json.gz"):
        file_counter += 1
    return f"{DATA_DIR}/{file_counter}.json.gz"

def reset_file_counter():
    """Réinitialise le compteur de fichiers."""
    global file_counter
    file_counter = 1
    while os.path.exists(f"{DATA_DIR}/{file_counter}.json.gz"):
        file_counter += 1
    logging.info(f"Compteur de fichiers réinitialisé à {file_counter}")

def get_logged_users() -> List[Dict[str, str]]:
    """Récupère la liste des utilisateurs connectés."""
    users = []
    try:
        for user in psutil.users():
            users.append({
                "username": user.name,
                "terminal": user.terminal,
                "host": user.host,
                "started": datetime.fromtimestamp(user.started).strftime("%Y-%m-%d %H:%M:%S"),
                "pid": user.pid if hasattr(user, 'pid') else None
            })
    except Exception as e:
        logging.error(f"Erreur utilisateurs connectés: {e}\n{traceback.format_exc()}")
    return users

def get_screen_resolution() -> Optional[str]:
    """Récupère la résolution d'écran."""
    try:
        if platform.system() == "Windows":
            import ctypes
            user32 = ctypes.windll.user32
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            return f"{width}x{height}"
        elif platform.system() == "Linux":
            cmd = "xrandr | grep ' connected' | head -n 1 | awk '{print $3}' | cut -d'+' -f1"
            return subprocess.check_output(cmd, shell=True).decode().strip()
    except Exception as e:
        logging.error(f"Erreur résolution écran: {e}\n{traceback.format_exc()}")
        return "Non disponible"

def get_machine_type() -> int:
    """Détermine si la machine est un portable (0) ou un desktop (1)."""
    try:
        system = platform.system()
        if system == "Windows":
            if hasattr(psutil, "sensors_battery") and psutil.sensors_battery():
                return 0
            return 1
        elif system == "Linux":
            if os.path.exists("/sys/class/power_supply/BAT0") or os.path.exists("/sys/class/power_supply/BAT1"):
                return 0
            return 1
        elif system == "Darwin":
            model = subprocess.getoutput("sysctl -n hw.model")
            return 0 if "MacBook" in model else 1
        return 1
    except Exception as e:
        logging.error(f"Erreur type machine: {e}\n{traceback.format_exc()}")
        return 1

def get_bios_motherboard_info() -> Dict[str, Any]:
    """Récupère les informations BIOS et carte mère."""
    bios_info = {"BIOS": {"Fabricant": "Non disponible", "Version": "Non disponible", "Date": "Non disponible"},
                 "Carte mère": {"Fabricant": "Non disponible", "Modèle": "Non disponible"}}
    try:
        if platform.system() == "Windows":
            import wmi
            c = wmi.WMI()
            for bios in c.Win32_BIOS():
                bios_info["BIOS"] = {
                    "Fabricant": bios.Manufacturer,
                    "Version": bios.Version,
                    "Date": bios.ReleaseDate
                }
            for board in c.Win32_BaseBoard():
                bios_info["Carte mère"] = {
                    "Fabricant": board.Manufacturer,
                    "Modèle": board.Product
                }
        elif platform.system() == "Linux":
            # Utiliser /sys/class/dmi/id/ pour éviter les permissions root
            if os.path.exists('/sys/class/dmi/id/bios_vendor'):
                with open('/sys/class/dmi/id/bios_vendor', 'r') as f:
                    bios_info["BIOS"]["Fabricant"] = f.read().strip()
            if os.path.exists('/sys/class/dmi/id/bios_version'):
                with open('/sys/class/dmi/id/bios_version', 'r') as f:
                    bios_info["BIOS"]["Version"] = f.read().strip()
            if os.path.exists('/sys/class/dmi/id/bios_date'):
                with open('/sys/class/dmi/id/bios_date', 'r') as f:
                    bios_info["BIOS"]["Date"] = f.read().strip()
            if os.path.exists('/sys/class/dmi/id/board_vendor'):
                with open('/sys/class/dmi/id/board_vendor', 'r') as f:
                    bios_info["Carte mère"]["Fabricant"] = f.read().strip()
            if os.path.exists('/sys/class/dmi/id/board_name'):
                with open('/sys/class/dmi/id/board_name', 'r') as f:
                    bios_info["Carte mère"]["Modèle"] = f.read().strip()
            # Essayer dmidecode en dernier recours
            try:
                bios_output = subprocess.check_output("dmidecode -t bios", shell=True, stderr=subprocess.DEVNULL).decode()
                bios_info["BIOS"] = {
                    "Fabricant": next((line.split("Vendor:")[1].strip() for line in bios_output.splitlines() if "Vendor:" in line), bios_info["BIOS"]["Fabricant"]),
                    "Version": next((line.split("Version:")[1].strip() for line in bios_output.splitlines() if "Version:" in line), bios_info["BIOS"]["Version"]),
                    "Date": next((line.split("Release Date:")[1].strip() for line in bios_output.splitlines() if "Release Date:" in line), bios_info["BIOS"]["Date"])
                }
                board_output = subprocess.check_output("dmidecode -t baseboard", shell=True, stderr=subprocess.DEVNULL).decode()
                bios_info["Carte mère"] = {
                    "Fabricant": next((line.split("Manufacturer:")[1].strip() for line in board_output.splitlines() if "Manufacturer:" in line), bios_info["Carte mère"]["Fabricant"]),
                    "Modèle": next((line.split("Product Name:")[1].strip() for line in board_output.splitlines() if "Product Name:" in line), bios_info["Carte mère"]["Modèle"])
                }
            except (subprocess.CalledProcessError, PermissionError):
                logging.warning("dmidecode non accessible, utilisant valeurs par défaut")
    except Exception as e:
        logging.error(f"Erreur BIOS: {e}\n{traceback.format_exc()}")
    return bios_info

def get_usb_devices() -> List[Dict[str, str]]:
    """Récupère les périphériques USB."""
    usb_devices = []
    try:
        if platform.system() == "Windows":
            import wmi
            c = wmi.WMI()
            for device in c.Win32_USBControllerDevice():
                dependent = device.Dependent
                if dependent and hasattr(dependent, 'Description'):
                    usb_devices.append({"Description": dependent.Description})
        elif platform.system() == "Linux":
            usb_output = subprocess.check_output("lsusb", shell=True).decode()
            for line in usb_output.strip().split('\n'):
                if line:
                    usb_devices.append({"Description": line})
    except Exception as e:
        logging.error(f"Erreur USB: {e}\n{traceback.format_exc()}")
    return usb_devices

def get_gpu_info() -> Dict[str, Any]:
    """Récupère les informations GPU."""
    gpu_info = {"Disponible": False}
    if GPU_UTIL_AVAILABLE:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info = {
                    "Disponible": True,
                    "Nom": gpu.name,
                    "RAM": f"{gpu.memoryTotal} MB",
                    "Utilisation": f"{gpu.load * 100:.1f}%",
                    "Température": f"{gpu.temperature}°C"
                }
        except Exception as e:
            logging.error(f"Erreur GPUtil: {e}\n{traceback.format_exc()}")
    return gpu_info

def get_network_interfaces() -> List[Dict[str, Any]]:
    """Récupère les interfaces réseau."""
    network_interfaces = []
    try:
        for name, addrs in psutil.net_if_addrs().items():
            interface_info = {"nom": name, "adresses": []}
            for addr in addrs:
                address_info = {}
                if addr.family == socket.AF_INET:
                    address_info["type"] = "IPv4"
                    address_info["adresse"] = addr.address
                elif addr.family == socket.AF_INET6:
                    address_info["type"] = "IPv6"
                    address_info["adresse"] = addr.address
                elif addr.family == psutil.AF_LINK:
                    address_info["type"] = "MAC"
                    address_info["adresse"] = addr.address
                if address_info:
                    interface_info["adresses"].append(address_info)
            if name in psutil.net_if_stats():
                stats = psutil.net_if_stats()[name]
                interface_info["statut"] = "Up" if stats.isup else "Down"
                interface_info["vitesse"] = f"{stats.speed} Mbps"
            network_interfaces.append(interface_info)
    except Exception as e:
        logging.error(f"Erreur interfaces réseau: {e}\n{traceback.format_exc()}")
    return network_interfaces

def is_internet_connected() -> bool:
    """Vérifie la connexion Internet."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError as e:
        logging.error(f"Erreur connexion Internet: {e}\n{traceback.format_exc()}")
        return False

def get_disk_partitions() -> List[Dict[str, Any]]:
    """Récupère les partitions de disque."""
    partitions = []
    try:
        for part in psutil.disk_partitions(all=True):
            partition_info = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype
            }
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partition_info.update({
                    "total": bytes_to_human_readable(usage.total),
                    "used": bytes_to_human_readable(usage.used),
                    "free": bytes_to_human_readable(usage.free),
                    "percent_used": usage.percent
                })
            except:
                partition_info.update({
                    "total": "Non disponible",
                    "used": "Non disponible",
                    "free": "Non disponible",
                    "percent_used": "Non disponible"
                })
            partitions.append(partition_info)
    except Exception as e:
        logging.error(f"Erreur partitions disque: {e}\n{traceback.format_exc()}")
    return partitions

def bytes_to_human_readable(bytes_value: int) -> str:
    """Convertit les octets en format lisible."""
    try:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0 or unit == 'TB':
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
    except Exception as e:
        logging.error(f"Erreur conversion octets: {e}\n{traceback.format_exc()}")
        return "Non disponible"

def get_cpu_temperature() -> Optional[float]:
    """Récupère la température CPU."""
    try:
        if platform.system() == "Linux":
            try:
                output = subprocess.check_output(["sensors"], universal_newlines=True)
                for line in output.split("\n"):
                    if "Core" in line and "°C" in line:
                        return float(line.split("+")[1].split("°C")[0].strip())
            except:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    return float(f.read().strip()) / 1000.0
        elif platform.system() == "Windows":
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            return (w.MSAcpi_ThermalZoneTemperature()[0].CurrentTemperature / 10.0) - 273.15
    except Exception as e:
        logging.error(f"Erreur température CPU: {e}\n{traceback.format_exc()}")
    return None

def get_battery_info() -> Dict[str, Any]:
    """Récupère les informations batterie."""
    battery_info = {
        "has_battery": 1,
        "percent": "Non disponible",
        "power_plugged": "Non disponible",
        "autonomy": "Non disponible"
    }
    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_info["has_battery"] = 0
            battery_info["percent"] = battery.percent
            battery_info["power_plugged"] = battery.power_plugged
            if battery.secsleft > 0 and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
                hours = battery.secsleft // 3600
                minutes = (battery.secsleft % 3600) // 60
                battery_info["autonomy"] = f"{hours}h {minutes}min"
            elif battery.power_plugged:
                battery_info["autonomy"] = "Branché secteur"
        else:
            logging.info("Aucune batterie détectée")
    except Exception as e:
        logging.error(f"Erreur batterie: {e}\n{traceback.format_exc()}")
    return battery_info

def get_cache_memory_total() -> str:
    """Récupère la mémoire cache totale du système."""
    try:
        if platform.system() == "Linux":
            # Lire /proc/meminfo pour obtenir la mémoire cache
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            # Extraire les valeurs de cache
            cached = 0
            buffers = 0
            slab = 0
            
            for line in meminfo.splitlines():
                if line.startswith('Cached:'):
                    cached = int(line.split()[1]) * 1024  # Convert kB to bytes
                elif line.startswith('Buffers:'):
                    buffers = int(line.split()[1]) * 1024
                elif line.startswith('Slab:'):
                    slab = int(line.split()[1]) * 1024
            
            total_cache = cached + buffers + slab
            return bytes_to_human_readable(total_cache)
            
        elif platform.system() == "Windows":
            # Sur Windows, utiliser la mémoire virtuelle disponible comme approximation
            memory = psutil.virtual_memory()
            return bytes_to_human_readable(memory.cached if hasattr(memory, 'cached') else 0)
        
        return "Non disponible"
    except Exception as e:
        logging.error(f"Erreur mémoire cache: {e}\n{traceback.format_exc()}")
        return "Non disponible"

def get_memory_cache_dynamic() -> Dict[str, Any]:
    """Récupère les informations de cache mémoire dynamiques."""
    try:
        if platform.system() == "Linux":
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            cache_info = {}
            for line in meminfo.splitlines():
                if line.startswith('Cached:'):
                    cache_info['cached'] = bytes_to_human_readable(int(line.split()[1]) * 1024)
                elif line.startswith('Buffers:'):
                    cache_info['buffers'] = bytes_to_human_readable(int(line.split()[1]) * 1024)
                elif line.startswith('Slab:'):
                    cache_info['slab'] = bytes_to_human_readable(int(line.split()[1]) * 1024)
                elif line.startswith('SReclaimable:'):
                    cache_info['sreclaimable'] = bytes_to_human_readable(int(line.split()[1]) * 1024)
            
            return cache_info
            
        elif platform.system() == "Windows":
            memory = psutil.virtual_memory()
            return {
                'cached': bytes_to_human_readable(getattr(memory, 'cached', 0)),
                'buffers': "Non disponible",
                'slab': "Non disponible",
                'sreclaimable': "Non disponible"
            }
        
        return {
            'cached': "Non disponible",
            'buffers': "Non disponible", 
            'slab': "Non disponible",
            'sreclaimable': "Non disponible"
        }
    except Exception as e:
        logging.error(f"Erreur cache mémoire dynamique: {e}\n{traceback.format_exc()}")
        return {
            'cached': "Non disponible",
            'buffers': "Non disponible",
            'slab': "Non disponible", 
            'sreclaimable': "Non disponible"
        }

def get_internet_speed() -> Dict[str, Any]:
    """Teste et mesure le débit internet."""
    try:
        import requests
        import time
        
        # URL de test pour mesurer le débit (petit fichier)
        test_url = "http://speedtest.ftp.otenet.gr/files/test100k.db"
        
        # Test de ping
        start_ping = time.time()
        try:
            response = requests.head("http://www.google.com", timeout=5)
            ping_time = (time.time() - start_ping) * 1000
        except:
            ping_time = None
        
        # Test de débit descendant (download)
        try:
            start_time = time.time()
            response = requests.get(test_url, timeout=10, stream=True)
            data_size = 0
            for chunk in response.iter_content(chunk_size=1024):
                data_size += len(chunk)
                if time.time() - start_time > 3:  # Limite à 3 secondes
                    break
            
            duration = time.time() - start_time
            download_speed = (data_size * 8) / (duration * 1024 * 1024)  # Mbps
        except:
            download_speed = None
        
        return {
            "ping_ms": round(ping_time, 2) if ping_time else "Non disponible",
            "download_mbps": round(download_speed, 2) if download_speed else "Non disponible",
            "test_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
    except ImportError:
        return {
            "ping_ms": "Module requests manquant",
            "download_mbps": "Module requests manquant", 
            "test_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logging.error(f"Erreur test débit internet: {e}\n{traceback.format_exc()}")
        return {
            "ping_ms": "Erreur de mesure",
            "download_mbps": "Erreur de mesure",
            "test_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def get_cpu_frequencies_per_core() -> Dict[str, Any]:
    """Récupère les fréquences CPU par cœur et globale."""
    try:
        frequencies = {
            "frequences_par_coeur": [],
            "frequence_globale": {
                "actuelle": "Non disponible",
                "min": "Non disponible", 
                "max": "Non disponible"
            }
        }
        
        # Fréquence globale
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            frequencies["frequence_globale"] = {
                "actuelle": f"{cpu_freq.current:.0f} MHz",
                "min": f"{cpu_freq.min:.0f} MHz" if cpu_freq.min else "Non disponible",
                "max": f"{cpu_freq.max:.0f} MHz" if cpu_freq.max else "Non disponible"
            }
        
        # Fréquences par cœur (si disponible)
        try:
            cpu_freqs = psutil.cpu_freq(percpu=True)
            if cpu_freqs:
                for i, freq in enumerate(cpu_freqs):
                    frequencies["frequences_par_coeur"].append({
                        "core": i,
                        "actuelle": f"{freq.current:.0f} MHz" if freq.current else "Non disponible",
                        "min": f"{freq.min:.0f} MHz" if freq.min else "Non disponible",
                        "max": f"{freq.max:.0f} MHz" if freq.max else "Non disponible"
                    })
            else:
                # Fallback: utiliser la fréquence globale pour tous les cœurs
                core_count = psutil.cpu_count(logical=True)
                for i in range(core_count):
                    frequencies["frequences_par_coeur"].append({
                        "core": i,
                        "actuelle": frequencies["frequence_globale"]["actuelle"],
                        "min": frequencies["frequence_globale"]["min"],
                        "max": frequencies["frequence_globale"]["max"]
                    })
        except:
            # Si psutil.cpu_freq(percpu=True) n'est pas supporté
            core_count = psutil.cpu_count(logical=True)
            for i in range(core_count):
                frequencies["frequences_par_coeur"].append({
                    "core": i,
                    "actuelle": frequencies["frequence_globale"]["actuelle"],
                    "min": frequencies["frequence_globale"]["min"],
                    "max": frequencies["frequence_globale"]["max"]
                })
        
        return frequencies
        
    except Exception as e:
        logging.error(f"Erreur fréquences CPU: {e}\n{traceback.format_exc()}")
        return {
            "frequences_par_coeur": [],
            "frequence_globale": {
                "actuelle": "Erreur",
                "min": "Erreur",
                "max": "Erreur"
            }
        }

def get_last_shutdown_time() -> str:
    """Récupère l'heure de la dernière mise hors tension du système."""
    try:
        if platform.system() == "Linux":
            # Essayer de lire les logs système pour trouver la dernière extinction
            try:
                # Chercher dans journalctl pour la dernière extinction
                result = subprocess.run(['journalctl', '--boot=-1', '--reverse', '--no-pager', '--output=short-iso'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    lines = result.stdout.splitlines()
                    for line in lines:
                        if 'shutdown' in line.lower() or 'power off' in line.lower():
                            # Extraire la date de la ligne
                            parts = line.split()
                            if len(parts) >= 2:
                                return f"{parts[0]} {parts[1]}"
            except subprocess.TimeoutExpired:
                logging.warning("Timeout lors de la lecture des logs de shutdown")
            except FileNotFoundError:
                logging.warning("journalctl non disponible")
            
            # Fallback: utiliser l'uptime pour estimer
            boot_time = psutil.boot_time()
            last_shutdown_estimate = datetime.fromtimestamp(boot_time) - timedelta(minutes=1)
            return last_shutdown_estimate.strftime("%Y-%m-%d %H:%M:%S") + " (estimé)"
            
        elif platform.system() == "Windows":
            try:
                # Utiliser wmic pour obtenir les événements de shutdown
                result = subprocess.run(['wmic', 'os', 'get', 'LastBootUpTime', '/value'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if 'LastBootUpTime=' in line:
                            boot_time_str = line.split('=')[1].strip()
                            if boot_time_str:
                                # Format WMI: 20240629141522.123456+120
                                boot_time = datetime.strptime(boot_time_str[:14], '%Y%m%d%H%M%S')
                                last_shutdown_estimate = boot_time - timedelta(minutes=1)
                                return last_shutdown_estimate.strftime("%Y-%m-%d %H:%M:%S") + " (estimé)"
            except (subprocess.TimeoutExpired, ValueError):
                logging.warning("Erreur lors de la lecture des événements Windows")
        
        return "Non disponible"
    except Exception as e:
        logging.error(f"Erreur dernière extinction: {e}\n{traceback.format_exc()}")
        return "Non disponible"

def get_network_packets_info() -> Dict[str, Any]:
    """Récupère les informations sur les paquets réseau envoyés/reçus."""
    try:
        net_io = psutil.net_io_counters()
        return {
            "paquets_envoyes": net_io.packets_sent if hasattr(net_io, 'packets_sent') else 0,
            "paquets_recus": net_io.packets_recv if hasattr(net_io, 'packets_recv') else 0,
            "erreurs_entree": net_io.errin if hasattr(net_io, 'errin') else 0,
            "erreurs_sortie": net_io.errout if hasattr(net_io, 'errout') else 0,
            "paquets_abandonnes_entree": net_io.dropin if hasattr(net_io, 'dropin') else 0,
            "paquets_abandonnes_sortie": net_io.dropout if hasattr(net_io, 'dropout') else 0
        }
    except Exception as e:
        logging.error(f"Erreur paquets réseau: {e}\n{traceback.format_exc()}")
        return {
            "paquets_envoyes": 0,
            "paquets_recus": 0,
            "erreurs_entree": 0,
            "erreurs_sortie": 0,
            "paquets_abandonnes_entree": 0,
            "paquets_abandonnes_sortie": 0
        }

def check_resource_threshold() -> Dict[str, Any]:
    """Vérifie si le seuil d'utilisation est atteint."""
    threshold_reached = {"cpu": False, "memory": False, "disk": False, "timestamp": None}
    try:
        if psutil.cpu_percent(interval=0.1) > RESOURCE_THRESHOLD:
            threshold_reached["cpu"] = True
        memory = psutil.virtual_memory()
        if memory.percent > RESOURCE_THRESHOLD:
            threshold_reached["memory"] = True
        disk = psutil.disk_usage('/')
        if disk.percent > RESOURCE_THRESHOLD:
            threshold_reached["disk"] = True
        if any(threshold_reached.values()):
            threshold_reached["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logging.error(f"Erreur seuils: {e}\n{traceback.format_exc()}")
    return threshold_reached

def collect_initial_data() -> Dict[str, Any]:
    """Collecte les données initiales."""
    try:
        os_info = {
            "nom": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "hostname": platform.node()
        }
        cpu_info = {
            "type": platform.processor(),
            "coeurs_physiques": psutil.cpu_count(logical=False),
            "coeurs_logiques": psutil.cpu_count(logical=True),
            "frequence": {
                "actuelle": psutil.cpu_freq().current if psutil.cpu_freq() else "Non disponible",
                "min": psutil.cpu_freq().min if psutil.cpu_freq() else "Non disponible",
                "max": psutil.cpu_freq().max if psutil.cpu_freq() else "Non disponible"
            }
        }
        memory = psutil.virtual_memory()
        memory_info = {
            "ram": {
                "total": bytes_to_human_readable(memory.total),
                "disponible": bytes_to_human_readable(memory.available),
                "utilisee": bytes_to_human_readable(memory.used),
                "pourcentage_utilise": memory.percent
            },
            "swap": {
                "total": bytes_to_human_readable(psutil.swap_memory().total)
            },
            "cache_total": get_cache_memory_total()
        }
        disk = psutil.disk_usage('/')
        disk_info = {
            "total": bytes_to_human_readable(disk.total),
            "disponible": bytes_to_human_readable(disk.free),
            "utilise": bytes_to_human_readable(disk.used),
            "pourcentage_utilise": disk.percent
        }
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "os": os_info,
            "type_machine": get_machine_type(),
            "cpu": cpu_info,
            "memoire": memory_info,
            "disque": disk_info,
            "adresse_mac": ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0, 8*6, 8)][::-1]),
            "resolution_ecran": get_screen_resolution(),
            "gpu": get_gpu_info(),
            "interfaces_reseau": get_network_interfaces(),
            "bios_carte_mere": get_bios_motherboard_info(),
            "utilisateurs_connectes": get_logged_users(),
            "partitions_disque": get_disk_partitions(),
            "peripheriques_usb": get_usb_devices(),
            "battery_initial": get_battery_info(),
            "heure_demarrage_systeme": system_boot_time.strftime("%Y-%m-%d %H:%M:%S"),
            "heure_demarrage_script": script_start_time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logging.error(f"Erreur collecte initiale: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}

def collect_variable_data() -> Dict[str, Any]:
    """Collecte les données variables."""
    try:
        cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        cpu_cores_data = [{"core": i, "utilisation": p} for i, p in enumerate(cpu_per_core)]
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage('/')
        gpu_usage = None
        if GPU_UTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    gpu_usage = {
                        "gpu": f"{gpu.load * 100:.1f}%",
                        "memory": f"{(gpu.memoryUsed / gpu.memoryTotal) * 100:.1f}%"
                    }
            except Exception as e:
                logging.error(f"Erreur GPU: {e}\n{traceback.format_exc()}")
        net_io = psutil.net_io_counters()
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu": {
                "global_utilise": sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0,
                "par_coeur": cpu_cores_data,
                "temperature": get_cpu_temperature(),
                "frequences": get_cpu_frequencies_per_core()
            },
            "memoire": {
                "ram": {
                    "pourcentage_utilise": memory.percent,
                    "utilisee": bytes_to_human_readable(memory.used),
                    "disponible": bytes_to_human_readable(memory.available)
                },
                "swap": {
                    "pourcentage_utilise": swap.percent,
                    "utilisee": bytes_to_human_readable(swap.used),
                    "disponible": bytes_to_human_readable(swap.free)
                },
                "cache_dynamique": get_memory_cache_dynamic()
            },
            "disque": {
                "pourcentage_utilise": disk.percent
            },
            "gpu_utilisation": gpu_usage,
            "reseau": {
                "octets_envoyes": bytes_to_human_readable(net_io.bytes_sent),
                "octets_recus": bytes_to_human_readable(net_io.bytes_recv),
                "paquets_info": get_network_packets_info(),
                "debit_internet": get_internet_speed()
            },
            "connexion_internet": is_internet_connected(),
            "nombre_processus": len(psutil.pids()),
            "battery": get_battery_info(),
            "uptime": str(timedelta(seconds=time.time() - psutil.boot_time())),
            "derniere_extinction": get_last_shutdown_time(),
            "seuil_atteint": check_resource_threshold()
        }
    except Exception as e:
        logging.error(f"Erreur collecte variable: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}

def save_initial_data():
    """Sauvegarde les données initiales dans 1.json.gz."""
    global initial_data_saved
    if initial_data_saved or os.path.exists(f"{DATA_DIR}/1.json.gz"):
        logging.info("Données initiales déjà sauvegardées")
        return
    try:
        initial_data = collect_initial_data()
        with gzip.open(f"{DATA_DIR}/1.json.gz", 'wt', encoding='utf-8') as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)
        initial_data_saved = True
        logging.info("Données initiales sauvegardées")
    except Exception as e:
        logging.error(f"Erreur sauvegarde initiale: {e}\n{traceback.format_exc()}")

def save_variable_data_to_file(data: Dict[str, Any]) -> Optional[str]:
    """Sauvegarde les données variables dans un fichier compressé."""
    try:
        filename = get_next_filename()
        with gzip.open(filename, 'wt', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"Données variables sauvegardées dans {filename}")
        return filename
    except Exception as e:
        logging.error(f"Erreur sauvegarde variable: {e}\n{traceback.format_exc()}")
        return None

def initialize_data_collection():
    """Initialise la collecte de données."""
    global initial_data_saved, file_counter
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if os.path.exists(f"{DATA_DIR}/1.json.gz"):
            initial_data_saved = True
        else:
            initial_data_saved = False
        reset_file_counter()
    except Exception as e:
        logging.error(f"Erreur initialisation collecte: {e}\n{traceback.format_exc()}")

def log_backoff(details):
    logging.warning(
        f"Tentative {details['tries']} échouée, nouvelle tentative dans {details['wait']}s..."
    )


@backoff.on_exception(
    backoff.expo,
    (socket.timeout, ConnectionRefusedError, ConnectionResetError, BrokenPipeError),
    max_tries=5,
    on_backoff=log_backoff
)
def send_files_to_server() -> Optional[str]:
    """Envoie les fichiers JSON au serveur."""
    machine_id = get_machine_id()
    json_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.json.gz')])
    if not json_files:
        logging.info("Aucun fichier à envoyer")
        return machine_id

    # Prioritize sending 1.json.gz first
    if "1.json.gz" in json_files and not machine_id:
        json_files = ["1.json.gz"] + [f for f in json_files if f != "1.json.gz"]

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.settimeout(5)
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            logging.info(f"Connecté au serveur {SERVER_HOST}:{SERVER_PORT}")

            for i, json_file in enumerate(json_files):
                file_path = os.path.join(DATA_DIR, json_file)
                try:
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        file_data = f.read()
                    json_data = json.loads(file_data)
                    data_to_send = {
                        "version": "1.0",
                        "filename": json_file,
                        "content": json_data,
                        "machine_id": machine_id,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    client_socket.sendall(f"{json.dumps(data_to_send)}\n".encode('utf-8'))
                    response = client_socket.recv(1024).decode('utf-8').strip()
                    response_data = json.loads(response)

                    if response_data.get("status") == "success":
                        if json_file == "1.json.gz" and response_data.get("machine_id"):
                            machine_id = response_data["machine_id"]
                            save_machine_id(machine_id)
                        logging.info(f"Fichier {json_file} envoyé, suppression")
                        os.remove(file_path)
                    elif response_data.get("message") == "RESEND_STATIC_DATA":
                        logging.warning(f"Machine non identifiée pour {json_file}, envoi de 1.json.gz requis")
                        if json_file != "1.json.gz" and os.path.exists(f"{DATA_DIR}/1.json.gz"):
                            json_files.insert(0, "1.json.gz")  # Retry with static data
                            continue
                    else:
                        logging.warning(f"Erreur envoi {json_file}: {response_data.get('message')}")

                    if (i + 1) % FILES_PER_BATCH == 0:
                        logging.info(f"Pause de {BATCH_PAUSE}s après {FILES_PER_BATCH} fichiers")
                        time.sleep(BATCH_PAUSE)
                except (ConnectionResetError, BrokenPipeError) as e:
                    logging.error(f"Erreur réseau lors de l'envoi de {json_file}: {e}\n{traceback.format_exc()}")
                    break
                except Exception as e:
                    logging.error(f"Erreur envoi {json_file}: {e}\n{traceback.format_exc()}")

            return machine_id
    except Exception as e:
        logging.error(f"Erreur connexion serveur: {e}\n{traceback.format_exc()}")
        return machine_id

def get_data_directory_size() -> int:
    """Calcule la taille du répertoire de données."""
    total_size = 0
    try:
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.json.gz'):
                total_size += os.path.getsize(os.path.join(DATA_DIR, filename))
    except Exception as e:
        logging.error(f"Erreur calcul taille répertoire: {e}\n{traceback.format_exc()}")
    return total_size

def is_storage_limit_reached() -> bool:
    """Vérifie si la limite de stockage est atteinte."""
    try:
        if get_data_directory_size() >= STORAGE_LIMIT:
            logging.warning(f"Limite de stockage atteinte: {bytes_to_human_readable(get_data_directory_size())}")
            return True
        return False
    except Exception as e:
        logging.error(f"Erreur vérification stockage: {e}\n{traceback.format_exc()}")
        return False

def continuous_collection():
    """Collecte continue des données."""
    try:
        check_dependencies()
        initialize_data_collection()
        machine_id = get_machine_id()
        last_send_time = time.time()

        if not machine_id:
            save_initial_data()
            machine_id = send_files_to_server()
        
        logging.info(f"Demarrage de la boucle de collecte continue avec machine_id: {machine_id}")

        while True:
            if is_storage_limit_reached():
                logging.warning("Limite de stockage atteinte, arrêt")
                break
            if not initial_data_saved:
                save_initial_data()
                
            variable_data = collect_variable_data()
            if variable_data and "error" not in variable_data:
                save_variable_data_to_file(variable_data)
            current_time = time.time()
            if current_time - last_send_time >= SEND_INTERVAL:
                machine_id = send_files_to_server()
                last_send_time = current_time
            time.sleep(COLLECTION_INTERVAL)
    except Exception as e:
        logging.error(f"Erreur collecte continue: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    try:
        continuous_collection()
    except KeyboardInterrupt:
        logging.info("Script arrêté par l'utilisateur")
        try:
            send_files_to_server()
        except Exception as e:
            logging.error(f"Erreur envoi final: {e}\n{traceback.format_exc()}")
    except Exception as e:
        logging.error(f"Erreur fatale: {e}\n{traceback.format_exc()}")
        import sys
        sys.exit(1)