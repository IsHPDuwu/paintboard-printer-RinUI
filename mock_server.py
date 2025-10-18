import asyncio
import websockets

async def handler(websocket):
    await websocket.send("Connected")
    await asyncio.sleep(10)

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
