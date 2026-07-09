"""
ASGI config for backend project.
"""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from socket_service import routing as socket_routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        # Pas d'auth session requise pour le dashboard local volontaire
        "websocket": URLRouter(socket_routing.websocket_urlpatterns),
    }
)
