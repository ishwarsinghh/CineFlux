from django.urls import re_path
from . import consumers

# WebSocket URL patterns — mounted in cineflux/asgi.py under the "websocket" protocol
websocket_urlpatterns = [
    # ws://localhost:8000/ws/showtimes/1/seats/
    re_path(
        r'ws/showtimes/(?P<showtime_id>\d+)/seats/$',
        consumers.SeatStatusConsumer.as_asgi()
    ),
]
