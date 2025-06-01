from django.apps import AppConfig
import threading

class VolontaireConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'volontaire'




    def ready(self):
        from .initializers import initialize_machine_info
        threading.Thread(target=initialize_machine_info).start()



    # def ready(self):
    #     import volontaire.signals
