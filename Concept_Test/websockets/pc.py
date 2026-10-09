import asyncio
import websockets

async def main():
    async with websockets.connect("ws://UNO_Q_IP:8765") as ws:
        await ws.send("Hello from laptop")
        print(await ws.recv())

asyncio.run(main())
