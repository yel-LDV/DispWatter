from __future__ import annotations

from typing import Optional

from backend.services import db_service


async def authorize_device(
    user: dict, device_id: str, require_claimed: bool = True
) -> tuple[Optional[dict], Optional[str]]:
    """Devuelve (device_info, error_code). Aplica propiedad y rol."""
    if not device_id:
        return None, "invalid_params"

    device = await db_service.get_device(device_id)

    if device is None:
        return None, "not_found"
    if device.status == "BLOCKED":
        return None, "forbidden"
    if require_claimed and device.status != "CLAIMED":
        return None, "device_not_claimed"
    if user.get("role") != "admin" and device.owner_id != user.get("id"):
        return None, "forbidden"

    return {
        "id": device.id,
        "name": device.name,
        "status": device.status,
        "owner_id": device.owner_id,
    }, None
