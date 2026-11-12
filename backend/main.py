import asyncio
import logging
import signal
import sys
from datetime import datetime
from urllib.parse import urlparse

import websockets
from websockets.server import WebSocketServerProtocol

from backend.config import settings
from backend.database.connect import init_db
from backend.handlers.device_handler import handle_device_message
from backend.handlers.panel_handler import (
    handle_panel_message,
    send_full_sync,
    wait_for_panel_auth,
)
from backend.handlers.state import server_state
from backend.security.auth import is_origin_allowed, record_audit
from backend.services import db_service
from backend.workers.thread_pool import worker_pool

# Configuración de Logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.BACKEND_LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("DispWatter.Main")


async def _handle_device_socket(websocket: WebSocketServerProtocol):
    logger.info("[ROUTER] Nueva conexión de hardware desde %s", websocket.remote_address)
    try:
        async for message in websocket:
            await handle_device_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        device_id = server_state.unregister_device_socket(websocket)
        if device_id:
            try:
                await db_service.update_device_online(device_id, is_online=False)
            except Exception:
                logger.exception("No se pudo marcar el dispositivo como offline")
            # El firmware apaga el relé al perder la conexión: el panel no debe
            # seguir mostrando la bomba encendida con datos viejos.
            cached = server_state.telemetry_cache.get(device_id)
            if cached:
                cached["relay_state"] = False
            server_state.clear_manual_hold(device_id)
            server_state.recent_readings.pop(device_id, None)
            await server_state.broadcast_to_panels(
                {"event": "relay_state", "device_id": device_id, "relay_state": False, "source": "disconnect"}
            )
            await record_audit("DEVICE_DISCONNECTED", device_id=device_id)
            logger.info("[DISPOSITIVO] %s desconectado", device_id)
            await server_state.broadcast_to_panels(
                {"event": "device_status", "device_id": device_id, "is_online": False}
            )


async def _handle_panel_socket(websocket: WebSocketServerProtocol):
    origin = websocket.request_headers.get("Origin")
    if not is_origin_allowed(origin):
        logger.warning("[PANEL] Origen rechazado: %s", origin)
        await websocket.close(1008, "Origen no permitido")
        return

    logger.info("[ROUTER] Nueva sesión de panel desde %s (origin=%s)", websocket.remote_address, origin)
    user = await wait_for_panel_auth(websocket)
    if user is None:
        try:
            await websocket.close(1008, "Autenticación requerida")
        except Exception:
            pass
        return

    server_state.register_panel(websocket, user)
    await record_audit("PANEL_CONNECTED", actor=user["username"], details="Sesión WebSocket iniciada")
    try:
        await send_full_sync(websocket)
        async for message in websocket:
            await handle_panel_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        server_state.unregister_panel(websocket)
        server_state.drop_requests_for_panel(websocket)
        logger.info("[PANEL] Sesión cerrada (%s)", user["username"])


async def router(websocket: WebSocketServerProtocol, path: str):
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    if clean_path == "/ws/device":
        await _handle_device_socket(websocket)
    elif clean_path == "/ws/panel":
        await _handle_panel_socket(websocket)
    else:
        logger.warning("[ROUTER] Ruta desconocida: %s", path)
        await websocket.close(1000, "Ruta no soportada")


async def main():
    logger.info("==========================================")
    logger.info("   INICIANDO DISPWATTER BACKEND SERVER    ")
    logger.info("==========================================")

    await init_db()
    logger.info("Base de datos inicializada: %s", settings.DB_PATH)

    # Al arrancar, ningún dispositivo está realmente conectado.
    await db_service.mark_all_devices_offline()

    await record_audit("BACKEND_START", details=f"Servidor iniciado en {settings.HOST}:{settings.PORT}")

    # Iniciar threads dedicados
    loop = asyncio.get_running_loop()
    worker_pool.start(loop)

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    async with websockets.serve(
        router,
        settings.HOST,
        settings.PORT,
        max_size=settings.MAX_MESSAGE_SIZE * 20,
    ):
        logger.info("Servidor WebSocket escuchando en ws://%s:%s", settings.HOST, settings.PORT)
        logger.info(" -> Hardware ESP32: ws://%s:%s/ws/device", settings.HOST, settings.PORT)
        logger.info(" -> Panel Web:      ws://%s:%s/ws/panel", settings.HOST, settings.PORT)
        await stop_event.wait()

    logger.info("Deteniendo servidor DispWatter...")
    worker_pool.stop()
    await record_audit("BACKEND_STOP", details="Servidor detenido de manera ordenada.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
