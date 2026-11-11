from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Optional

from backend.config import settings
from backend.handlers.device_command import send_error, send_to_panel
from backend.handlers.state import server_state
from backend.security.auth import record_audit

logger = logging.getLogger("DispWatter.System")

VALID_TARGETS = {"backend", "panel", "all"}
VALID_ACTIONS = {"start", "stop", "restart", "status"}


async def _run_ctl(*args: str, timeout: float = 25.0) -> tuple[int, str]:
    ctl = settings.DISPWATTER_CTL
    if not os.path.isfile(ctl):
        return 127, f"No se encuentra {ctl}. Instala deploy/dispwatter-ctl y deploy/sudoers.d/dispwatter."

    cmd: list[str] = []
    if os.geteuid() != 0 and shutil.which("sudo"):
        cmd += ["sudo", "-n"]
    cmd += [ctl, *args]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, output.decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return 124, "Tiempo de espera agotado ejecutando dispwatter-ctl"
    except Exception as exc:
        return 1, f"Error ejecutando dispwatter-ctl: {exc}"


async def _sleep_all_devices(minutes: int = 60) -> int:
    count = 0
    for device_id in list(server_state.device_sockets.keys()):
        if await server_state.send_to_device(
            device_id, {"command": "sleep", "minutes": minutes, "request_id": f"all-sleep-{device_id}"}
        ):
            count += 1
    return count


async def _reboot_all_devices() -> int:
    count = 0
    for device_id in list(server_state.device_sockets.keys()):
        if await server_state.send_to_device(
            device_id, {"command": "reboot", "request_id": f"all-reboot-{device_id}"}
        ):
            count += 1
    return count


async def _send_result(panel_ws, request_id: Optional[str], ok: bool, output: str = "", error: str = "") -> None:
    payload = {
        "event": "system_result",
        "request_id": request_id,
        "ok": ok,
        "output": output,
    }
    if not ok:
        payload["error"] = error or output
    await send_to_panel(panel_ws, payload)


async def handle_system_action(
    user: dict,
    panel_ws,
    request_id: Optional[str],
    target: str,
    action: str,
) -> None:
    if user.get("role") != "admin":
        await send_error(panel_ws, request_id, "forbidden", "Solo un administrador")
        return

    target = (target or "").lower()
    action = (action or "").lower()
    if target not in VALID_TARGETS or action not in VALID_ACTIONS:
        await send_error(panel_ws, request_id, "invalid_params", "Destino o acción inválidos")
        return

    if not settings.SYSTEM_ACTIONS_ENABLED:
        await send_error(panel_ws, request_id, "systemd_unavailable", "Acciones de sistema deshabilitadas")
        return

    actor = user.get("username", "USER")

    # Regla de no autoapagado: el backend nunca se detiene desde el panel.
    if target == "backend" and action == "stop":
        await send_error(panel_ws, request_id, "forbidden", "El backend no puede detenerse desde el panel")
        return
    if target == "backend" and action == "start":
        await send_error(panel_ws, request_id, "forbidden", "El backend ya está en ejecución")
        return

    if target == "backend" and action == "restart":
        await _send_result(panel_ws, request_id, True, "Reinicio del backend programado")
        await record_audit("SYSTEM_BACKEND_RESTART", actor=actor)

        async def _later():
            await asyncio.sleep(1.0)
            code, output = await _run_ctl("backend-restart")
            logger.info("backend-restart -> %s: %s", code, output)

        asyncio.create_task(_later())
        return

    if target == "panel":
        code, output = await _run_ctl(f"panel-{action}")
        ok = code == 0
        await record_audit(
            f"SYSTEM_PANEL_{action.upper()}",
            actor=actor,
            details=output[:300],
        )
        if code == 127:
            await send_error(panel_ws, request_id, "systemd_unavailable", output)
        else:
            await _send_result(panel_ws, request_id, ok, output, "" if ok else output)
        return

    if target == "all":
        if action == "status":
            code, output = await _run_ctl("status")
            await _send_result(panel_ws, request_id, code == 0, output, "" if code == 0 else output)
            return

        if action == "stop":
            slept = await _sleep_all_devices(60)
            code, output = await _run_ctl("panel-stop")
            ok = code in (0, 127)
            await record_audit(
                "SYSTEM_ALL_STOP",
                actor=actor,
                details=f"Dispositivos dormidos={slept}; panel: {output[:200]}",
            )
            await _send_result(
                panel_ws,
                request_id,
                ok,
                f"Panel detenido. Dispositivos dormidos: {slept}. El backend sigue activo.",
            )
            return

        if action == "start":
            code, output = await _run_ctl("panel-start")
            ok = code == 0
            await record_audit("SYSTEM_ALL_START", actor=actor, details=output[:300])
            message = (
                f"{output}\nLos dispositivos en deep sleep no pueden despertarse por red: "
                "usan el temporizador o el botón físico."
            )
            if code == 127:
                await send_error(panel_ws, request_id, "systemd_unavailable", output)
            else:
                await _send_result(panel_ws, request_id, ok, message, "" if ok else output)
            return

        if action == "restart":
            rebooted = await _reboot_all_devices()
            code, output = await _run_ctl("panel-restart")
            ok = code in (0, 127)
            await record_audit(
                "SYSTEM_ALL_RESTART",
                actor=actor,
                details=f"Dispositivos reiniciados={rebooted}; panel: {output[:200]}",
            )
            await _send_result(panel_ws, request_id, ok, f"Panel reiniciado. Dispositivos: {rebooted}")
            return

    await send_error(panel_ws, request_id, "invalid_params", "Combinación no soportada")
