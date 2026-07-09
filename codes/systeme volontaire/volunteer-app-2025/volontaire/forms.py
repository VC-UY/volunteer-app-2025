from django import forms
from .models import PreferenceModel, JourDisponible, PlageHoraire
from django.forms import inlineformset_factory


# ----------------------------
# Formulaire principal : Préférences générales
class PreferenceForm(forms.ModelForm):
    class Meta:
        model = PreferenceModel
        fields = [
            'cpu_max_utilisation',
            'ram_max_utilisation',
            'disk_max_utilisation',
            'collection_interval',
            'send_interval',
            'available_hours_start',
            'available_hours_end',
            'available_days',
            'notify_on_task_assignment',
            'notify_on_resource_threshold',
            'priorite_min_acceptee',
            'duree_max_execution',
            'notification_email',
            'pauseActiviteUser',
            'playInactiviteUser',
            'types_calcul_autorises',
        ]
        widgets = {
            'available_days': forms.CheckboxSelectMultiple(choices=[
                (0, 'Lundi'), (1, 'Mardi'), (2, 'Mercredi'),
                (3, 'Jeudi'), (4, 'Vendredi'), (5, 'Samedi'), (6, 'Dimanche')
            ]),
            'types_calcul_autorises': forms.TextInput(attrs={'placeholder': 'Ex: calcul1, calcul2'}),
        }


# ----------------------------
# Formulaire pour un jour disponible
class JourDisponibleForm(forms.ModelForm):
    class Meta:
        model = JourDisponible
        fields = ['jour']


# ----------------------------
# Formulaire pour une plage horaire d’un jour donné
class PlageHoraireForm(forms.ModelForm):
    class Meta:
        model = PlageHoraire
        fields = ['heure_debut', 'heure_fin']


# ----------------------------
# Formsets (si besoin de gérer plusieurs plages par jour)
PlageHoraireFormSet = inlineformset_factory(
    JourDisponible, PlageHoraire,
    form=PlageHoraireForm,
    extra=1,
    can_delete=True
)
