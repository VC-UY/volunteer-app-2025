from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class MachineInfoManager(models.Manager):
    def get_last_inserted(self):
        try:
            return self.latest('id')
        except self.model.DoesNotExist:
            return None


# Modèle des informations statiques de la machine
class MachineInfo(models.Model):
    objects = MachineInfoManager()
    # Identifiants
    volunteer_id = models.UUIDField(unique=True,null=True, blank=True, editable=False)
    adresse_mac = models.JSONField(default=list, help_text="Liste des adresses MAC de la machine")

    # Informations d'authentification
    username = models.CharField(max_length=255, default="", help_text="Nom d'utilisateur")
    password = models.CharField(max_length=255, default="", help_text="Mot de passe")
    
    # Informations sur le système d'exploitation
    os_name = models.CharField(max_length=50, default="", help_text="Nom du système d'exploitation")
    os_version = models.CharField(max_length=100, default="", help_text="Version du système d'exploitation")
    os_release = models.CharField(max_length=100, default="", help_text="Release du système d'exploitation")
    os_architecture = models.CharField(max_length=50, default="", help_text="Architecture du système d'exploitation")
    hostname = models.CharField(max_length=255, default="", help_text="Nom d'hôte de la machine")
    
    # Type de machine
    machine_tipe = models.CharField(max_length=50, default="", help_text="Type de machine (Portable, PC de bureau, etc.)")
    
    # Informations sur le processeur
    cpu_modele = models.CharField(max_length=100, default="", help_text="Type de processeur")
    cpu_architecture = models.CharField(max_length=50, default="", help_text="Architecture du processeur")
    cpu_bits = models.CharField(max_length=10, default="", help_text="Nombre de bits du processeur (32-bit, 64-bit)")
    cpu_cores_physical = models.IntegerField(default=1, help_text="Nombre de cœurs physiques")
    cpu_cores_logical = models.IntegerField(default=1, help_text="Nombre de cœurs logiques")
    cpu_frequency_current = models.FloatField(null=True, blank=True, help_text="Fréquence actuelle du processeur en MHz")
    cpu_frequency_min = models.FloatField(null=True, blank=True, help_text="Fréquence minimale du processeur en MHz")
    cpu_frequency_max = models.FloatField(null=True, blank=True, help_text="Fréquence maximale du processeur en MHz")
    
    # Informations sur la mémoire
    ram_total = models.BigIntegerField(default=0, help_text="Mémoire RAM totale en octets")
    ram_total_human = models.CharField(max_length=20, default="0", help_text="Mémoire RAM totale en format lisible")
    swap_total = models.BigIntegerField(default=0, help_text="Mémoire swap totale en octets")
    swap_total_human = models.CharField(max_length=20, default="0", help_text="Mémoire swap totale en format lisible")
    
    # Informations sur le disque
    disk_total = models.BigIntegerField(default=0, help_text="Espace disque total en octets")
    disk_total_human = models.CharField(max_length=20, default="0", help_text="Espace disque total en format lisible")
    partitions = models.JSONField(default=list, help_text="Liste des partitions de disque")
    
    # Informations sur l'écran
    screen_resolution = models.CharField(max_length=50, default="", help_text="Résolution de l'écran")
    
    # Informations sur le réseau
    network_interfaces = models.JSONField(default=list, help_text="Liste des interfaces réseau")
    
    # Informations sur le BIOS et la carte mère
    bios_info = models.JSONField(default=dict, null=True, blank=True, help_text="Informations sur le BIOS")
    motherboard_info = models.JSONField(default=dict, null=True, blank=True, help_text="Informations sur la carte mère")
    
    # Informations sur les périphériques USB
    usb_devices = models.JSONField(default=list, null=True, blank=True, help_text="Liste des périphériques USB")
    
    # Informations sur les utilisateurs connectés
    logged_users = models.JSONField(default=list, help_text="Liste des utilisateurs connectés")
    
    # Métadonnées
    last_update = models.DateTimeField(default=timezone.now, help_text="Dernière mise à jour des informations")
    registration_date = models.DateTimeField(auto_now_add=True, help_text="Date d'enregistrement de la machine")
    
    # Données brutes (pour stocker toutes les informations collectées)
    raw_data = models.JSONField(default=dict, null=True, blank=True, help_text="Données brutes collectées")

    def __str__(self):
        return f"{self.hostname} ({self.machine_tipe})"

