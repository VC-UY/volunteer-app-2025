"""
Commande Django pour collecter et enregistrer les informations de la machine.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from volontaire.models import MachineInfo, EtatMachine
import platform
import socket
import uuid
import psutil
from datetime import datetime


class Command(BaseCommand):
    help = 'Collecte et enregistre les informations de la machine dans la base de données'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Collecte des informations de la machine...'))

        try:
            # Fonction utilitaire pour convertir les octets
            def bytes_to_human_readable(bytes_value):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if bytes_value < 1024.0 or unit == 'TB':
                        return f"{bytes_value:.2f} {unit}"
                    bytes_value /= 1024.0

            # Collecter les adresses MAC
            mac_addresses = []
            for interface_name, interface_addresses in psutil.net_if_addrs().items():
                for addr in interface_addresses:
                    if addr.family == psutil.AF_LINK:
                        mac_addresses.append(addr.address)

            # Résolution d'écran (optionnelle)
            screen_resolution = "Non disponible"
            try:
                import subprocess
                if platform.system() == "Linux":
                    cmd = "xrandr | grep ' connected' | head -n 1 | awk '{print $3}' | cut -d'+' -f1"
                    screen_resolution = subprocess.check_output(cmd, shell=True).decode().strip()
            except:
                pass

            # Type de machine
            machine_type = "PC de bureau"
            if platform.system() == "Linux":
                if psutil.sensors_battery():
                    machine_type = "Portable"

            # Informations CPU
            cpu_freq = psutil.cpu_freq()
            cpu_cores_physical = psutil.cpu_count(logical=False) or 1
            cpu_cores_logical = psutil.cpu_count(logical=True) or 1

            # Informations mémoire
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Informations disque
            disk = psutil.disk_usage('/')

            # Partitions
            partitions = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    partitions.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": bytes_to_human_readable(usage.total),
                        "used": bytes_to_human_readable(usage.used),
                        "free": bytes_to_human_readable(usage.free),
                        "percent": usage.percent
                    })
                except:
                    pass

            # Interfaces réseau
            network_interfaces = []
            for interface_name, interface_addresses in psutil.net_if_addrs().items():
                interface_info = {"nom": interface_name, "adresses": []}
                for addr in interface_addresses:
                    if addr.family == socket.AF_INET:
                        interface_info["adresses"].append({
                            "type": "IPv4",
                            "adresse": addr.address
                        })
                network_interfaces.append(interface_info)

            # Utilisateurs connectés
            logged_users = []
            for user in psutil.users():
                logged_users.append({
                    "username": user.name,
                    "terminal": user.terminal,
                    "host": user.host
                })

            # Créer ou mettre à jour l'entrée MachineInfo
            machine, created = MachineInfo.objects.get_or_create(
                hostname=platform.node(),
                defaults={
                    'adresse_mac': mac_addresses,
                    'username': f"volunteer_{uuid.uuid4().hex[:8]}",
                    'password': uuid.uuid4().hex,
                    'os_name': platform.system(),
                    'os_version': platform.version(),
                    'os_release': platform.release(),
                    'os_architecture': platform.machine(),
                    'machine_type': machine_type,
                    'cpu_type': platform.processor(),
                    'cpu_architecture': platform.machine(),
                    'cpu_bits': "64-bit" if platform.machine().endswith('64') else "32-bit",
                    'cpu_cores_physical': cpu_cores_physical,
                    'cpu_cores_logical': cpu_cores_logical,
                    'cpu_frequency_current': cpu_freq.current if cpu_freq else None,
                    'cpu_frequency_min': cpu_freq.min if cpu_freq and hasattr(cpu_freq, 'min') else None,
                    'cpu_frequency_max': cpu_freq.max if cpu_freq and hasattr(cpu_freq, 'max') else None,
                    'ram_total': memory.total,
                    'ram_total_human': bytes_to_human_readable(memory.total),
                    'swap_total': swap.total,
                    'swap_total_human': bytes_to_human_readable(swap.total),
                    'disk_total': disk.total,
                    'disk_total_human': bytes_to_human_readable(disk.total),
                    'partitions': partitions,
                    'screen_resolution': screen_resolution,
                    'network_interfaces': network_interfaces,
                    'logged_users': logged_users,
                    'last_update': timezone.now(),
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Machine créée avec succès: {machine.hostname}'))
            else:
                # Mettre à jour les informations
                machine.adresse_mac = mac_addresses
                machine.os_name = platform.system()
                machine.os_version = platform.version()
                machine.os_release = platform.release()
                machine.os_architecture = platform.machine()
                machine.machine_type = machine_type
                machine.cpu_type = platform.processor()
                machine.cpu_cores_physical = cpu_cores_physical
                machine.cpu_cores_logical = cpu_cores_logical
                machine.ram_total = memory.total
                machine.ram_total_human = bytes_to_human_readable(memory.total)
                machine.swap_total = swap.total
                machine.swap_total_human = bytes_to_human_readable(swap.total)
                machine.disk_total = disk.total
                machine.disk_total_human = bytes_to_human_readable(disk.total)
                machine.partitions = partitions
                machine.screen_resolution = screen_resolution
                machine.network_interfaces = network_interfaces
                machine.logged_users = logged_users
                machine.last_update = timezone.now()
                machine.save()
                self.stdout.write(self.style.SUCCESS(f'✅ Machine mise à jour avec succès: {machine.hostname}'))

            # Créer un état initial
            EtatMachine.objects.create(
                machine=machine,
                cpu_usage_global=psutil.cpu_percent(interval=1),
                cpu_usage_per_core=psutil.cpu_percent(interval=0.1, percpu=True),
                ram_used=memory.used,
                ram_used_human=bytes_to_human_readable(memory.used),
                ram_available=memory.available,
                ram_available_human=bytes_to_human_readable(memory.available),
                ram_percent_used=memory.percent,
                ram_percent_free=100 - memory.percent,
                swap_used=swap.used,
                swap_used_human=bytes_to_human_readable(swap.used),
                swap_free=swap.free,
                swap_free_human=bytes_to_human_readable(swap.free),
                swap_percent_used=swap.percent,
                swap_percent_free=100 - swap.percent,
                disk_percent_used=disk.percent,
                disk_percent_free=100 - disk.percent,
                internet_connected=True,
                process_count=len(psutil.pids()),
                uptime_seconds=int(psutil.boot_time()),
                statut_actuel='available'
            )

            self.stdout.write(self.style.SUCCESS('✅ État de la machine enregistré avec succès'))
            self.stdout.write(self.style.SUCCESS('\n📊 Informations collectées:'))
            self.stdout.write(f'  • Hostname: {machine.hostname}')
            self.stdout.write(f'  • OS: {machine.os_name} {machine.os_release}')
            self.stdout.write(f'  • CPU: {machine.cpu_type} ({machine.cpu_cores_physical} cœurs physiques, {machine.cpu_cores_logical} cœurs logiques)')
            self.stdout.write(f'  • RAM: {machine.ram_total_human}')
            self.stdout.write(f'  • Disque: {machine.disk_total_human}')
            self.stdout.write(f'  • Résolution: {machine.screen_resolution}')
            self.stdout.write(self.style.SUCCESS('\n🎉 Vous pouvez maintenant rafraîchir la page web!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Erreur lors de la collecte: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
