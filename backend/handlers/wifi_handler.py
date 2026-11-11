from __future__ import annotations

import json
import logging

from backend.handlers.access import authorize_device
from backend.handlers.device_command import request_device, send_ack, send_error
from backend.security.auth import record_audit

logger = logging.getLogger("DispWatter.WiFi")


def _valid_ssid(value: str) -> bool:
    return 1 <= len(value.encode("utf-8")) <= 31


def _valid_password(value: str) -> bool:
    return value == "" or 8 <= len(value) <= 63


async def handle_wifi_list(user: dict, panel_ws, device_id: str, request_id: str | None):
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(panel_ws, request_id, error)
        return

    result = await request_device(panel_ws, user, device_id, {"command": "wifi_list", "request_id": request_id})
    if result.get("event") == "wifi_list" and isinstance(result.get("networks"), list):
        await panel_ws.send(
            json.dumps(
                {
                    "event": "wifi_list_result",
                    "request_id": result.get("request_id", request_id),
                    "device_id": device_id,
                    "networks": result["networks"],
                }
            )
        )
        return

    if not result.get("ok", False):
        await send_error(panel_ws, request_id, result.get("error", "hardware_error"))
        return

    await panel_ws.send(
        json.dumps(
            {
                "event": "wifi_list_result",
                "request_id": result.get("request_id", request_id),
                "device_id": device_id,
                "networks": [],
            }
        )
    )


async def handle_wifi_add(
    user: dict, panel_ws, device_id: str, request_id: str | None, ssid: str, password: str
):
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(panel_ws, request_id, error)
        return

    ssid = (ssid or "").strip()
    password = password or ""
    if not _valid_ssid(ssid):
        await send_error(panel_ws, request_id, "invalid_params", "SSID inválido")
        return
    if not _valid_password(password):
        await send_error(panel_ws, request_id, "invalid_params", "Contraseña WiFi inválida")
        return

    result = await request_device(
        panel_ws,
        user,
        device_id,
        {"command": "wifi_add", "ssid": ssid, "password": password, "request_id": request_id},
    )
    ok = bool(result.get("ok", False))
    if ok:
        await record_audit("WIFI_ADDED", device_id=device_id, actor=user.get("username", "USER"), details=f"SSID={ssid}")
    await send_ack(panel_ws, result.get("request_id", request_id), ok, result.get("error", ""))


async def handle_wifi_remove(user: dict, panel_ws, device_id: str, request_id: str | None, ssid: str):
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(panel_ws, request_id, error)
        return

    ssid = (ssid or "").strip()
    if not _valid_ssid(ssid):
        await send_error(panel_ws, request_id, "invalid_params", "SSID inválido")
        return

    result = await request_device(
        panel_ws, user, device_id, {"command": "wifi_remove", "ssid": ssid, "request_id": request_id}
    )
    ok = bool(result.get("ok", False))
    if ok:
        await record_audit("WIFI_REMOVED", device_id=device_id, actor=user.get("username", "USER"), details=f"SSID={ssid}")
    await send_ack(panel_ws, result.get("request_id", request_id), ok, result.get("error", ""))


async def handle_wifi_reorder(
    user: dict, panel_ws, device_id: str, request_id: str | None, ssid: str, index: int
):
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(panel_ws, request_id, error)
        return

    ssid = (ssid or "").strip()
    if not _valid_ssid(ssid):
        await send_error(panel_ws, request_id, "invalid_params", "SSID inválido")
        return
    try:
        index = int(index)
    except (TypeError, ValueError):
        await send_error(panel_ws, request_id, "invalid_params", "Índice inválido")
        return
    if index < 0:
        await send_error(panel_ws, request_id, "invalid_params", "Índice inválido")
        return

    result = await request_device(
        panel_ws,
        user,
        device_id,
        {"command": "wifi_reorder", "ssid": ssid, "index": index, "request_id": request_id},
    )
    ok = bool(result.get("ok", False))
    if ok:
        await record_audit(
            "WIFI_REORDERED",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"SSID={ssid} index={index}",
        )
    await send_ack(panel_ws, result.get("request_id", request_id), ok, result.get("error", ""))
