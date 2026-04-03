import asyncio
import websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8000/ws/stream") as ws:
        print("Baglandi, bekleniyor...")
        while True:
            msg = await ws.recv()
            print("Mesaj:", msg)

asyncio.run(test())