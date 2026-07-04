"""WebSocket consumer pour le tableau de bord volontaire."""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class VolunteerTaskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "task_updates"
        if self.channel_layer is None:
            await self.close()
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_established",
                    "message": "WebSocket volontaire connecté",
                }
            )
        )
        logger.info("WebSocket volontaire connecté: %s", self.channel_name)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info("WebSocket volontaire déconnecté (%s)", close_code)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def _forward(self, event, event_type: str):
        payload = event.get("data") or {}
        await self.send(
            text_data=json.dumps(
                {
                    "type": event_type,
                    "data": payload,
                }
            )
        )

    async def send_task_update(self, event):
        await self._forward(event, "send_task_update")

    async def send_task_progress(self, event):
        await self._forward(event, "send_task_progress")

    async def send_task_status_change(self, event):
        await self._forward(event, "send_task_status_change")

    async def send_task_deleted(self, event):
        await self._forward(event, "send_task_deleted")

    async def send_add_task(self, event):
        await self._forward(event, "send_add_task")
