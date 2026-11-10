from typing import Dict, Set, Any
import json

class ServerState:
    def __init__(self):
        # device_id -> websocket
        self.device_sockets: Dict[str, Any] = {}
        # panel websockets
        self.panel_sockets: Set[Any] = set()
        # device_id -> latest telemetry cache
        self.telemetry_cache: Dict[str, dict] = {}

    def register_device(self, device_id: str, websocket: Any):
        self.device_sockets[device_id] = websocket

    def unregister_device(self, device_id: str):
        if device_id in self.device_sockets:
            del self.device_sockets[device_id]

    def register_panel(self, websocket: Any):
        self.panel_sockets.add(websocket)

    def unregister_panel(self, websocket: Any):
        self.panel_sockets.discard(websocket)

    async def broadcast_to_panels(self, message: dict):
        if not self.panel_sockets:
            return
        payload = json.dumps(message)
        dead_sockets = set()
        for ws in self.panel_sockets:
            try:
                await ws.send(payload)
            except Exception:
                dead_sockets.add(ws)
        self.panel_sockets.difference_update(dead_sockets)

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        ws = self.device_sockets.get(device_id)
        if ws:
            try:
                await ws.send(json.dumps(message))
                return True
            except Exception:
                self.unregister_device(device_id)
        return False

server_state = ServerState()
