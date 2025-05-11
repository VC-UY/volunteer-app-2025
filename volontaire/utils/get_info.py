# system_info.py
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
            "machine_type": platform.machine(),
            "system": platform.system(),
            "node_name": platform.node(),
            "host_name": hostname,
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine_arch": platform.architecture()[0],
            "processor_name": platform.processor(),
            "cpu_type": platform.processor(),
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




