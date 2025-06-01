from django.contrib import admin
from django.urls import path , include
from .views import MachineInfoView
from .views import DockerContainersStatusView
from .views import  home, handle_task_action

from communication.views import publier_message

urlpatterns = [
    path("pubsub/", publier_message),
    path("", home, name="home"),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path("api/docker/containers/", DockerContainersStatusView.as_view(), name="docker-containers-status"),
    # Gestion des actios sur conteneur
    path('task/<str:action>/<str:task_id>/', handle_task_action, name='handle_task_action'),
]
