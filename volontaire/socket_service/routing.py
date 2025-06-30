from django.urls import re_path
from .consumers import VolunteerTaskConsumer

websocket_urlpatterns = [
    re_path(r'ws/tasks/$', VolunteerTaskConsumer.as_asgi()),
]
