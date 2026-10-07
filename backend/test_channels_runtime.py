import asyncio
import json
import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8765/ws/telemetry/") as socket:
        message = json.loads(await socket.recv())
        assert message["mqtt"] is False
        assert "HTTPS POST" in message["ingestion"]
        print("CHANNELS_RUNTIME_OK")


asyncio.run(main())
