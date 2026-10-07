from django.urls import re_path
from .consumers import MeterTelemetryConsumer

websocket_urlpatterns = [
    re_path(r"ws/telemetry/$", MeterTelemetryConsumer.as_asgi()),
]
