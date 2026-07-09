from django.urls import path
from .views import (
    home,
    handle_task_action,
    save_preferences,
    preferences_list,
    MachineInfoView,
    MachineStateView,
    delete_preference,
    delete_preferences,
    tasks,
    task_details,
    AgentStatusView,
    AgentControlView,
    CoordinatorStatusView,
    RuntimeStatusView,
    RuntimeResourcesView,
    RuntimeControlView,
    RuntimeDiskView,
    RuntimeHistoryView,
    RuntimeResultView,
    RuntimeSubmitView,
    )

urlpatterns = [
    path("", home, name="home"),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),

    # API Agent de collecte
    path('api/agent/status/', AgentStatusView.as_view(), name='agent-status'),
    path('api/agent/<str:action>/', AgentControlView.as_view(), name='agent-control'),

    # API État machine (temps réel)
    path('api/machine/state/', MachineStateView.as_view(), name='machine-state'),

    # Détails d'une tâche (AVANT la route action pour éviter le conflit)
    path('api/task/<str:task_id>/details/', task_details, name='task_details'),
    # Gestion des actions sur une tâche (pause/resume/stop/limit_cpu/limit_ram)
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

    # ------------------- API Coordinateur VC-UY1 -------------------
    path('api/coordinator/status/', CoordinatorStatusView.as_view(), name='coordinator-status'),

    # ------------------- API Runtime vc-uyr -------------------
    path('api/runtime/status/', RuntimeStatusView.as_view(), name='runtime-status'),
    path('api/runtime/resources/', RuntimeResourcesView.as_view(), name='runtime-resources'),
    path('api/runtime/control/<str:action>/', RuntimeControlView.as_view(), name='runtime-control'),
    path('api/runtime/disk/', RuntimeDiskView.as_view(), name='runtime-disk'),
    path('api/runtime/history/', RuntimeHistoryView.as_view(), name='runtime-history'),
    path('api/runtime/result/', RuntimeResultView.as_view(), name='runtime-result'),
    path('api/runtime/submit/', RuntimeSubmitView.as_view(), name='runtime-submit'),

]
