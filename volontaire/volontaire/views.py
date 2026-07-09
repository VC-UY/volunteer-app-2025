from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from volontaire.utils.get_info import get_statics_infos
from volontaire.docker_manager import DockerManager
from django.shortcuts import render


# Utiliser l'instance singleton de DockerManager
manager = DockerManager.get_instance()



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
            ok = False

            if action == 'pause':
                ok = task_manager.pause_task(task_id)
            elif action in ['resume', 'replay']:
                ok = task_manager.resume_task(task_id)
            elif action in ['stop', 'suspend']:
                ok = task_manager.stop_task(task_id)
            elif action == 'delete':
                task_manager.stop_task(task_id)
                task.delete()
                return JsonResponse({'message': 'Tâche supprimée'}, status=200)
            elif action == 'limit_cpu':
                cpu_quota = int(request.POST.get('cpu_quota', 50000))
                ok = task_manager.update_limits(task_id, cpu_quota=cpu_quota)
            elif action == 'limit_ram':
                mem_limit = request.POST.get('mem_limit', '500m')
                ok = task_manager.update_limits(task_id, mem_limit=mem_limit)
            else:
                return JsonResponse({'error': f'Action inconnue: {action}'}, status=400)

            if not ok:
                return JsonResponse(
                    {'error': f"Action '{action}' impossible pour la tâche {task_id} (statut: {task.status})"},
                    status=400,
                )

            task.refresh_from_db()
            return JsonResponse({'message': f'Action {action} effectuée', 'status': task.status}, status=200)

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
from .models import MachineInfo, EtatMachine, PreferenceModel, Task, TaskProgress, Workflow
from django.db.models import Prefetch


def home(request):
    # Utiliser le manager pour récupérer la dernière machine insérée
    machine = MachineInfo.objects.get_last_inserted()

    # Si aucune machine n'existe, créer des valeurs par défaut
    if not machine:
        # Créer une machine par défaut ou retourner des valeurs vides
        context = {
            'machine': None,
            'etat': None,
            'preferences': None,
            'tasks': [],
        }
        return render(request, 'home.html', context)

    # Récupérer le dernier état et les préférences
    etat = EtatMachine.objects.filter(machine=machine).order_by('-timestamp').first()

    # Récupérer ou créer les préférences pour cette machine
    preferences, created = PreferenceModel.objects.get_or_create(machine=machine)

    # Toutes les tâches, avec progression la plus récente
    tasks = Task.objects.all().order_by('-start_date')
    for task in tasks:
        last_progress = task.progress_events.order_by('-timestamp').first()
        task.progress = last_progress.percentage if last_progress else 0

    context = {
        'machine': machine,
        'etat': etat,
        'preferences': preferences,
        'tasks': tasks,
    }
    return render(request, 'home.html', context)



def _task_command_and_description(task):
    command = getattr(task, 'command', None)
    description = ''
    params = task.parameters if isinstance(task.parameters, dict) else {}
    if not command and task.docker_information:
        command = task.docker_information.get('command', task.docker_information.get('cmd'))
    if not command and params:
        command = params.get('command')
    if params:
        description = params.get('description', '') or ''
    return command, description


def tasks(request):
    tasks_list = Task.objects.select_related('workflow').all().order_by('-start_date')
    result = []
    for task in tasks_list:
        last_progress = task.progress_events.order_by('-timestamp').first()
        progress = last_progress.percentage if last_progress else 0
        command, description = _task_command_and_description(task)
        params = task.parameters if isinstance(task.parameters, dict) else {}
        result.append({
            "id": task.task_id,
            "task_id": task.task_id,
            "progress": progress,
            "name": task.name,
            "description": description,
            "status": task.status,
            "command": command,
            "workflow_id": str(task.workflow.workflow_id) if task.workflow else None,
            "workflow_name": getattr(task.workflow, "name", None) if task.workflow else None,
            "workflow_description": getattr(task.workflow, "description", None) if task.workflow else None,
            "workflow_type": params.get('workflow_type', ''),
        })
    return JsonResponse(result, safe=False)


def workflows_list(request):
    workflows = []
    for wf in Workflow.objects.all().order_by('-modification_date'):
        wf_tasks = Task.objects.filter(workflow=wf).order_by('start_date', 'id')
        task_items = []
        counts = {'total': 0, 'running': 0, 'pending': 0, 'completed': 0, 'failed': 0}
        for task in wf_tasks:
            last_progress = task.progress_events.order_by('-timestamp').first()
            progress = last_progress.percentage if last_progress else 0
            command, description = _task_command_and_description(task)
            st = (task.status or '').lower()
            counts['total'] += 1
            if st in ('running', 'progress', 'started', 'in_progress'):
                counts['running'] += 1
            elif st in ('pending', 'queued', 'assigned', 'created', 'accepted'):
                counts['pending'] += 1
            elif st in ('completed', 'complete'):
                counts['completed'] += 1
            elif st in ('failed', 'error', 'stopped', 'cancelled', 'canceled'):
                counts['failed'] += 1
            else:
                counts['pending'] += 1
            task_items.append({
                "task_id": task.task_id,
                "name": task.name,
                "description": description,
                "status": task.status,
                "progress": progress,
                "command": command,
            })
        workflows.append({
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description or "",
            "active": wf.active,
            "creation_date": wf.creation_date.isoformat() if wf.creation_date else None,
            "task_counts": counts,
            "tasks": task_items,
        })
    return JsonResponse(workflows, safe=False)


