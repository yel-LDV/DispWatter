from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from backend.config import settings
from backend.services import db_service

logger = logging.getLogger("DispWatter.DeviceWorker")


def _run_async(coro) -> Any:
    """Ejecuta una coroutine en un nuevo event loop dentro del thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def handle(action: str, params: Dict[str, Any]) -> Any:
    """Punto de entrada del device worker. Despacha acciones a funciones async."""
    handlers = {
        "save_telemetry": _save_telemetry,
        "update_device_online": _update_device_online,
        "update_device_status": _update_device_status,
        "cleanup_telemetry": _cleanup_telemetry,
        "update_device_networks": _update_device_networks,
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValueError(f"Acción de device desconocida: {action}")
    return _run_async(handler(params))


async def _save_telemetry(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    distance_mm = params["distance_mm"]
    water_percent = params["water_percent"]
    water_liters = params["water_liters"]
    relay_state = params["relay_state"]

    await db_service.save_telemetry(
        device_id=device_id,
        distance_mm=distance_mm,
        water_percent=water_percent,
        water_liters=water_liters,
        relay_state=relay_state,
    )

    # Actualizar last_seen del dispositivo
    await db_service.update_device_fields(
        device_id,
        is_online=True,
        last_seen=datetime.utcnow(),
    )

    return {"ok": True}


async def _update_device_online(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    is_online = params["is_online"]
    await db_service.update_device_online(device_id, is_online)
    return {"ok": True}


async def _update_device_status(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    await db_service.update_device_fields(
        device_id,
        is_online=params.get("is_online"),
        last_seen=datetime.utcnow() if params.get("last_seen") else None,
        last_ip=params.get("last_ip"),
        last_rssi=params.get("last_rssi"),
        wake_reason=params.get("wake_reason"),
        name=params.get("name"),
        location=params.get("location"),
        firmware_version=params.get("firmware_version"),
        key_hash=params.get("key_hash"),
        status=params.get("status"),
        owner_id=params.get("owner_id"),
    )
    return {"ok": True}


async def _cleanup_telemetry(params: Dict[str, Any]) -> Dict[str, Any]:
    retention_hours = params.get("retention_hours", settings.TELEMETRY_RETENTION_HOURS)
    await db_service.cleanup_old_telemetry(retention_hours)
    return {"ok": True}


async def _update_device_networks(params: Dict[str, Any]) -> Dict[str, Any]:
    device_id = params["device_id"]
    networks = params["networks"]
    await db_service.update_device_networks(device_id, networks)
    return {"ok": True}
