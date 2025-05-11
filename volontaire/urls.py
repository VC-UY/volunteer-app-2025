from django.contrib import admin
from django.urls import path , include
from .views import MachineInfoView

from communication.views import publier_message
from .views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path("pubsub/", publier_message),
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path('', home, name='home'),  # Page d'accueil
]
