from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from volontaire.utils.get_info import get_statics_infos
from volontaire.docker_manager import DockerManager
from django.shortcuts import render
from pathlib import Path
import psutil
import time as time_module
import json


# Utiliser l'instance singleton de DockerManager
manager = DockerManager.get_instance()

# Chemin vers le fichier de statistiques de l'agent
BASE_DIR = Path(__file__).resolve().parent.parent
AGENT_STATS_FILE = BASE_DIR / '.volunteer' / 'agent_stats.json'


def _read_agent_stats():
    """Lit les statistiques de l'agent depuis le fichier partagé"""
    try:
        if AGENT_STATS_FILE.exists():
            with open(AGENT_STATS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    
    # Valeurs par défaut si le fichier n'existe pas
    return {
        'status': 'unknown',
        'connected': False,
        'start_time': None,
        'messages_sent': 0,
        'messages_received': 0,
        'files_collected': 0,
        'files_sent': 0,
        'tasks_completed': 0,
        'tasks_failed': 0,
        'data_collected_mb': 0.0,
        'data_sent_mb': 0.0,
        'reconnections': 0,
        'last_sync': None,
        'last_error': None,
        'uptime_seconds': 0
    }


# ==================== API AGENT DE COLLECTE ====================

class AgentStatusView(APIView):
    """Récupère le statut de l'agent de collecte Redis"""
    def get(self, request):
        stats = _read_agent_stats()
        return Response(stats)


class AgentControlView(APIView):
    """Contrôle l'agent de collecte (start/stop)"""
    def post(self, request, action):
        try:
            from redis_communication.client import RedisClient
            
            if action == 'start':
                client = RedisClient.get_instance()
                if not client.running:
                    client.start()
                return Response({'message': 'Agent démarré', 'success': True})
            
            elif action == 'stop':
                if RedisClient._instance:
                    RedisClient._instance.stop()
                return Response({'message': 'Agent arrêté', 'success': True})
            
            else:
                return Response({'error': 'Action inconnue'}, status=400)
                
        except Exception as e:
            return Response({'error': str(e), 'success': False}, status=500)


class MachineStateView(APIView):
    """Récupère l'état actuel de la machine (CPU, RAM, Disk usage)"""
    def get(self, request):
        try:
            # CPU usage (moyenne sur 1 seconde)
            cpu_usage = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            
            # RAM usage
            memory = psutil.virtual_memory()
            ram_usage = memory.percent
            ram_used = memory.used / (1024 ** 3)  # GB
            ram_total = memory.total / (1024 ** 3)  # GB
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            disk_used = disk.used / (1024 ** 3)  # GB
            disk_total = disk.total / (1024 ** 3)  # GB
            
            return Response({
                'cpu_usage': round(cpu_usage, 1),
                'cpu_count': cpu_count,
                'cpu_count_physical': cpu_count_physical,
                'ram_usage': round(ram_usage, 1),
                'ram_used_gb': round(ram_used, 2),
                'ram_total_gb': round(ram_total, 2),
                'disk_usage': round(disk_usage, 1),
                'disk_used_gb': round(disk_used, 2),
                'disk_total_gb': round(disk_total, 2),
                'timestamp': time_module.time()
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)


# ==================== DOCKER CONTAINER MANAGEMENT ====================



# Pause
class PauseContainerView(APIView):
    def post(self, request, container_id):
        try:
            msg = manager.pause_task(container_id)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Replay
class ReplayContainerView(APIView):
    def post(self, request, container_id):
        try:
            msg = manager.resume_task(container_id)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Suspend
class SuspendContainerView(APIView):
    def post(self, request, container_id):
        try:
            msg = manager.stop_task(container_id)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Delete
class DeleteContainerView(APIView):
    def delete(self, request, container_id):
        try:
            msg = manager.remove_task(container_id)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Limit CPU
class LimitCPUView(APIView):
    def post(self, request, container_id):
        try:
            cpu_quota = int(request.data.get("cpu_quota", 50000))  # ex: 50000 = 5% CPU
            msg = manager.update_limits(container_id, cpu_quota)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Limit RAM
class LimitRAMView(APIView):
    def post(self, request, container_id):
        try:
            mem_limit = request.data.get("mem_limit", "500m")  # ex: "500m", "1g"
            msg = manager.update_limits(container_id, mem_limit)
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

# Purge
class PurgeContainersView(APIView):
    def delete(self, request):
        try:
            msg = manager.purge_all()
            return Response({"message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=500)

# Liste des conteneurs (task list)
class TaskListView(APIView):
    def get(self, request):
        try:
            containers = manager.list_tasks()
            result = [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags
                } for c in containers
            ]
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

# Détails d’un conteneur (task details)
class TaskDetailView(APIView):
    def get(self, request, container_id):
        try:
            details = manager.task_details(container_id)
            return Response(details)
        except Exception as e:
            return Response({"error": str(e)}, status=404)
        

# ------------------- Gestion des actions sur un conteneur --------------------------


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Task

@csrf_exempt
def handle_task_action(request, action, task_id):
    if request.method == 'POST':
        try:
            from redis_communication.task_handlers import TaskManager
            task_manager = TaskManager.get_instance()
            task = Task.objects.get(task_id=task_id)

            if action == 'pause':
                task_manager.pause_task(task_id)
                task.status = 'paused'
                task.save()
            elif action in ['resume', 'replay']:  # Accepter les deux
                task_manager.resume_task(task_id)
                task.status = 'running'
                task.save()
            elif action in ['stop', 'suspend']:  # Accepter les deux
                task_manager.stop_task(task_id)
                task.status = 'stopped'
                task.save()
            elif action == 'delete':
                task_manager.stop_task(task_id)
                task.delete()
                return JsonResponse({'message': 'Tâche supprimée'}, status=200)
            elif action == 'limit_cpu':
                cpu_quota = int(request.POST.get('cpu_quota', 50000))
                task_manager.update_limits(task_id, cpu_quota=cpu_quota)
            elif action == 'limit_ram':
                mem_limit = request.POST.get('mem_limit', '500m')
                task_manager.update_limits(task_id, mem_limit=mem_limit)
            else:
                return JsonResponse({'error': f'Action inconnue: {action}'}, status=400)

            return JsonResponse({'message': f'Action {action} effectuée'}, status=200)

        except Task.DoesNotExist:
            return JsonResponse({'error': f'Tâche {task_id} non trouvée'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)




# ------------------------- Docker Container Status API -------------------------------------

# API pour récupérer les états de tous les conteneurs Docker
class DockerContainersStatusView(APIView):
    def get(self, request):
        try:
            # Récupérer la liste des tâches avec leurs conteneurs associés
            containers = manager.list_tasks()
            
            # Formater la réponse
            response_data = {
                "total_containers": len(containers),
                "containers": containers
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------- Computer charateristic manage -------------------------------------

# recuperration des caracteristiques de la machine

class MachineInfoView(APIView):
    def get(self, request):
        infos = get_statics_infos()
        if not infos:
            return Response({"error": "Failed to retrieve machine information."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(infos, status=status.HTTP_200_OK)


from django.shortcuts import render
from .models import MachineInfo, EtatMachine, PreferenceModel, Task, TaskProgress
from django.db.models import Prefetch


def home(request):
    from volontaire.preferences_payload import build_preferences_payload, is_available_now

    machine = getattr(MachineInfo.objects, "get_last_inserted", lambda: None)()
    if not machine:
        machine = MachineInfo.objects.order_by('-last_update').first()
    etat = EtatMachine.objects.filter(machine=machine).order_by('-timestamp').first() if machine else None
    preferences = PreferenceModel.objects.filter(machine=machine).first() if machine else None
    pref_summary = build_preferences_payload()
    available_now = is_available_now(pref_summary)

    tasks = Task.objects.all().order_by('-start_date')
    counts = {
        'total': tasks.count(),
        'running': 0,
        'pending': 0,
        'completed': 0,
        'failed': 0,
    }
    for task in tasks:
        last_progress = task.progress_events.order_by('-timestamp').first()
        task.progress = last_progress.percentage if last_progress else (
            100 if task.status in ('completed', 'complete') else 0
        )
        command = getattr(task, 'command', None)
        if not command and task.docker_information:
            command = task.docker_information.get('command') or task.docker_information.get('cmd')
        if not command and isinstance(task.parameters, dict):
            command = task.parameters.get('command')
        task.command = command or '—'
        st = (task.status or '').lower()
        if st in ('running', 'progress', 'started'):
            counts['running'] += 1
        elif st in ('pending', 'queued', 'assigned'):
            counts['pending'] += 1
        elif st in ('completed', 'complete'):
            counts['completed'] += 1
        elif st in ('failed', 'error', 'terminate', 'stopped'):
            counts['failed'] += 1

    context = {
        'machine': machine,
        'etat': etat,
        'preferences': preferences,
        'pref_summary': pref_summary,
        'available_now': available_now,
        'tasks': tasks,
        'counts': counts,
    }
    return render(request, 'home.html', context)



def tasks(request):
    tasks_list = Task.objects.all().order_by('-start_date')

    result = []
    for task in tasks_list:
        last_progress = task.progress_events.order_by('-timestamp').first()
        progress = last_progress.percentage if last_progress else 0

        # Récupérer la commande depuis docker_information ou parameters
        command = None
        if task.docker_information:
            command = task.docker_information.get('command', task.docker_information.get('cmd'))
        if not command and task.parameters:
            command = task.parameters.get('command')

        result.append({
            "id": task.task_id,
            "task_id": task.task_id,
            "progress": progress,
            "name": task.name,
            "status": task.status,
            "command": command
        })
    return JsonResponse(result, safe=False)


def task_details(request, task_id):
    """Récupère les détails complets d'une tâche"""
    try:
        task = Task.objects.get(task_id=task_id)
        last_progress = task.progress_events.order_by('-timestamp').first()
        progress = last_progress.percentage if last_progress else 0

        # Récupérer les fichiers d'entrée et sortie
        input_files = task.input_data.get('files', []) if task.input_data else []
        output_files = task.output_data.get('files', []) if task.output_data else []

        # Récupérer la commande depuis docker_information ou parameters
        command = None
        if task.docker_information:
            command = task.docker_information.get('command', task.docker_information.get('cmd'))
        if not command and task.parameters:
            command = task.parameters.get('command')

        return JsonResponse({
            'task_id': task.task_id,
            'name': task.name,
            'status': task.status,
            'progress': progress,
            'command': command,
            'docker_info': task.docker_information,
            'input_files': input_files,
            'output_files': output_files,
            'workflow_id': str(task.workflow.workflow_id) if task.workflow else None,
            'created_at': task.start_date.isoformat() if task.start_date else None,
            'end_date': task.end_date.isoformat() if task.end_date else None,
            'error_message': task.error_message,
            'execution_priority': task.execution_priority,
            'attempts': task.attempts,
            'container_id': task.container_id,
            'local_input_path': task.local_input_path,
        })
    except Task.DoesNotExist:
        return JsonResponse({'error': f'Tâche {task_id} non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ---------------------------  Gestion des preferences -----------------  


# -------- Enregistrement et mise a jour d'une Preferences 


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .models import PreferenceModel, JourDisponible, PlageHoraire, MachineInfo
from datetime import time


@csrf_exempt
def save_preferences(request):
    if request.method == 'POST':
        try:
            from volontaire.preferences_payload import (
                normalize_day,
                save_preferences_file,
                _machine_resources,
            )

            data = json.loads(request.body)
            machine = getattr(MachineInfo.objects, "get_last_inserted", lambda: None)()
            if not machine:
                machine = MachineInfo.objects.first()

            if machine:
                pref, _created = PreferenceModel.objects.get_or_create(machine=machine)
            else:
                pref = PreferenceModel.objects.filter(machine__isnull=True).first()
                if not pref:
                    pref = PreferenceModel.objects.create()

            slots = data.get("preferences") or []
            # Ressources: top-level ou premier créneau
            first = slots[0] if slots else {}
            cpu_pct = int(data.get("cpu_max_utilisation") or first.get("cpu") or 80)
            ram_gb = int(data.get("max_ram_gb") or first.get("ram") or 4)
            disk_gb = int(data.get("max_disk_gb") or first.get("disk") or 10)
            max_time = int(data.get("duree_max_execution") or first.get("maxTime") or 0)
            types_ok = data.get("types_calcul_autorises") or first.get("types") or ""

            machine_res = _machine_resources()
            max_cpu_cores = int(
                data.get("max_cpu_cores")
                or max(1, int(machine_res["cpu_cores"] * (cpu_pct / 100.0)))
            )

            pref.cpu_max_utilisation = max(1, min(100, cpu_pct))
            pref.ram_max_utilisation = ram_gb  # stocke aussi la RAM offerte (Go)
            pref.disk_max_utilisation = disk_gb
            pref.duree_max_execution = max(0, max_time)
            pref.notification_email = bool(data.get("notification_email", False))
            pref.priorite_min_acceptee = int(data.get("priorite_min_acceptee", 0) or 0)
            pref.types_calcul_autorises = types_ok
            pref.pauseActiviteUser = bool(data.get("pauseActiviteUser", False))
            pref.playInactiviteUser = int(data.get("playInactiviteUser", 0) or 0)
            pref.save()

            pref.jours.all().delete()
            schedule = []
            for jour_data in slots:
                jour_nom = normalize_day(jour_data.get("day") or jour_data.get("jour") or "")
                if not jour_nom:
                    continue
                jour_obj = JourDisponible.objects.create(preference=pref, jour=jour_nom)
                start_s = jour_data.get("startTime") or jour_data.get("start") or "00:00"
                end_s = jour_data.get("endTime") or jour_data.get("end") or "23:59"
                heure_debut = time.fromisoformat(start_s)
                heure_fin = time.fromisoformat(end_s)
                PlageHoraire.objects.create(
                    jour=jour_obj, heure_debut=heure_debut, heure_fin=heure_fin
                )
                schedule.append(
                    {"day": jour_nom, "start": start_s[:5], "end": end_s[:5]}
                )

            payload = {
                "cpu_max_utilisation": pref.cpu_max_utilisation,
                "max_cpu_cores": max_cpu_cores,
                "max_ram_gb": ram_gb,
                "max_disk_gb": disk_gb,
                "duree_max_execution": pref.duree_max_execution,
                "priorite_min_acceptee": pref.priorite_min_acceptee,
                "types_calcul_autorises": pref.types_calcul_autorises or "",
                "schedule": schedule,
                "machine_cpu_cores": machine_res["cpu_cores"],
                "machine_ram_mb": machine_res["ram_mb"],
                "machine_disk_gb": machine_res["disk_gb"],
            }
            save_preferences_file(payload)

            # Publier immédiatement un heartbeat avec les nouvelles préférences
            try:
                from redis_communication.task_handlers import TaskManager

                tm = TaskManager.get_instance()
                if tm.volunteer_id:
                    tm._send_heartbeat()
            except Exception:
                pass

            return JsonResponse({"success": True, "message": "Préférences enregistrées.", "preferences": payload})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse({"error": "Méthode non autorisée."}, status=405)


#  ----------------Suppression de la preference 


from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

@csrf_exempt
def delete_preferences(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            if data.get("action") == "delete_all":
                machine = MachineInfo.objects.first()  # ou ta logique machine réelle
                preference = PreferenceModel.objects.filter(machine=machine).first()
                if preference:
                    preference.delete()
                    return JsonResponse({'message': 'Préférences supprimées'}, status=200)
                else:
                    return JsonResponse({'message': 'Aucune préférence trouvée'}, status=404)
            else:
                return JsonResponse({'error': 'Action inconnue'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


# suppression d'une preference en particulie


@csrf_exempt  # Pour tests rapides, sinon gérer le CSRF token côté JS
def delete_preference(request, id):
    if request.method == "DELETE":
        pref = get_object_or_404(PreferenceModel, id=id)
        pref.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)



def preferences_list(request):
    from volontaire.preferences_payload import build_preferences_payload, load_preferences_file

    payload = load_preferences_file() or build_preferences_payload()
    schedule = payload.get("schedule") or []
    prefs = []
    for index, slot in enumerate(schedule):
        prefs.append(
            {
                "id": index,
                "day": slot.get("day"),
                "startTime": slot.get("start"),
                "endTime": slot.get("end"),
                "cpu": payload.get("cpu_max_utilisation", 80),
                "ram": payload.get("max_ram_gb", 4),
                "disk": payload.get("max_disk_gb", 10),
                "maxTime": payload.get("duree_max_execution", 0),
                "types": payload.get("types_calcul_autorises", ""),
            }
        )
    # Inclure aussi le résumé global pour l'UI
    return JsonResponse(
        {
            "slots": prefs,
            "summary": payload,
        },
        safe=False,
    )


