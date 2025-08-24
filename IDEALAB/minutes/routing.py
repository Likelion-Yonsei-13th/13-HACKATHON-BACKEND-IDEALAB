from django.urls import re_path
from .consumers import MinutesConsumer

websocket_urlpatterns = [
    re_path(r"ws/meetings/(?P<meeting_id>\d+)/minutes/$", MinutesConsumer.as_asgi()),
]
