import asyncio
import websockets

async def handler(ws):
    async for msg in ws:
        print("Received:", msg)
        await ws.send(f"UNO Q got: {msg}")

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()

asyncio.run(main())
