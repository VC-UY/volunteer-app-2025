from django.contrib import admin
from django.urls import path , include
from .views import MachineInfoView

from communication.views import publier_message
<<<<<<< HEAD
from .views import home
=======
>>>>>>> 786acc5b158bf5aef3b8865c29bf1cf491ec0800

urlpatterns = [
    path('admin/', admin.site.urls),
    path("pubsub/", publier_message),
<<<<<<< HEAD
    path("machines/", MachineInfoView.as_view(), name="machine-info"),
    path('', home, name='home'),  # Page d'accueil
=======
    path("machines/", MachineInfoView.as_view(), name="machine-info")
>>>>>>> 786acc5b158bf5aef3b8865c29bf1cf491ec0800
]
