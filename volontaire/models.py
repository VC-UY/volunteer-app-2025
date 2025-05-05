from django.db import models
# from django.contrib.postgres.fields import JSONField, ArrayField
from django.db.models import JSONField
from django.utils import timezone
import uuid
from django.db import models
from django.core.exceptions import ValidationError
# Create your models here.

# 

# model des information statique

from django.db import models

class MachineInfo(models.Model):
    volunteer_id =models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    adresse_mac = models.JSONField(default=list)
    machine_type = models.CharField(max_length=50)
    system = models.CharField(max_length=50)
    node_name = models.CharField(max_length=100)
    host_name = models.CharField(max_length=255)
    os_release = models.CharField(max_length=100)
    os_version = models.CharField(max_length=100)
    machine_arch = models.CharField(max_length=50)
    processor_name = models.CharField(max_length=100)
    
    cpu_type = models.CharField(max_length=100)
    cpu_cores = models.IntegerField()
    cpu_logical_cores = models.IntegerField()
    cpu_frequency = models.FloatField(null=True, blank=True)

    total_memory = models.BigIntegerField()
    screen_resolution = models.CharField(max_length=50)

    total_disk = models.BigIntegerField()

    last_update = models.DateTimeField(default=timezone.now)
    registration_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mac_address} ({self.machine_type})"


# model des information variable


class EtatMachine(models.Model):

    VOLUNTEER_STATUS_CHOICES = [
    ('available', 'Available'),
    ('busy', 'Busy'),
    ('offline', 'Offline'),
]

    machine = models.ForeignKey(MachineInfo, on_delete=models.CASCADE, related_name='etats')

    used_memory = models.BigIntegerField()
    memory_usage = models.FloatField()
    cache = models.BigIntegerField()

    swap_total = models.BigIntegerField()
    swap_used = models.BigIntegerField()
    swap_percentage = models.FloatField()

    used_disk = models.BigIntegerField()
    disk_percentage = models.FloatField()

    cpu_usage_per_core = models.JSONField()
    gpu_usage_percentage = models.FloatField()
    cpu_temperature = models.FloatField()

    net_bytes_sent = models.BigIntegerField()
    net_bytes_received = models.BigIntegerField()

    battery_percentage = models.FloatField()
    uptime = models.BigIntegerField()
    boot_time = models.DateTimeField()
    shutdown_time = models.DateTimeField(null=True, blank=True)

    internet_enabled = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)

    statut_actuel = models.CharField(
        max_length=10,
        choices=VOLUNTEER_STATUS_CHOICES,
        default="available"
    )

    def __str__(self):
        return f"État de {self.machine.mac_address} à {self.timestamp}"





# --------------------------------------------- Preference Model



class PreferenceModel(models.Model):
    cpu_max_utilisation = models.IntegerField(default=100)
    ram_max_utilisation = models.IntegerField(default=100)
    priorite_min_acceptee = models.IntegerField(default=0)
    duree_max_execution = models.IntegerField(default=0)
    notification_email = models.BooleanField(default=False)
    pauseActiviteUser = models.BooleanField(default=False)
    playInactiviteUser = models.IntegerField(default=0)
    types_calcul_autorises = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Préférence #{self.id}"

    class Meta:
        verbose_name = "Préférence"
        verbose_name_plural = "Préférences"


class JourDisponible(models.Model):
    JOUR_CHOICES = [
        ("lundi", "Lundi"),
        ("mardi", "Mardi"),
        ("mercredi", "Mercredi"),
        ("jeudi", "Jeudi"),
        ("vendredi", "Vendredi"),
        ("samedi", "Samedi"),
        ("dimanche", "Dimanche"),
    ]

    preference = models.ForeignKey(PreferenceModel, related_name="jours", on_delete=models.CASCADE)
    jour = models.CharField(max_length=10, choices=JOUR_CHOICES)

    def __str__(self):
        return f"{self.jour} ({self.preference})"


class PlageHoraire(models.Model):
    jour = models.ForeignKey(JourDisponible, related_name="plages", on_delete=models.CASCADE)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()

    def clean(self):
        if self.heure_debut >= self.heure_fin:
            raise ValidationError("L'heure de début doit être avant l'heure de fin.")
        
        # Vérifier les chevauchements
        for plage in PlageHoraire.objects.filter(jour=self.jour).exclude(pk=self.pk):
            if not (self.heure_fin <= plage.heure_debut or self.heure_debut >= plage.heure_fin):
                raise ValidationError("Cette plage horaire chevauche une autre plage existante.")

    def __str__(self):
        return f"{self.heure_debut} - {self.heure_fin} ({self.jour.jour})"




#  -------------- Workflow And Task Model 




# --------------------- Workflow


class Workflow(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)  # Pour activer/désactiver le workflow

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Workflow"
        verbose_name_plural = "Workflows"



# ------------------------------ Global tasks



from django.db import models

class Task(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    task_id = models.CharField(max_length=50)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    parameters = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    attempts = models.IntegerField(default=0)
    results = models.JSONField(null=True, blank=True)
    dependencies = models.JSONField(null=True, blank=True)  # Replaces ArrayField
    execution_priority = models.IntegerField(default=0)
    estimated_execution_time = models.IntegerField(null=True, blank=True)
    actual_execution_time = models.IntegerField(null=True, blank=True)
    input_data_size = models.IntegerField(null=True, blank=True)
    output_data_size = models.IntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    checkpoints = models.JSONField(null=True, blank=True)
    input_data = models.JSONField(null=True, blank=True)
    output_data = models.JSONField(null=True, blank=True)
    docker_information = models.JSONField(null=True, blank=True)

    # New field to store Docker container ID
    container_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.title
