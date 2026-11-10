import asyncio
import logging
import signal
import sys
from urllib.parse import urlparse
import websockets
from websockets.server import WebSocketServerProtocol

from backend.config import settings
from backend.database.connect import init_db
from backend.security.auth import record_audit
from backend.handlers.state import server_state
from backend.handlers.device_handler import handle_device_message
from backend.handlers.panel_handler import handle_panel_message, send_full_sync

# Configuración de Logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.BACKEND_LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("DispWatter.Main")

async def router(websocket: WebSocketServerProtocol, path: str):
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    # Conexión desde ESP32
    if clean_path == "/ws/device":
        logger.info(f"[ROUTER] Nueva conexión de hardware desde {websocket.remote_address}")
        current_device_id = None
        try:
            async for message in websocket:
                await handle_device_message(websocket, message)
                # Extraer id para el cierre
                for dev_id, sock in list(server_state.device_sockets.items()):
                    if sock == websocket:
                        current_device_id = dev_id
                        break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if current_device_id:
                server_state.unregister_device(current_device_id)
                await record_audit("DEVICE_DISCONNECTED", device_id=current_device_id)
                logger.info(f"[DISPOSITIVO] {current_device_id} desconectado.")
                await server_state.broadcast_to_panels({
                    "event": "device_status",
                    "device_id": current_device_id,
                    "is_online": False
                })

    # Conexión desde el Panel Frontend
    elif clean_path == "/ws/panel":
        logger.info(f"[ROUTER] Nueva sesión de panel web desde {websocket.remote_address}")
        server_state.register_panel(websocket)
        try:
            await send_full_sync(websocket)
            async for message in websocket:
                await handle_panel_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            server_state.unregister_panel(websocket)
            logger.info(f"[PANEL] Sesión de panel cerrada.")

    else:
        logger.warning(f"[ROUTER] Ruta desconocida: {path}")
        await websocket.close(1000, "Ruta no soportada")

async def main():
    logger.info("==========================================")
    logger.info("   INICIANDO DISPWATTER BACKEND SERVER    ")
    logger.info("==========================================")

    # 1. Inicializar Base de Datos
    await init_db()
    logger.info(f"Base de datos inicializada: {settings.DB_PATH}")

    # 2. Registrar evento de inicio en auditoría
    await record_audit("BACKEND_START", details=f"Servidor iniciado en {settings.HOST}:{settings.PORT}")

    # 3. Arrancar Servidor WebSockets
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: stop_event.set())
        except NotImplementedError:
            pass

    async with websockets.serve(
        router,
        settings.HOST,
        settings.PORT,
        max_size=settings.MAX_MESSAGE_SIZE * 10
    ):
        logger.info(f"Servidor WebSocket escuchando en ws://{settings.HOST}:{settings.PORT}")
        logger.info(f" -> Hardware ESP32: ws://{settings.HOST}:{settings.PORT}/ws/device")
        logger.info(f" -> Panel Web:      ws://{settings.HOST}:{settings.PORT}/ws/panel")
        await stop_event.wait()

    logger.info("Deteniendo servidor DispWatter...")
    await record_audit("BACKEND_STOP", details="Servidor detenido de manera ordenada.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
