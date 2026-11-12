from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any, Dict

from backend.config import settings

logger = logging.getLogger("DispWatter.SystemWorker")


def _run_async(coro) -> Any:
    """Ejecuta una coroutine en un nuevo event loop dentro del thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def handle(action: str, params: Dict[str, Any]) -> Any:
    """Punto de entrada del system worker. Despacha acciones a funciones async."""
    handlers = {
        "run_ctl": _run_ctl,
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValueError(f"Acción de system desconocida: {action}")
    return _run_async(handler(params))


async def _run_ctl(params: Dict[str, Any]) -> Dict[str, Any]:
    args = params.get("args", [])
    timeout = params.get("timeout", 25.0)

    ctl = settings.DISPWATTER_CTL
    if not os.path.isfile(ctl):
        return {
            "code": 127,
            "output": f"No se encuentra {ctl}. Instala deploy/dispwatter-ctl y deploy/sudoers.d/dispwatter.",
        }

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
        return {
            "code": proc.returncode or 0,
            "output": output.decode("utf-8", errors="replace").strip(),
        }
    except asyncio.TimeoutError:
        return {"code": 124, "output": "Tiempo de espera agotado ejecutando dispwatter-ctl"}
    except Exception as exc:
        return {"code": 1, "output": f"Error ejecutando dispwatter-ctl: {exc}"}
