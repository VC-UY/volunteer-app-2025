# from channels.generic.websocket import AsyncWebsocketConsumer
# import json

# class TaskConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.volunteer_id = self.scope['url_route']['kwargs']['volunteer_id']
#         self.room_group_name = f"tasks_{self.volunteer_id}"
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         await self.accept()

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#     async def send_task(self, event):
#         await self.send(text_data=json.dumps(event["task"]))


import json
from channels.generic.websocket import AsyncWebsocketConsumer

class TaskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "task_updates"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=json.dumps({"message": "WebSocket connecté"}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Pour l'instant, on ne traite pas les messages entrants
        pass

    async def send_task_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))
