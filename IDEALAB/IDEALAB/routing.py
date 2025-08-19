from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import minutes.routing   # ← minutes ws만 노출 (stt용 ws 필요시 추가)

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter(minutes.routing.websocket_urlpatterns)
    ),
})
