from __future__ import annotations

import logging

from backend.handlers.access import authorize_device
from backend.handlers.device_command import request_device, send_ack, send_error
from backend.security.auth import record_audit

logger = logging.getLogger("DispWatter.Actions")

ALLOWED_ACTIONS = {"reboot", "sleep", "factory_reset"}


async def handle_device_action(
    user: dict,
    panel_ws,
    device_id: str,
    request_id: str | None,
    action: str,
    args: dict | None = None,
) -> None:
    args = args or {}
    if action not in ALLOWED_ACTIONS:
        await send_error(panel_ws, request_id, "invalid_params", "Acción desconocida")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(panel_ws, request_id, error)
        return

    if action == "factory_reset" and user.get("role") != "admin":
        await send_error(panel_ws, request_id, "forbidden", "Solo un administrador puede resetear")
        return

    command: dict = {"command": action}
    if action == "sleep":
        try:
            minutes = int(args.get("minutes", 60))
        except (TypeError, ValueError):
            await send_error(panel_ws, request_id, "invalid_params", "Minutos inválidos")
            return
        if not 1 <= minutes <= 1440:
            await send_error(panel_ws, request_id, "invalid_params", "Minutos fuera de rango")
            return
        command["minutes"] = minutes

    result = await request_device(panel_ws, user, device_id, {**command, "request_id": request_id})
    ok = bool(result.get("ok", False))
    if ok:
        details = f"action={action}"
        if action == "sleep":
            details += f" minutes={command['minutes']}"
        await record_audit(
            f"DEVICE_{action.upper()}",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=details,
        )
    await send_ack(panel_ws, result.get("request_id", request_id), ok, result.get("error", ""))
