import json
from channels.generic.websocket import AsyncWebsocketConsumer

class VolunteerTaskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "task_updates"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        pass  # Pas de gestion de messages entrants pour l'instant

    async def send_task_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def send_task_progress(self, event):
        await self.send(text_data=json.dumps(event))

    async def send_task_status_change(self, event):
        await self.send(text_data=json.dumps(event))

    async def send_task_deleted(self, event):
        await self.send(text_data=json.dumps(event))
    
    async def send_add_task(self, event):
        await self.send(text_data=json.dumps(event))
        