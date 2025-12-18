# system_info.py

# recuperation des donnees statics de l'ordinateur

import platform
import uuid
import psutil
import socket
import shutil
import subprocess

def get_statics_infos():
    try:
        hostname = socket.gethostname()
        resolution = get_screen_resolution()

        infos = {
            "volunteer_id": str(uuid.uuid4()),
            "adresse_mac": get_mac_addresses(),
            "machine_tipe": platform.machine(),
            "system": platform.system(),
            "node_name": platform.node(),
            "host_name": hostname,
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine_arch": platform.architecture()[0],
            "processor_name": platform.processor(),
            "cpu_modele": platform.processor(),
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_logical_cores": psutil.cpu_count(),
            "cpu_frequency": psutil.cpu_freq().max if psutil.cpu_freq() else None,
            "total_memory": psutil.virtual_memory().total,
            "screen_resolution": resolution,
            "total_disk": shutil.disk_usage("/").total,
        }
        return infos
    except Exception as e:
        print(f"[ERROR] Static info error: {e}")
        return {}

def get_mac_addresses():
    macs = []
    for interface, snics in psutil.net_if_addrs().items():
        for snic in snics:
            if snic.family.name == 'AF_LINK' or snic.family == psutil.AF_LINK:
                macs.append(snic.address)
    return macs

def get_screen_resolution():
    try:
        output = subprocess.check_output(['xrandr']).decode()
        for line in output.splitlines():
            if '*' in line:
                return line.split()[0]  # ex: '1920x1080'
    except Exception:
        return "unknown"
    return "unknown"




'''



import platform
import uuid
import psutil
import socket
import shutil
import subprocess
import json

def get_mac_addresses():
    macs = []
    for interface, snics in psutil.net_if_addrs().items():
        for snic in snics:
            if snic.family.name == 'AF_LINK' or snic.family == psutil.AF_LINK:
                macs.append(snic.address)
    return macs

def get_screen_resolution():
    try:
        output = subprocess.check_output(['xrandr']).decode()
        for line in output.splitlines():
            if '*' in line:
                return line.split()[0]  # ex: '1920x1080'
    except Exception:
        return "unknown"
    return "unknown"

def get_bios_info():
    try:
        output = subprocess.check_output(['sudo', 'dmidecode', '-t', 'bios'], stderr=subprocess.DEVNULL).decode()
        return output
    except Exception:
        return {}

def get_motherboard_info():
    try:
        output = subprocess.check_output(['sudo', 'dmidecode', '-t', 'baseboard'], stderr=subprocess.DEVNULL).decode()
        return output
    except Exception:
        return {}

def get_usb_devices():
    try:
        output = subprocess.check_output(['lsusb']).decode()
        return output.splitlines()
    except Exception:
        return []

def bytes_to_human(n):
    symbols = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    prefix = {}
    for i, s in enumerate(symbols[1:], 1):
        prefix[s] = 1 << (i * 10)
    for s in reversed(symbols[1:]):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return f'{value:.2f} {s}'
    return f"{n} B"

def get_statics_infos():
    try:
        hostname = socket.gethostname()
        resolution = get_screen_resolution()
        virtual_mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = shutil.disk_usage("/")
        cpu_freq = psutil.cpu_freq()
        bios = get_bios_info()
        motherboard = get_motherboard_info()
        usb = get_usb_devices()

        infos = {
            "volunteer_id": str(uuid.uuid4()),
            "adresse_mac": get_mac_addresses(),
            "hostname": hostname,
            "os_name": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "os_architecture": platform.architecture()[0],
            "machine_tipe": platform.machine(),
            "cpu_modele": platform.processor(),
            "cpu_architecture": platform.machine(),
            "cpu_bits": platform.architecture()[0],
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(),
            "cpu_frequency_current": cpu_freq.current if cpu_freq else None,
            "cpu_frequency_min": cpu_freq.min if cpu_freq else None,
            "cpu_frequency_max": cpu_freq.max if cpu_freq else None,
            "ram_total": virtual_mem.total,
            "ram_total_human": bytes_to_human(virtual_mem.total),
            "swap_total": swap.total,
            "swap_total_human": bytes_to_human(swap.total),
            "disk_total": disk.total,
            "disk_total_human": bytes_to_human(disk.total),
            "partitions": [part._asdict() for part in psutil.disk_partitions()],
            "screen_resolution": resolution,
            "network_interfaces": {iface: [snic._asdict() for snic in snics] for iface, snics in psutil.net_if_addrs().items()},
            "bios_info": bios,
            "motherboard_info": motherboard,
            "usb_devices": usb,
            "logged_users": [user._asdict() for user in psutil.users()],
        }

        # Optional: include raw_data for debugging/audit purposes
        infos["raw_data"] = json.dumps(infos)

        return infos

    except Exception as e:
        print(f"[ERROR] Static info error: {e}")
        return {}

# get_statics_infos()  # Run for preview/debugging purposes


'''