# Modèle des informations variables de la machine

class EtatMachine(models.Model):
    VOLUNTEER_STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
    ]

    # Référence à la machine
    machine = models.ForeignKey(MachineInfo, on_delete=models.CASCADE, related_name='etats')
    
    # Horodatage
    timestamp = models.DateTimeField(auto_now_add=True, help_text="Horodatage de la collecte")
    
    # Informations sur le CPU
    cpu_usage_global = models.FloatField(default=0, help_text="Utilisation globale du CPU en pourcentage")
    cpu_usage_per_core = models.JSONField(default=list, help_text="Utilisation du CPU par cœur")
    cpu_temperature = models.FloatField(null=True, blank=True, help_text="Température du CPU en degrés Celsius")
    
    # Informations sur la mémoire RAM
    ram_used = models.BigIntegerField(default=0, help_text="Mémoire RAM utilisée en octets")
    ram_used_human = models.CharField(max_length=20, default="0", help_text="Mémoire RAM utilisée en format lisible")
    ram_available = models.BigIntegerField(default=0, help_text="Mémoire RAM disponible en octets")
    ram_available_human = models.CharField(max_length=20, default="0", help_text="Mémoire RAM disponible en format lisible")
    ram_percent_used = models.FloatField(default=0, help_text="Pourcentage d'utilisation de la RAM")
    ram_percent_free = models.FloatField(default=0, help_text="Pourcentage de RAM libre")
    
    # Informations sur la mémoire swap
    swap_used = models.BigIntegerField(default=0, help_text="Mémoire swap utilisée en octets")
    swap_used_human = models.CharField(max_length=20, default="0", help_text="Mémoire swap utilisée en format lisible")
    swap_free = models.BigIntegerField(default=0, help_text="Mémoire swap libre en octets")
    swap_free_human = models.CharField(max_length=20, default="0", help_text="Mémoire swap libre en format lisible")
    swap_percent_used = models.FloatField(default=0, help_text="Pourcentage d'utilisation du swap")
    swap_percent_free = models.FloatField(default=0, help_text="Pourcentage de swap libre")
    
    # Informations sur le cache
    cache_used = models.BigIntegerField(default=0, null=True, blank=True, help_text="Mémoire cache utilisée en octets")
    cache_used_human = models.CharField(max_length=20, null=True, blank=True, help_text="Mémoire cache utilisée en format lisible")
    
    # Informations sur le disque
    disk_percent_used = models.FloatField(default=0, help_text="Pourcentage d'utilisation du disque")
    disk_percent_free = models.FloatField(default=0, help_text="Pourcentage de disque libre")
    
    # Informations sur le GPU
    gpu_usage = models.JSONField(default=list, null=True, blank=True, help_text="Utilisation du GPU")
    
    # Informations sur le réseau
    net_bytes_sent = models.BigIntegerField(default=0, help_text="Octets envoyés")
    net_bytes_sent_human = models.CharField(max_length=20, default="0", help_text="Octets envoyés en format lisible")
    net_bytes_received = models.BigIntegerField(default=0, help_text="Octets reçus")
    net_bytes_received_human = models.CharField(max_length=20, default="0", help_text="Octets reçus en format lisible")
    net_packets_sent = models.BigIntegerField(default=0, help_text="Paquets envoyés")
    net_packets_received = models.BigIntegerField(default=0, help_text="Paquets reçus")
    net_errors_in = models.IntegerField(default=0, help_text="Erreurs en réception")
    net_errors_out = models.IntegerField(default=0, help_text="Erreurs en envoi")
    net_drop_in = models.IntegerField(default=0, help_text="Paquets supprimés en réception")
    net_drop_out = models.IntegerField(default=0, help_text="Paquets supprimés en envoi")
    
    # Informations sur la connexion Internet
    internet_connected = models.BooleanField(default=False, help_text="Connexion Internet active")
    
    # Informations sur les processus
    process_count = models.IntegerField(default=1, help_text="Nombre de processus actifs")
    
    # Informations sur la batterie
    battery = models.JSONField(default=dict, null=True, blank=True, help_text="Informations sur la batterie")
    
    # Informations sur l'uptime
    uptime = models.CharField(max_length=50, default="0", help_text="Temps de fonctionnement")
    uptime_seconds = models.BigIntegerField(default=0, help_text="Temps de fonctionnement en secondes")
    
    # Informations sur le seuil d'utilisation des ressources
    threshold_reached = models.JSONField(default=dict, null=True, blank=True, help_text="Seuils d'utilisation des ressources atteints")
    
    # Statut du volontaire
    statut_actuel = models.CharField(
        max_length=10,
        choices=VOLUNTEER_STATUS_CHOICES,
        default="available",
        help_text="Statut actuel du volontaire"
    )
    
    # Données brutes (pour stocker toutes les informations collectées)
    raw_data = models.JSONField(default=dict, null=True, blank=True, help_text="Données brutes collectées")

    def __str__(self):
        return f"État de {self.machine.hostname} à {self.timestamp}"





