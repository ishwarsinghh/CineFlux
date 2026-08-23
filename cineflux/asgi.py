"""
ASGI config for CineFlux.

Supports two protocols:
  - http   -> Django views (REST API + SPA)
  - websocket -> Django Channels consumers (real-time seat updates)

Run with Daphne (ASGI) instead of the built-in runserver for WebSocket support:
    daphne cineflux.asgi:application
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cineflux.settings')

# Initialize Django BEFORE importing channel routing (Django apps must be ready)
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import api.routing

application = ProtocolTypeRouter({
    # Standard HTTP requests -> Django views
    "http": django_asgi_app,

    # WebSocket connections -> Channels consumers
    # AuthMiddlewareStack populates scope["user"] from Django sessions
    # (for JWT auth over WS, a custom middleware would be needed)
    "websocket": AuthMiddlewareStack(
        URLRouter(api.routing.websocket_urlpatterns)
    ),
})