import platform
import uuid
import psutil
import socket
import shutil
import subprocess
import json

def get_mac_addresses():
    macs = []
    for interface, snics in psutil.net_if_addrs().items():
        for snic in snics:
            if snic.family.name == 'AF_LINK' or snic.family == psutil.AF_LINK:
                macs.append(snic.address)
    return macs

def get_screen_resolution():
    try:
        output = subprocess.check_output(['xrandr']).decode()
        for line in output.splitlines():
            if '*' in line:
                return line.split()[0]
    except Exception:
        return "unknown"
    return "unknown"

def get_bios_info():
    try:
        # Ne pas utiliser sudo. dmidecode requiert root, sinon échoue silencieusement
        output = subprocess.check_output(['dmidecode', '-t', 'bios'], stderr=subprocess.DEVNULL).decode()
        return output
    except Exception:
        return None  # << Null si accès refusé ou dmidecode non disponible

def get_motherboard_info():
    try:
        output = subprocess.check_output(['dmidecode', '-t', 'baseboard'], stderr=subprocess.DEVNULL).decode()
        return output
    except Exception:
        return None

def get_usb_devices():
    try:
        output = subprocess.check_output(['lsusb']).decode()
        return output.splitlines()
    except Exception:
        return []

def bytes_to_human(n):
    symbols = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    prefix = {s: 1 << (i * 10) for i, s in enumerate(symbols)}
    for s in reversed(symbols[1:]):
        if n >= prefix[s]:
            return f"{float(n) / prefix[s]:.2f} {s}"
    return f"{n} B"

def get_static_infos():
    try:
        hostname = socket.gethostname()
        resolution = get_screen_resolution()
        virtual_mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = shutil.disk_usage("/")
        cpu_freq = psutil.cpu_freq()

        infos = {
            "adresse_mac": get_mac_addresses(),
            "hostname": hostname,
            "os_name": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "os_architecture": platform.architecture()[0],
            "machine_tipe": platform.machine(),
            "cpu_modele": platform.processor(),
            "cpu_architecture": platform.machine(),
            "cpu_bits": platform.architecture()[0],
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(),
            "cpu_frequency_current": cpu_freq.current if cpu_freq else None,
            "cpu_frequency_min": cpu_freq.min if cpu_freq else None,
            "cpu_frequency_max": cpu_freq.max if cpu_freq else None,
            "ram_total": virtual_mem.total,
            "ram_total_human": bytes_to_human(virtual_mem.total),
            "swap_total": swap.total,
            "swap_total_human": bytes_to_human(swap.total),
            "disk_total": disk.total,
            "disk_total_human": bytes_to_human(disk.total),
            "partitions": [part._asdict() for part in psutil.disk_partitions()],
            "screen_resolution": resolution,
            "network_interfaces": {iface: [snic._asdict() for snic in snics] for iface, snics in psutil.net_if_addrs().items()},
            "bios_info": get_bios_info(),  # will be None if non-root
            "motherboard_info": get_motherboard_info(),  # will be None if non-root
            "usb_devices": get_usb_devices(),
            "logged_users": [user._asdict() for user in psutil.users()],
        }

        infos["raw_data"] = json.dumps(infos)
        return infos

    except Exception as e:
        print(f"[ERROR] Static info error: {e}")
        return {}




#  recuperation des informationn dynamique de l'ordinateur.