# --------------------------------------------- Modèle de préférences
class PreferenceModel(models.Model):
    # Machine associée (nullable pour permettre la création sans machine)
    machine = models.OneToOneField(MachineInfo, on_delete=models.CASCADE, related_name='preferences', null=True, blank=True)
    
    # Préférences d'utilisation des ressources
    cpu_max_utilisation = models.IntegerField(default=80, help_text="Utilisation maximale du CPU en pourcentage")
    ram_max_utilisation = models.IntegerField(default=80, help_text="Utilisation maximale de la RAM en pourcentage")
    disk_max_utilisation = models.IntegerField(default=90, help_text="Utilisation maximale du disque en pourcentage")
    
    # Préférences de collecte de données
    collection_interval = models.IntegerField(default=60, help_text="Intervalle de collecte des données en secondes")
    send_interval = models.IntegerField(default=300, help_text="Intervalle d'envoi des données en secondes")
    
    # Préférences de disponibilité
    available_hours_start = models.TimeField(null=True, blank=True, help_text="Heure de début de disponibilité")
    available_hours_end = models.TimeField(null=True, blank=True, help_text="Heure de fin de disponibilité")
    available_days = models.JSONField(default=list, help_text="Jours de disponibilité (0-6, 0=lundi)")
    
    # Préférences de notification
    notify_on_task_assignment = models.BooleanField(default=True, help_text="Notifier lors de l'assignation d'une tâche")
    notify_on_resource_threshold = models.BooleanField(default=True, help_text="Notifier lorsqu'un seuil de ressource est atteint")
    
    def __str__(self):
        return f"Préférences pour {self.machine.hostname}"

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

# Preference Management Model

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

# End Preference


#  -------------- Workflow And Task Model 




# --------------------- Workflow


class Workflow(models.Model):
    name = models.CharField(max_length=255)
    workflow_id = models.CharField(max_length=255, unique=True, null=True)
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
    command = models.CharField(max_length=500, null=True, blank=True)
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
    runtime_info = models.JSONField(null=True, blank=True)

    # Chemin local des fichiers d'entrée téléchargés
    local_input_path = models.CharField(max_length=500, null=True, blank=True)

    # New field to store Docker container ID
    container_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name


class TaskProgress(models.Model):
    """
    Modèle pour suivre la progression d'une tâche.
    Chaque entrée représente un événement de progression pour une tâche spécifique.
    """
    PROGRESS_TYPE_CHOICES = [
        ('start', 'Démarrage'),
        ('progress', 'Progression'),
        ('complete', 'Terminée'),
        ('error', 'Erreur'),
        ('cancel', 'Annulée'),
    ]
    
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='progress_events')
    timestamp = models.DateTimeField(auto_now_add=True)
    progress_type = models.CharField(max_length=20, choices=PROGRESS_TYPE_CHOICES)
    percentage = models.FloatField(default=0)
    message = models.TextField(blank=True, null=True)
    details = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['timestamp']
        verbose_name = 'Progression de tâche'
        verbose_name_plural = 'Progressions de tâches'
    
    def __str__(self):
        return f"{self.task.name} - {self.progress_type} ({self.percentage}%)"
