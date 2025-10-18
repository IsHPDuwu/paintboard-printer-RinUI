import sys
import requests
import asyncio
import websockets
import struct
import os
import base64
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Slot, Signal, QThread, QByteArray
from PySide6.QtQml import QQmlApplicationEngine

import RinUI
from RinUI.core.theme import ThemeManager

class ApiHandler(QObject):
    token_received = Signal(str)

    def __init__(self):
        super().__init__()

    @Slot(str, str, result=str)
    def get_token(self, uid, access_key):
        try:
            response = requests.post(
                "https://paintboard.luogu.me/api/auth/gettoken",
                json={"uid": int(uid), "access_key": access_key}
            )
            response.raise_for_status()
            data = response.json()
            if data.get("data", {}).get("token"):
                token = data["data"]["token"]
                self.token_received.emit(token)
                return token
            else:
                return f"Error: {data.get('data', {}).get('errorType', 'Unknown error')}"
        except requests.exceptions.RequestException as e:
            return f"Error: {e}"
        except (ValueError, KeyError) as e:
            return f"Error parsing response: {e}"

class BoardFetcher(QObject):
    board_received = Signal(str) # Now emits a base64 string
    error = Signal(str)

    @Slot()
    def fetch_board(self):
        try:
            print("Fetching board data...")
            response = requests.get("https://paintboard.luogu.me/api/paintboard/getboard")
            response.raise_for_status()
            content = response.content
            print(f"Board data received. Size: {len(content)} bytes.")

            if len(content) != 1000 * 600 * 3:
                self.error.emit(f"Error: Invalid board data size.")
                return

            # Create a raw PPM image header
            header = f"P6\n1000 600\n255\n".encode('ascii')
            ppm_data = header + content

            # Encode as base64
            base64_data = base64.b64encode(ppm_data).decode('ascii')
            print("Board data converted to base64 PPM image.")
            self.board_received.emit(f"data:image/ppm;base64,{base64_data}")

        except requests.exceptions.RequestException as e:
            self.error.emit(f"Error getting board: {e}")

class WebSocketWorker(QObject):
    message_received = Signal(str)
    paint_event = Signal(int, int, int, int, int)
    paint_result = Signal(int, int)

    start_connecting = Signal()
    request_board_update = Signal()

    def __init__(self):
        super().__init__()
        self.uri = "wss://paintboard.luogu.me/api/paintboard/ws"
        self.websocket = None
        self.loop = asyncio.new_event_loop()
        self.send_queue = []
        self.start_connecting.connect(self.run)

    @Slot()
    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self.connect())
        self.loop.run_forever()
        tasks = asyncio.all_tasks(loop=self.loop)
        for task in tasks:
            task.cancel()
        group = asyncio.gather(*tasks, return_exceptions=True)
        self.loop.run_until_complete(group)
        self.loop.close()

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.uri)
            self.message_received.emit("WebSocket connected.")
            asyncio.create_task(self.send_loop())
            async for message in self.websocket:
                self.handle_message(message)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass
        except Exception as e:
            self.message_received.emit(f"WebSocket error: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()

    def handle_message(self, message):
        offset = 0
        while offset < len(message):
            msg_type = message[offset]
            offset += 1
            if msg_type == 0xfa:
                x, y, r, g, b = struct.unpack("<HHBBB", message[offset:offset+7])
                offset += 7
                self.paint_event.emit(x, y, r, g, b)
                self.request_board_update.emit() # Request a full refresh
            elif msg_type == 0xfc:
                self.send_queue.append(b'\xfb')
            elif msg_type == 0xff:
                paint_id, status = struct.unpack("<IB", message[offset:offset+5])
                offset += 5
                self.paint_result.emit(paint_id, status)

    async def send_loop(self):
        try:
            while True:
                if self.send_queue:
                    await self.websocket.send(b"".join(self.send_queue))
                    self.send_queue.clear()
                await asyncio.sleep(0.02)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass

    @Slot(bytes)
    def add_to_send_queue(self, data):
        self.send_queue.append(data)

    @Slot()
    def stop(self):
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

class WebSocketClient(QObject):
    paint_event = Signal(int, int, int, int, int)
    paint_result = Signal(int, int)
    message_received = Signal(str)

    stop_worker = Signal()
    request_board_update = Signal()

    def __init__(self):
        super().__init__()
        self.worker = WebSocketWorker()
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.worker.paint_event.connect(self.paint_event)
        self.worker.paint_result.connect(self.paint_result)
        self.worker.message_received.connect(self.message_received)
        self.worker.request_board_update.connect(self.request_board_update)
        self.stop_worker.connect(self.worker.stop)

        self.paint_id_counter = 0

    @Slot(int, str, int, int, int, int, int)
    def paint(self, uid, token, r, g, b, x, y):
        paint_id = self.paint_id_counter
        self.paint_id_counter = (self.paint_id_counter + 1) % 4294967296
        uid_bytes = uid.to_bytes(3, 'little')
        token_bytes = bytes.fromhex(token.replace("-", ""))
        paint_data = struct.pack("<BHHBBB", 0xfe, x, y, r, g, b) + uid_bytes + token_bytes + paint_id.to_bytes(4, 'little')
        self.worker.add_to_send_queue(paint_data)

    @Slot()
    def start(self):
        if not self.thread.isRunning():
            self.thread.start()
            self.worker.start_connecting.emit()

    def shutdown(self):
        if self.thread.isRunning():
            self.stop_worker.emit()
            self.thread.quit()
            self.thread.wait()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    engine = QQmlApplicationEngine()

    rinui_path = os.path.dirname(RinUI.__file__)
    engine.addImportPath(os.path.abspath(os.path.join(rinui_path, os.pardir)))

    api_handler = ApiHandler()
    ws_client = WebSocketClient()
    theme_manager = ThemeManager()
    board_fetcher = BoardFetcher()
    fetcher_thread = QThread()
    board_fetcher.moveToThread(fetcher_thread)

    api_handler.token_received.connect(ws_client.start)
    ws_client.request_board_update.connect(board_fetcher.fetch_board)
    fetcher_thread.started.connect(board_fetcher.fetch_board)

    engine.rootContext().setContextProperty("apiHandler", api_handler)
    engine.rootContext().setContextProperty("wsClient", ws_client)
    engine.rootContext().setContextProperty("ThemeManager", theme_manager)
    engine.rootContext().setContextProperty("boardFetcher", board_fetcher)

    @Slot()
    def shutdown_threads():
        print("Shutting down threads...")
        ws_client.shutdown()
        if fetcher_thread.isRunning():
            fetcher_thread.quit()
            fetcher_thread.wait()
        print("Threads shut down.")

    app.aboutToQuit.connect(shutdown_threads)

    engine.load("main.qml")

    if not engine.rootObjects():
        sys.exit(-1)

    fetcher_thread.start()

    sys.exit(app.exec())