'''

import psutil
import shutil
import socket
import datetime
import time
import platform

def get_dynamic_infos():
    try:
        cpu_percent = psutil.cpu_percent(percpu=False)
        cpu_percent_per_core = psutil.cpu_percent(percpu=True)

        # Température CPU (Linux)
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = temps.get("coretemp", [{}])[0].get("current", None)
        except Exception:
            cpu_temp = None

        # RAM
        virtual_mem = psutil.virtual_memory()
        ram_used = virtual_mem.used
        ram_available = virtual_mem.available
        ram_percent_used = virtual_mem.percent
        ram_percent_free = 100 - ram_percent_used

        # SWAP
        swap = psutil.swap_memory()
        swap_used = swap.used
        swap_free = swap.free
        swap_percent_used = swap.percent
        swap_percent_free = 100 - swap_percent_used

        # Cache (Linux-specific, approximatif)
        try:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            cache_lines = [line for line in meminfo.splitlines() if "Cached:" in line]
            cache_kb = int(cache_lines[0].split()[1]) if cache_lines else 0
            cache_bytes = cache_kb * 1024
        except Exception:
            cache_bytes = None

        # Disk
        disk = psutil.disk_usage("/")
        disk_percent_used = disk.percent
        disk_percent_free = 100 - disk_percent_used

        # Network
        net_io = psutil.net_io_counters()
        net_bytes_sent = net_io.bytes_sent
        net_bytes_recv = net_io.bytes_recv
        net_packets_sent = net_io.packets_sent
        net_packets_recv = net_io.packets_recv
        net_errors_in = net_io.errin
        net_errors_out = net_io.errout
        net_drop_in = net_io.dropin
        net_drop_out = net_io.dropout

        # Internet connectivity check
        def check_internet():
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                return True
            except OSError:
                return False

        internet_connected = check_internet()

        # Process count
        process_count = len(psutil.pids())

        # Battery
        try:
            battery = psutil.sensors_battery()
            battery_info = {
                "percent": battery.percent,
                "plugged": battery.power_plugged,
                "secsleft": battery.secsleft,
            } if battery else {}
        except Exception:
            battery_info = {}

        # Uptime
        boot_time = psutil.boot_time()
        now = time.time()
        uptime_seconds = int(now - boot_time)
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))

        # Raw data (optionnel)
        raw_data = {
            "cpu": {"global": cpu_percent, "per_core": cpu_percent_per_core, "temperature": cpu_temp},
            "ram": virtual_mem._asdict(),
            "swap": swap._asdict(),
            "disk": disk._asdict(),
            "net": net_io._asdict(),
            "battery": battery_info,
        }

        return {
            "cpu_usage_global": cpu_percent,
            "cpu_usage_per_core": cpu_percent_per_core,
            "cpu_temperature": cpu_temp,
            "ram_used": ram_used,
            "ram_used_human": shutil._ntuple_diskusage(ram_used).__str__(),
            "ram_available": ram_available,
            "ram_available_human": shutil._ntuple_diskusage(ram_available).__str__(),
            "ram_percent_used": ram_percent_used,
            "ram_percent_free": ram_percent_free,
            "swap_used": swap_used,
            "swap_used_human": shutil._ntuple_diskusage(swap_used).__str__(),
            "swap_free": swap_free,
            "swap_free_human": shutil._ntuple_diskusage(swap_free).__str__(),
            "swap_percent_used": swap_percent_used,
            "swap_percent_free": swap_percent_free,
            "cache_used": cache_bytes,
            "cache_used_human": f"{cache_bytes / (1024**2):.2f} MB" if cache_bytes else None,
            "disk_percent_used": disk_percent_used,
            "disk_percent_free": disk_percent_free,
            "gpu_usage": [],  # Ajoute si tu utilises `nvidia-smi` ou autre
            "net_bytes_sent": net_bytes_sent,
            "net_bytes_sent_human": f"{net_bytes_sent / (1024**2):.2f} MB",
            "net_bytes_received": net_bytes_recv,
            "net_bytes_received_human": f"{net_bytes_recv / (1024**2):.2f} MB",
            "net_packets_sent": net_packets_sent,
            "net_packets_received": net_packets_recv,
            "net_errors_in": net_errors_in,
            "net_errors_out": net_errors_out,
            "net_drop_in": net_drop_in,
            "net_drop_out": net_drop_out,
            "internet_connected": internet_connected,
            "process_count": process_count,
            "battery": battery_info,
            "uptime": uptime_str,
            "uptime_seconds": uptime_seconds,
            "threshold_reached": {},
            "statut_actuel": "available",
            "raw_data": raw_data,
        }

    except Exception as e:
        print(f"Erreur dans get_dynamic_infos: {e}")
        return {}

'''

import psutil
import shutil
import socket
import time
import platform
import datetime

# Facultatif : dépendances pour température CPU et GPU (py-cpuinfo, GPUtil, etc.)
try:
    import GPUtil
except ImportError:
    GPUtil = None

try:
    import psutil
except ImportError:
    raise ImportError("Le module psutil est requis pour cette fonction.")

def bytes_to_human(n):
    """Convertit les octets en format lisible (Ko, Mo, Go...)"""
    symbols = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    prefix = {}
    for i, s in enumerate(symbols[1:], 1):
        prefix[s] = 1 << (i * 10)
    for s in reversed(symbols[1:]):
        if n >= prefix[s]:
            return f"{n / prefix[s]:.2f} {s}"
    return f"{n} B"

