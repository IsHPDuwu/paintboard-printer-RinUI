import sys
import requests
import asyncio
import websockets
import struct
import os
import base64
import io
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Slot, Signal, QThread, QTimer
from PySide6.QtQml import QQmlApplicationEngine
from PIL import Image, ImageDraw
import numpy as np

import RinUI
from RinUI.core.theme import ThemeManager

HEATMAP_BLOCK_SIZE = 10
HEATMAP_WIDTH = 1000 // HEATMAP_BLOCK_SIZE
HEATMAP_HEIGHT = 600 // HEATMAP_BLOCK_SIZE

class TokenFetcher(QObject):
    token_received = Signal(str)
    error = Signal(str)

    @Slot(int, str)
    def get_token(self, uid, access_key):
        try:
            response = requests.post("https://paintboard.luogu.me/api/auth/gettoken", json={"uid": uid, "access_key": access_key})
            response.raise_for_status()
            data = response.json()
            if data.get("data", {}).get("token"):
                self.token_received.emit(data["data"]["token"])
            else:
                self.error.emit(f"Error: {data.get('data', {}).get('errorType', 'Unknown error')}")
        except requests.exceptions.RequestException as e: self.error.emit(f"Error: {e}")
        except (ValueError, KeyError) as e: self.error.emit(f"Error parsing response: {e}")

class ApiHandler(QObject):
    token_result = Signal(bool, str) # success, message
    start_fetch_token = Signal(int, str)

    # This signal will now be used to trigger the websocket start
    token_successfully_fetched = Signal()

    def __init__(self):
        super().__init__()

    @Slot(str, str)
    def get_token(self, uid, access_key):
        try:
            self.start_fetch_token.emit(int(uid), access_key)
        except ValueError:
            self.token_result.emit(False, "Error: UID must be a number.")

    @Slot(str)
    def on_token_received(self, token):
        self.token_result.emit(True, token)
        self.token_successfully_fetched.emit() # Emit the new signal

    @Slot(str)
    def on_token_error(self, error_message):
        self.token_result.emit(False, error_message)


class BoardFetcher(QObject):
    board_received = Signal(bytes)
    error = Signal(str)

    @Slot()
    def fetch_board(self):
        try:
            response = requests.get("https://paintboard.luogu.me/api/paintboard/getboard")
            response.raise_for_status()
            content = response.content
            if len(content) != 1000 * 600 * 3:
                self.error.emit(f"Error: Invalid board data size.")
                return
            self.board_received.emit(content)
        except requests.exceptions.RequestException as e: self.error.emit(f"Error getting board: {e}")

class WebSocketWorker(QObject):
    message_received = Signal(str)
    paint_event = Signal(int, int, int, int, int)
    paint_result = Signal(int, int)
    start_connecting = Signal()

    def __init__(self):
        super().__init__()
        self.uri = "wss://paintboard.luogu.me/api/paintboard/ws"
        self.websocket = None; self.loop = asyncio.new_event_loop(); self.send_queue = []
        self.start_connecting.connect(self.run)

    @Slot()
    def run(self):
        asyncio.set_event_loop(self.loop); self.loop.create_task(self.connect()); self.loop.run_forever()
        tasks = asyncio.all_tasks(loop=self.loop); [task.cancel() for task in tasks]
        group = asyncio.gather(*tasks, return_exceptions=True); self.loop.run_until_complete(group)
        self.loop.close()

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.uri)
            self.message_received.emit("WebSocket connected.")
            asyncio.create_task(self.send_loop())
            async for message in self.websocket: self.handle_message(message)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed): pass
        except Exception as e: self.message_received.emit(f"WebSocket error: {e}")
        finally:
            if self.websocket: await self.websocket.close()

    def handle_message(self, message):
        offset = 0
        while offset < len(message):
            msg_type = message[offset]; offset += 1
            if msg_type == 0xfa:
                x, y, r, g, b = struct.unpack("<HHBBB", message[offset:offset+7]); offset += 7
                self.paint_event.emit(x, y, r, g, b)
            elif msg_type == 0xfc: self.send_queue.append(b'\xfb')
            elif msg_type == 0xff:
                paint_id, status = struct.unpack("<IB", message[offset:offset+5]); offset += 5
                self.paint_result.emit(paint_id, status)

    async def send_loop(self):
        try:
            while True:
                if self.send_queue:
                    await self.websocket.send(b"".join(self.send_queue)); self.send_queue.clear()
                await asyncio.sleep(0.02)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed): pass

    @Slot(bytes)
    def add_to_send_queue(self, data): self.send_queue.append(data)
    @Slot()
    def stop(self):
        if self.loop.is_running(): self.loop.call_soon_threadsafe(self.loop.stop)

