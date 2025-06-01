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
            task = Task.objects.get(task_id=task_id)
            
            if action == 'pause':
                # Logique de pause ici
                task.status = 'paused'
            elif action == 'resume':
                # Logique de reprise ici
                task.status = 'running'
            elif action == 'suspend':
                # Logique de suspension ici
                task.status = 'suspended'
            elif action == 'delete':
                # Logique de suppression ici
                task.delete()
                return JsonResponse({'message': 'Tâche supprimée'}, status=200)

            task.save()
            return JsonResponse({'message': f'Action {action} effectuée'}, status=200)
        
        except Task.DoesNotExist:
            return JsonResponse({'error': 'Tâche non trouvée'}, status=404)
    
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


def home(request):
    # Récupérer les informations statics de la machine
    infos_raw = get_statics_infos()
    
    if not infos_raw:
        infos_raw = {"error": "Failed to retrieve machine information."}

    # Récupérer la liste des conteneurs
    containers = manager.list_tasks()  # assure-toi que `manager` est bien importé
    result = [
        {
            "id": c['id'],
            "name": c['name'],
            "status": c['status'],
            "image": c['image']
        } for c in containers
    ]

    # dictionnaire des icônes
    icon_map = {
        "volunteer_id": "fa-id-badge",
        "adresse_mac": "fa-network-wired",
        "machine_type": "fa-desktop",
        "system": "fa-cogs",
        "node_name": "fa-server",
        "host_name": "fa-server",
        "os_release": "fa-code-branch",
        "os_version": "fa-info",
        "machine_arch": "fa-microchip",
        "processor_name": "fa-microchip",
        "cpu_type": "fa-microchip",
        "cpu_cores": "fa-microchip",
        "cpu_logical_cores": "fa-microchip",
        "cpu_frequency": "fa-tachometer-alt",
        "total_memory": "fa-memory",
        "screen_resolution": "fa-tv",
        "total_disk": "fa-hdd"
    }

    # Structurer les infos avec icônes
    infos = [
        {
            "label": key.replace("_", " ").capitalize(),
            "value": ", ".join(value) if isinstance(value, list) else value,
            "icon": icon_map.get(key, "fa-info-circle")
        }
        for key, value in infos_raw.items()
    ]

    return render(request, 'home.html', {'infos': infos, 'containers': result})

 


# ---------------------------  Gestion des preferences -----------------  




from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .models import PreferenceModel, JourDisponible, PlageHoraire, MachineInfo
from datetime import time

@csrf_exempt  # ou utiliser @require_POST et inclure @csrf_protect avec le token
def enregistrer_preferences(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            prefs = data.get('preferences', [])

            # Supposons qu'on utilise la première machine (à adapter selon ton cas réel)
            machine = MachineInfo.objects.first()
            if not machine:
                return JsonResponse({'error': 'Machine introuvable'}, status=400)

            # Créer ou mettre à jour le modèle de préférences
            pref_model, _ = PreferenceModel.objects.get_or_create(machine=machine)
            JourDisponible.objects.filter(preference=pref_model).delete()

            jours_temp = {}

            for pref in prefs:
                jour = pref['day'].lower()
                start = pref['startTime']
                end = pref['endTime']

                # Associer chaque jour avec des plages
                if jour not in jours_temp:
                    jour_obj = JourDisponible.objects.create(preference=pref_model, jour=jour)
                    jours_temp[jour] = jour_obj
                else:
                    jour_obj = jours_temp[jour]

                # Enregistrer la plage horaire
                PlageHoraire.objects.create(
                    jour=jour_obj,
                    heure_debut=time.fromisoformat(start),
                    heure_fin=time.fromisoformat(end)
                )

            return JsonResponse({'message': 'Préférences enregistrées'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)





'''
from django.shortcuts import render, get_object_or_404
from .models import PreferenceModel
from .forms import PreferenceForm

def preference_view(request, machine_id):
    preferences = get_object_or_404(PreferenceModel, machine_id=machine_id)
    if request.method == 'POST':
        form = PreferenceForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
    else:
        form = PreferenceForm(instance=preferences)
    return render(request, 'home.html', {'form': form})



from django.shortcuts import render, get_object_or_404, redirect
from .models import PreferenceModel, MachineInfo, JourDisponible
from .forms import PreferenceForm, JourDisponibleForm, PlageHoraireFormSet
from django.forms import modelformset_factory
from django.contrib import messages

def preference_view(request):
    # --- 1. Trouver la machine locale ---
    machine = MachineInfo.objects.first()  # à adapter si tu veux la machine en cours

    if not machine:
        messages.error(request, "Aucune machine trouvée.")
        return redirect("home")

    # --- 2. Charger ou créer la préférence ---
    preference, created = PreferenceModel.objects.get_or_create(machine=machine)

    # --- 3. Préparer le formulaire principal ---
    pref_form = PreferenceForm(request.POST or None, instance=preference)

    # --- 4. Préparer le formulaire pour jours disponibles ---
    JourFormSet = modelformset_factory(JourDisponible, form=JourDisponibleForm, extra=1, can_delete=True)
    jour_formset = JourFormSet(request.POST or None, queryset=JourDisponible.objects.filter(preference=preference))

    # --- 5. Traiter la soumission ---
    if request.method == "POST":
        if pref_form.is_valid() and jour_formset.is_valid():
            pref_form.save()
            jour_instances = jour_formset.save(commit=False)

            for form in jour_formset.deleted_forms:
                if form.instance.pk:
                    form.instance.delete()

            for jour in jour_instances:
                jour.preference = preference
                jour.save()

            messages.success(request, "Préférences enregistrées avec succès.")
            return redirect("preference_view")

        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")

    return render(request, "preferences/preferences_form.html", {
        "pref_form": pref_form,
        "jour_formset": jour_formset,
    })
'''