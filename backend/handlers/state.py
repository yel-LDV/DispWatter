from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any, Dict, Optional, Set

from backend.config import settings
from backend.security.auth import LoginRateLimiter


class ServerState:
    def __init__(self):
        # device_id -> websocket autenticado (o pendiente de claim)
        self.device_sockets: Dict[str, Any] = {}
        # device_id -> websocket que envió "hello" pero aún no se autenticó
        self.pending_device_sockets: Dict[str, Any] = {}
        # websocket -> device_id
        self.device_ids: Dict[Any, str] = {}
        # paneles autenticados
        self.panel_sockets: Set[Any] = set()
        # websocket -> datos del usuario autenticado
        self.panel_users: Dict[Any, dict] = {}
        # device_id -> última telemetría
        self.telemetry_cache: Dict[str, dict] = {}

        # websocket de dispositivo -> challenge pendiente
        # {"nonce": str, "expires": float, "purpose": "auth"|"claim"}
        self.challenges: Dict[Any, dict] = {}

        # device_id -> intento de claim
        # {"nonce", "expected_hash", "future", "panel_ws", "user", "expires"}
        self.claim_attempts: Dict[str, dict] = {}

        # request_id -> {"future": Future, "panel_ws": ws, "user": dict, "device_id": str}
        self.pending_requests: Dict[str, dict] = {}

        self.login_limiter = LoginRateLimiter(
            settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS
        )

    # ------------------------------------------------------------------
    # Dispositivos
    # ------------------------------------------------------------------
    def register_pending_device(self, device_id: str, websocket: Any) -> None:
        previous = self.pending_device_sockets.get(device_id)
        if previous is not None and previous is not websocket:
            self.challenges.pop(previous, None)
        self.pending_device_sockets[device_id] = websocket
        self.device_ids[websocket] = device_id

    def register_device(self, device_id: str, websocket: Any) -> None:
        previous = self.device_sockets.get(device_id)
        if previous is not None and previous is not websocket:
            self.device_ids.pop(previous, None)
        self.pending_device_sockets.pop(device_id, None)
        self.device_sockets[device_id] = websocket
        self.device_ids[websocket] = device_id

    def unregister_device(self, device_id: str) -> None:
        ws = self.device_sockets.pop(device_id, None)
        pending = self.pending_device_sockets.pop(device_id, None)
        for socket in {ws, pending}:
            if socket is not None:
                self.device_ids.pop(socket, None)
                self.challenges.pop(socket, None)

    def unregister_device_socket(self, websocket: Any) -> Optional[str]:
        device_id = self.device_ids.pop(websocket, None)
        if device_id:
            if self.device_sockets.get(device_id) is websocket:
                self.device_sockets.pop(device_id, None)
            if self.pending_device_sockets.get(device_id) is websocket:
                self.pending_device_sockets.pop(device_id, None)
        self.challenges.pop(websocket, None)
        return device_id

    def device_is_online(self, device_id: str) -> bool:
        return device_id in self.device_sockets

    def device_socket_for_challenge(self, device_id: str) -> Any:
        return self.device_sockets.get(device_id) or self.pending_device_sockets.get(device_id)

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        ws = self.device_sockets.get(device_id)
        if ws is None:
            return False
        try:
            await ws.send(json.dumps(message))
            return True
        except Exception:
            self.unregister_device(device_id)
            return False

    def new_challenge(self, websocket: Any, purpose: str = "auth") -> str:
        nonce = secrets.token_hex(32)
        self.challenges[websocket] = {
            "nonce": nonce,
            "expires": time.monotonic() + 30,
            "purpose": purpose,
        }
        return nonce

    def consume_challenge(self, websocket: Any, nonce: str) -> Optional[dict]:
        challenge = self.challenges.get(websocket)
        if not challenge:
            return None
        if challenge["nonce"] != nonce:
            return None
        if challenge["expires"] < time.monotonic():
            self.challenges.pop(websocket, None)
            return None
        self.challenges.pop(websocket, None)
        return challenge

    # ------------------------------------------------------------------
    # Paneles
    # ------------------------------------------------------------------
    def register_panel(self, websocket: Any, user: dict) -> None:
        self.panel_sockets.add(websocket)
        self.panel_users[websocket] = user

    def unregister_panel(self, websocket: Any) -> None:
        self.panel_sockets.discard(websocket)
        self.panel_users.pop(websocket, None)

    def panel_user(self, websocket: Any) -> Optional[dict]:
        return self.panel_users.get(websocket)

    async def broadcast_to_panels(self, message: dict) -> None:
        if not self.panel_sockets:
            return
        payload = json.dumps(message)
        dead_sockets = set()
        for ws in self.panel_sockets:
            try:
                await ws.send(payload)
            except Exception:
                dead_sockets.add(ws)
        for ws in dead_sockets:
            self.unregister_panel(ws)

    # ------------------------------------------------------------------
    # Peticiones panel -> dispositivo (esperando ack/resultado)
    # ------------------------------------------------------------------
    def create_request(
        self, request_id: str, panel_ws: Any, user: dict, device_id: str
    ) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_id] = {
            "future": future,
            "panel_ws": panel_ws,
            "user": user,
            "device_id": device_id,
        }
        return future

    def resolve_request(self, request_id: str, result: dict) -> bool:
        entry = self.pending_requests.pop(request_id, None)
        if not entry:
            return False
        future: asyncio.Future = entry["future"]
        if not future.done():
            future.set_result(result)
        return True

    def drop_request(self, request_id: str) -> None:
        entry = self.pending_requests.pop(request_id, None)
        if entry and not entry["future"].done():
            entry["future"].cancel()

    def drop_requests_for_panel(self, panel_ws: Any) -> None:
        for request_id, entry in list(self.pending_requests.items()):
            if entry["panel_ws"] is panel_ws:
                self.drop_request(request_id)


server_state = ServerState()
