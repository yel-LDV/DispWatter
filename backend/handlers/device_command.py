from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from backend.handlers.state import server_state


def new_request_id() -> str:
    return uuid.uuid4().hex


async def send_to_panel(panel_ws: Any, payload: dict) -> None:
    try:
        await panel_ws.send(json.dumps(payload))
    except Exception:
        pass


async def request_device(
    panel_ws: Any,
    user: dict,
    device_id: str,
    payload: dict,
    timeout: float = 10.0,
) -> dict:
    """Envía un comando al ESP32 y espera su ack/wifi_list."""
    request_id = str(payload.get("request_id") or new_request_id())
    payload = {**payload, "request_id": request_id}

    future = server_state.create_request(request_id, panel_ws, user, device_id)
    sent = await server_state.send_to_device(device_id, payload)
    if not sent:
        server_state.drop_request(request_id)
        return {"ok": False, "error": "device_offline", "request_id": request_id}

    try:
        result = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        server_state.drop_request(request_id)
        return {"ok": False, "error": "timeout", "request_id": request_id}
    except asyncio.CancelledError:
        server_state.drop_request(request_id)
        raise

    result.setdefault("request_id", request_id)
    return result


async def send_error(panel_ws: Any, request_id: str | None, code: str, message: str = "") -> None:
    await send_to_panel(
        panel_ws,
        {
            "event": "error",
            "request_id": request_id,
            "code": code,
            "message": message or code,
        },
    )


async def send_ack(panel_ws: Any, request_id: str | None, ok: bool, error: str = "") -> None:
    payload = {"event": "ack", "request_id": request_id, "ok": ok}
    if not ok and error:
        payload["error"] = error
    await send_to_panel(panel_ws, payload)