def get_uptime():
    boot_time = psutil.boot_time()
    now = time.time()
    uptime_seconds = int(now - boot_time)
    uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
    return uptime_str, uptime_seconds

def get_dynamic_infos():
    try:
        # Informations CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        per_core_percent = psutil.cpu_percent(interval=1, percpu=True)

        # Température CPU (si supporté)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                cpu_temp = next((t.current for k, v in temps.items() for t in v if 'cpu' in t.label.lower() or 'core' in t.label.lower()), None)
            else:
                cpu_temp = None
        except Exception:
            cpu_temp = None

        # RAM
        virtual_mem = psutil.virtual_memory()
        ram_used = virtual_mem.used
        ram_available = virtual_mem.available

        # Swap
        swap = psutil.swap_memory()

        # Cache (approximé depuis virtual memory)
        cache_used = getattr(virtual_mem, 'cached', 0)

        # Disque
        disk_usage = shutil.disk_usage("/")
        disk_total = disk_usage.total
        disk_used = disk_usage.used
        disk_percent_used = (disk_used / disk_total) * 100
        disk_percent_free = 100 - disk_percent_used

        # GPU
        gpu_info = []
        if GPUtil:
            gpus = GPUtil.getGPUs()
            for gpu in gpus:
                gpu_info.append({
                    "name": gpu.name,
                    "load": round(gpu.load * 100, 2),
                    "memoryTotal": gpu.memoryTotal,
                    "memoryUsed": gpu.memoryUsed,
                    "temperature": gpu.temperature
                })

        # Réseau
        net_io = psutil.net_io_counters()
        net = {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errin": net_io.errin,
            "errout": net_io.errout,
            "dropin": net_io.dropin,
            "dropout": net_io.dropout
        }

        # Connexion Internet
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=3)
            internet_connected = True
        except OSError:
            internet_connected = False

        # Batterie
        try:
            battery = psutil.sensors_battery()
            battery_info = {
                "percent": battery.percent,
                "secsleft": battery.secsleft,
                "power_plugged": battery.power_plugged
            } if battery else {}
        except Exception:
            battery_info = {}

        # Processus
        process_count = len(psutil.pids())

        # Uptime
        uptime_str, uptime_seconds = get_uptime()

        # Seuils critiques fictifs (exemple)
        threshold_reached = {
            "cpu": cpu_percent > 90,
            "ram": virtual_mem.percent > 90,
            "disk": disk_percent_used > 90
        }

        return {
            "cpu_usage_global": cpu_percent,
            "cpu_usage_per_core": per_core_percent,
            "cpu_temperature": cpu_temp,

            "ram_used": ram_used,
            "ram_used_human": bytes_to_human(ram_used),
            "ram_available": ram_available,
            "ram_available_human": bytes_to_human(ram_available),
            "ram_percent_used": virtual_mem.percent,
            "ram_percent_free": 100 - virtual_mem.percent,

            "swap_used": swap.used,
            "swap_used_human": bytes_to_human(swap.used),
            "swap_free": swap.free,
            "swap_free_human": bytes_to_human(swap.free),
            "swap_percent_used": swap.percent,
            "swap_percent_free": 100 - swap.percent,

            "cache_used": cache_used,
            "cache_used_human": bytes_to_human(cache_used),

            "disk_percent_used": disk_percent_used,
            "disk_percent_free": disk_percent_free,

            "gpu_usage": gpu_info,

            "net_bytes_sent": net["bytes_sent"],
            "net_bytes_sent_human": bytes_to_human(net["bytes_sent"]),
            "net_bytes_received": net["bytes_recv"],
            "net_bytes_received_human": bytes_to_human(net["bytes_recv"]),
            "net_packets_sent": net["packets_sent"],
            "net_packets_received": net["packets_recv"],
            "net_errors_in": net["errin"],
            "net_errors_out": net["errout"],
            "net_drop_in": net["dropin"],
            "net_drop_out": net["dropout"],

            "internet_connected": internet_connected,
            "process_count": process_count,
            "battery": battery_info,

            "uptime": uptime_str,
            "uptime_seconds": uptime_seconds,

            "threshold_reached": threshold_reached,
            "statut_actuel": "available",  # valeur par défaut
            "raw_data": {},  # facultatif pour stocker tout
        }

    except Exception as e:
        print(f"[ERROR] Erreur lors de la récupération des infos dynamiques : {e}")
        return None
