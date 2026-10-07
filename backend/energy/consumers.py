import json
from channels.generic.websocket import AsyncWebsocketConsumer


class MeterTelemetryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("telemetry", self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection.ready",
            "transport": "Django Channels WebSocket",
            "ingestion": "HTTPS POST signé toutes les 5 secondes",
            "mqtt": False,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("telemetry", self.channel_name)

    async def telemetry_refresh(self, event):
        await self.send(text_data=json.dumps({
            "type": "telemetry.refresh",
            "message_id": event.get("message_id"),
            "meter_id": event.get("meter_id"),
        }))

    async def receive(self, text_data=None, bytes_data=None):
        await self.send(text_data=json.dumps({
            "type": "telemetry.refresh",
            "message": "Le client doit lire le dernier état accepté par l’API HTTPS.",
        }))