def workflow_details(request, workflow_id):
    try:
        wf = Workflow.objects.get(workflow_id=workflow_id)
    except Workflow.DoesNotExist:
        return JsonResponse({'error': f'Workflow {workflow_id} introuvable'}, status=404)

    wf_tasks = Task.objects.filter(workflow=wf).order_by('start_date', 'id')
    task_items = []
    for task in wf_tasks:
        last_progress = task.progress_events.order_by('-timestamp').first()
        progress = last_progress.percentage if last_progress else 0
        command, description = _task_command_and_description(task)
        task_items.append({
            "task_id": task.task_id,
            "name": task.name,
            "description": description,
            "status": task.status,
            "progress": progress,
            "command": command,
        })

    return JsonResponse({
        "workflow_id": wf.workflow_id,
        "name": wf.name,
        "description": wf.description or "",
        "active": wf.active,
        "creation_date": wf.creation_date.isoformat() if wf.creation_date else None,
        "modification_date": wf.modification_date.isoformat() if wf.modification_date else None,
        "tasks": task_items,
    })


def task_details(request, task_id):
    try:
        task = Task.objects.get(task_id=task_id)
        last_progress = task.progress_events.order_by('-timestamp').first()
        progress = last_progress.percentage if last_progress else 0
        input_files = task.input_data.get('files', []) if task.input_data else []
        output_files = task.output_data.get('files', []) if task.output_data else []
        command, description = _task_command_and_description(task)
        return JsonResponse({
            'task_id': task.task_id,
            'name': task.name,
            'description': description,
            'status': task.status,
            'progress': progress,
            'command': command,
            'docker_info': task.docker_information,
            'input_files': input_files,
            'output_files': output_files,
            'workflow_id': str(task.workflow.workflow_id) if task.workflow else None,
            'workflow_name': getattr(task.workflow, 'name', None) if task.workflow else None,
            'workflow_description': getattr(task.workflow, 'description', None) if task.workflow else None,
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


@csrf_exempt  # ou utiliser @require_POST et inclure @csrf_protect avec le token
def save_preferences(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # Récupérer la dernière machine insérée
            machine = MachineInfo.objects.get_last_inserted()

            if not machine:
                return JsonResponse({"success": False, "error": "Aucune machine trouvée. Veuillez d'abord enregistrer les informations de la machine."}, status=404)

            # Créer ou mettre à jour les préférences
            pref, created = PreferenceModel.objects.get_or_create(machine=machine)

            # Mettre à jour les champs simples
            pref.cpu_max_utilisation = data.get('cpu_max_utilisation', 80)
            pref.ram_max_utilisation = data.get('ram_max_utilisation', 80)
            pref.disk_max_utilisation = data.get('disk_max_utilisation', 90)
            pref.duree_max_execution = data.get('duree_max_execution', 0)
            pref.notification_email = data.get('notification_email', False)
            pref.priorite_min_acceptee = data.get('priorite_min_acceptee', 0)
            pref.types_calcul_autorises = data.get('types_calcul_autorises', "")
            pref.pauseActiviteUser = data.get('pauseActiviteUser', False)
            pref.playInactiviteUser = data.get('playInactiviteUser', 0)

            pref.save()

            # Nettoyer les anciens jours et créneaux
            pref.jours.all().delete()

            # Ajouter les jours et plages horaires
            for jour_data in data.get("preferences", []):
                jour_nom = jour_data["day"]
                jour_obj = JourDisponible.objects.create(preference=pref, jour=jour_nom)

                heure_debut = time.fromisoformat(jour_data["startTime"])
                heure_fin = time.fromisoformat(jour_data["endTime"])

                PlageHoraire.objects.create(jour=jour_obj, heure_debut=heure_debut, heure_fin=heure_fin)

            return JsonResponse({"success": True, "message": "Préférences enregistrées."})
        
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

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
                # Utiliser la dernière machine insérée
                machine = MachineInfo.objects.get_last_inserted()
                if not machine:
                    return JsonResponse({'error': 'Aucune machine trouvée'}, status=404)

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
    # Récupérer les préférences pour la dernière machine insérée
    machine = MachineInfo.objects.get_last_inserted()

    if not machine:
        return JsonResponse([], safe=False)

    prefs = []
    preference = PreferenceModel.objects.filter(machine=machine).first()

    if preference:
        for jour in preference.jours.all():
            for plage in jour.plages.all():
                prefs.append({
                    "id": plage.id,  # L'id utilisé pour la suppression
                    "day": jour.jour,
                    "startTime": plage.heure_debut.strftime('%H:%M'),
                    "endTime": plage.heure_fin.strftime('%H:%M'),
                    "cpu": preference.cpu_max_utilisation,
                    "ram": preference.ram_max_utilisation,
                    "maxTime": preference.duree_max_execution
                })

    return JsonResponse(prefs, safe=False)