class WebSocketClient(QObject):
    paint_result = Signal(int, int)
    message_received = Signal(str)
    board_updated = Signal(str)
    heatmap_updated = Signal(str)
    stop_worker = Signal()
    request_board_update = Signal()

    def __init__(self):
        super().__init__()
        self.worker = WebSocketWorker(); self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.worker.paint_event.connect(self.on_paint_event)
        self.worker.paint_result.connect(self.paint_result)
        self.worker.message_received.connect(self.message_received)
        self.stop_worker.connect(self.worker.stop)
        self.paint_id_counter = 0; self.board_data = None
        self.heatmap = np.zeros((HEATMAP_HEIGHT, HEATMAP_WIDTH))
        self.heatmap_timer = QTimer(self)
        self.heatmap_timer.timeout.connect(self.decay_heatmap)
        self.heatmap_timer.start(1000)

    @Slot(int, str, int, int, int, int, int)
    def paint(self, uid, token, r, g, b, x, y):
        paint_id = self.paint_id_counter; self.paint_id_counter = (self.paint_id_counter + 1) % 4294967296
        uid_bytes = uid.to_bytes(3, 'little'); token_bytes = bytes.fromhex(token.replace("-", ""))
        paint_data = struct.pack("<BHHBBB", 0xfe, x, y, r, g, b) + uid_bytes + token_bytes + paint_id.to_bytes(4, 'little')
        self.worker.add_to_send_queue(paint_data); self.on_paint_event(x, y, r, g, b)

    @Slot(bytes)
    def on_board_received(self, raw_bytes):
        self.board_data = bytearray(raw_bytes); self.emit_board_update()

    @Slot(int, int, int, int, int)
    def on_paint_event(self, x, y, r, g, b):
        if self.board_data and 0 <= x < 1000 and 0 <= y < 600:
            index = (y * 1000 + x) * 3
            self.board_data[index] = r; self.board_data[index+1] = g; self.board_data[index+2] = b
            self.emit_board_update()
            hx, hy = x // HEATMAP_BLOCK_SIZE, y // HEATMAP_BLOCK_SIZE
            if 0 <= hx < HEATMAP_WIDTH and 0 <= hy < HEATMAP_HEIGHT: self.heatmap[hy, hx] += 1

    @Slot()
    def decay_heatmap(self):
        self.heatmap *= 0.95; self.render_heatmap()

    def render_heatmap(self):
        if np.max(self.heatmap) < 0.1:
            self.heatmap_updated.emit(""); return
        norm_heatmap = self.heatmap / (np.max(self.heatmap) + 1e-6)
        img = Image.new("RGBA", (1000, 600), (0,0,0,0)); draw = ImageDraw.Draw(img)
        for y in range(HEATMAP_HEIGHT):
            for x in range(HEATMAP_WIDTH):
                heat = norm_heatmap[y, x]
                if heat > 0.1:
                    r, g, b, a = int(255 * min(1, heat * 2)), int(255 * max(0, heat * 2 - 1)), 0, int(150 * heat)
                    x0, y0, x1, y1 = x * HEATMAP_BLOCK_SIZE, y * HEATMAP_BLOCK_SIZE, (x + 1) * HEATMAP_BLOCK_SIZE, (y + 1) * HEATMAP_BLOCK_SIZE
                    draw.rectangle([x0, y0, x1, y1], fill=(r,g,b,a))
        buffer = io.BytesIO(); img.save(buffer, format="PNG")
        base64_data = base64.b64encode(buffer.getvalue()).decode('ascii')
        self.heatmap_updated.emit(f"data:image/png;base64,{base64_data}")

    def emit_board_update(self):
        if self.board_data:
            header = f"P6\n1000 600\n255\n".encode('ascii')
            ppm_data = header + self.board_data
            base64_data = base64.b64encode(ppm_data).decode('ascii')
            self.board_updated.emit(f"data:image/ppm;base64,{base64_data}")

    @Slot()
    def start(self):
        if not self.thread.isRunning(): self.thread.start(); self.worker.start_connecting.emit()
    def shutdown(self):
        if self.thread.isRunning(): self.stop_worker.emit(); self.thread.quit(); self.thread.wait()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    rinui_path = os.path.dirname(RinUI.__file__)
    engine.addImportPath(os.path.abspath(os.path.join(rinui_path, os.pardir)))

    api_handler = ApiHandler(); ws_client = WebSocketClient(); theme_manager = ThemeManager()
    board_fetcher = BoardFetcher(); fetcher_thread = QThread()
    board_fetcher.moveToThread(fetcher_thread)

    token_fetcher = TokenFetcher(); token_fetcher_thread = QThread()
    token_fetcher.moveToThread(token_fetcher_thread)

    api_handler.start_fetch_token.connect(token_fetcher.get_token)
    token_fetcher.token_received.connect(api_handler.on_token_received)
    token_fetcher.error.connect(api_handler.on_token_error)

    # This is the critical line that was missing.
    api_handler.token_successfully_fetched.connect(ws_client.start)

    board_fetcher.board_received.connect(ws_client.on_board_received)
    board_fetcher.error.connect(lambda msg: print(f"Board fetch error: {msg}"))
    ws_client.request_board_update.connect(board_fetcher.fetch_board)
    fetcher_thread.started.connect(board_fetcher.fetch_board)

    engine.rootContext().setContextProperty("apiHandler", api_handler)
    engine.rootContext().setContextProperty("wsClient", ws_client)
    engine.rootContext().setContextProperty("ThemeManager", theme_manager)

    @Slot()
    def shutdown_threads():
        print("Shutting down threads..."); ws_client.shutdown()
        if fetcher_thread.isRunning(): fetcher_thread.quit(); fetcher_thread.wait()
        if token_fetcher_thread.isRunning(): token_fetcher_thread.quit(); token_fetcher_thread.wait()
        print("Threads shut down.")

    app.aboutToQuit.connect(shutdown_threads)
    engine.load("main.qml")
    if not engine.rootObjects(): sys.exit(-1)

    fetcher_thread.start()
    token_fetcher_thread.start()

    sys.exit(app.exec())
