from django.contrib import admin
from django.urls import path , include
from .views import MachineInfoView, delete_preference, delete_preferences
from .views import DockerContainersStatusView
from .views import ( 
    home, 
    handle_task_action, 
    save_preferences,
    )

from communication.views import publier_message

urlpatterns = [
    path("pubsub/", publier_message),
    path("", home, name="home"),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path("api/docker/containers/", DockerContainersStatusView.as_view(), name="docker-containers-status"),
    # Gestion des actios sur conteneur
    path('task/<str:action>/<str:task_id>/', handle_task_action, name='handle_task_action'),
    # ------Gestion des preferences
    # Suvegarde et mise a jour de preference
    path('save_preferences/', save_preferences, name='save_preferences'),
    # supprission des preferences
    path("preferences/delete/", delete_preferences, name="delete_preferences"),
    # suppression d'une preference en particulier
    path('preferences/delete/<int:id>/', delete_preference, name='delete_preference'),
    

]
