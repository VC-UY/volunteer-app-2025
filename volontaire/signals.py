from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import MachineInfo, PreferenceModel

@receiver(post_save, sender=MachineInfo)
def create_preferences_for_machine(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'preferences'):
        PreferenceModel.objects.create(machine=instance)
