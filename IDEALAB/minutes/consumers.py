import json
from channels.generic.websocket import AsyncWebsocketConsumer

class MinutesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.meeting_id = self.scope["url_route"]["kwargs"]["meeting_id"]
        self.group = f"meeting_{self.meeting_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def minutes_update(self, event):
        await self.send(text_data=json.dumps(event["payload"], ensure_ascii=False))
