from django.urls import path 
from .views import ( 
    home, 
    handle_task_action, 
    save_preferences,
    preferences_list,
    MachineInfoView,
    DockerContainersStatusView,
    delete_preference,
    delete_preferences,
    tasks,
    )

urlpatterns = [
    path("", home, name="home"),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path("api/docker/containers/", DockerContainersStatusView.as_view(), name="docker-containers-status"),
    # Gestion des actios sur conteneur
    path('api/task/<str:task_id>/<str:action>/', handle_task_action, name='handle_task_action'),
    # ------Gestion des preferences
    # Suvegarde et mise a jour de preference
    path('save_preferences/', save_preferences, name='save_preferences'),
    path('preferences/', preferences_list, name='preferences_list'),
    # supprission des preferences
    path("preferences/delete/", delete_preferences, name="delete_preferences"),
    # suppression d'une preference en particulier
    path('preferences/delete/<int:id>/', delete_preference, name='delete_preference'),
    path('tasks/', tasks, name='tasks'),

]
