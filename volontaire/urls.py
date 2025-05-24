from django.contrib import admin
from django.urls import path , include
from .views import MachineInfoView, home, DockerContainersStatusView

from communication.views import publier_message

urlpatterns = [
    path('admin/', admin.site.urls),
    path("pubsub/", publier_message),
    path("", home, name="home"),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path("api/docker/containers/", DockerContainersStatusView.as_view(), name="docker-containers-status")
]
