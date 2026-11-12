from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from backend.services import db_service
from backend.security.auth import verify_password

logger = logging.getLogger("DispWatter.PanelWorker")


def _run_async(coro) -> Any:
    """Ejecuta una coroutine en un nuevo event loop dentro del thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def handle(action: str, params: Dict[str, Any]) -> Any:
    """Punto de entrada del panel worker. Despacha acciones a funciones async."""
    handlers = {
        "login": _login,
        "resume": _resume,
        "get_all_devices": _get_all_devices,
        "update_tank_config": _update_tank_config,
        "get_audit_logs": _get_audit_logs,
        "delete_device": _delete_device,
        "release_device": _release_device,
        "get_device": _get_device,
        "update_device_name": _update_device_name,
        "get_tank_config": _get_tank_config,
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValueError(f"Acción de panel desconocida: {action}")
    return _run_async(handler(params))


async def _login(params: Dict[str, Any]) -> Dict[str, Any]:
    username = params["username"]
    password = params["password"]

    user = await db_service.get_user_by_username(username)
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        return {"ok": False, "error": "unauthorized"}

    await db_service.update_user_last_login(user.id)
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }


async def _resume(params: Dict[str, Any]) -> Dict[str, Any]:
    user_id = params["user_id"]
    user = await db_service.get_user_by_id(user_id)
    if user is None or not user.is_active:
        return {"ok": False, "error": "unauthorized"}
    
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }


async def _get_all_devices(params: Dict[str, Any]) -> Dict[str, Any]:
    devices = await db_service.get_all_devices_for_sync()
    return {"devices": devices}


async def _update_tank_config(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    await db_service.update_tank_config(
        device_id,
        capacity_liters=params.get("capacity_liters"),
        bottom_dist_mm=params.get("bottom_dist_mm"),
        mirror_dist_mm=params.get("mirror_dist_mm"),
        min_level_percent=params.get("min_level_percent"),
        max_level_percent=params.get("max_level_percent"),
        auto_refill=params.get("auto_refill"),
    )
    return {"ok": True}


async def _get_audit_logs(params: Dict[str, Any]) -> Dict[str, Any]:
    logs = await db_service.get_audit_logs(
        action_filter=params.get("action_filter", ""),
        device_filter=params.get("device_filter", ""),
        limit=params.get("limit", 250),
    )
    return {"entries": logs}


async def _delete_device(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    await db_service.delete_device(device_id)
    return {"ok": True}


async def _release_device(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    await db_service.release_device(device_id)
    return {"ok": True}


async def _get_device(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    device = await db_service.get_device(device_id)
    if device is None:
        return {"device": None}
    return {
        "device": {
            "id": device.id,
            "name": device.name,
            "status": device.status,
            "owner_id": device.owner_id,
            "key_hash": device.key_hash,
        }
    }


async def _update_device_name(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    name = params["name"]
    await db_service.update_device_fields(device_id, name=name)
    return {"ok": True}


async def _get_tank_config(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    cfg = await db_service.get_tank_config(device_id)
    if cfg is None:
        return {"config": None}
    return {"config": cfg.to_dict()}
