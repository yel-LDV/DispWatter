import json
import logging
from sqlalchemy import select
from backend.database.connect import get_db
from backend.database.models import Device, TankConfig, Telemetry
from backend.security.auth import record_audit, verify_device_token
from backend.handlers.state import server_state

logger = logging.getLogger("DispWatter.Device")

async def handle_device_message(websocket, raw_message: str):
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        logger.warning(f"Mensaje JSON no válido recibido: {raw_message}")
        return

    event = data.get("event")
    device_id = data.get("device_id")

    if not device_id:
        return

    # ==========================================
    # 1. EVENTO DE AUTENTICACIÓN / HANDSHAKE
    # ==========================================
    if event == "auth":
        token = data.get("token", "")
        timestamp = data.get("timestamp", 0)

        async with get_db() as session:
            result = await session.execute(select(Device).where(Device.id == device_id))
            device = result.scalar_one_or_none()

            # Si el dispositivo no existe aún en BD, se pre-registra como PENDING_CLAIM
            if not device:
                # Si no conocemos la clave, usamos un hash provisional derivado del token
                device = Device(
                    id=device_id,
                    name=f"Bebedero {device_id}",
                    key_hash=token,  # Guardado provisional hasta el claim
                    status="PENDING_CLAIM",
                    is_online=True
                )
                session.add(device)
                default_config = TankConfig(
                    device_id=device_id,
                    capacity_liters=50.0,
                    bottom_dist_mm=900.0,
                    mirror_dist_mm=100.0,
                    min_level_percent=25.0,
                    max_level_percent=90.0,
                    auto_refill=True
                )
                session.add(default_config)
                await session.commit()
                await record_audit("DEVICE_AUTO_REGISTERED", device_id=device_id, details="Dispositivo registrado en estado PENDING_CLAIM")
            else:
                device.is_online = True
                await session.commit()

        # Registrar socket en estado activo
        server_state.register_device(device_id, websocket)
        await websocket.send(json.dumps({"auth_status": "ok", "device_id": device_id}))
        await record_audit("DEVICE_AUTH_SUCCESS", device_id=device_id, details=f"Conexión autenticada (ts={timestamp})")
        logger.info(f"[DISPOSITIVO] {device_id} autenticado y conectado.")

        # Notificar a paneles
        await server_state.broadcast_to_panels({
            "event": "device_status",
            "device_id": device_id,
            "is_online": True
        })

    # ==========================================
    # 2. EVENTO DE TELEMETRÍA (DISTANCIA EN MM)
    # ==========================================
    elif event == "telemetry":
        distance_mm = float(data.get("distance_mm", 0.0))
        relay_state = bool(data.get("relay_state", False))

        async with get_db() as session:
            # Obtener configuración geométrica del bebedero
            res_cfg = await session.execute(select(TankConfig).where(TankConfig.device_id == device_id))
            cfg = res_cfg.scalar_one_or_none()

            bottom = cfg.bottom_dist_mm if cfg else 900.0
            mirror = cfg.mirror_dist_mm if cfg else 100.0
            capacity = cfg.capacity_liters if cfg else 50.0
            min_lvl = cfg.min_level_percent if cfg else 25.0
            max_lvl = cfg.max_level_percent if cfg else 90.0
            auto_refill = cfg.auto_refill if cfg else True

            # Fórmulas de cálculo de nivel
            usable_height = max(1.0, bottom - mirror)
            water_height = bottom - distance_mm
            percent = (water_height / usable_height) * 100.0
            percent = max(0.0, min(100.0, percent))
            liters = round((capacity * (percent / 100.0)), 1)

            # Guardar telemetría en BD
            telemetry_row = Telemetry(
                device_id=device_id,
                distance_mm=distance_mm,
                water_percent=percent,
                water_liters=liters,
                relay_state=relay_state
            )
            session.add(telemetry_row)
            await session.commit()

        # Actualizar caché
        server_state.telemetry_cache[device_id] = {
            "distance_mm": distance_mm,
            "percent": percent,
            "liters": liters,
            "relay_state": relay_state
        }

        # Lógica de Riego / Llenado Automático
        if auto_refill:
            if percent <= min_lvl and not relay_state:
                # Nivel bajo detectado -> Encender bomba
                await server_state.send_to_device(device_id, {"command": "set_relay", "state": True})
                await server_state.send_to_device(device_id, {
                    "command": "display",
                    "line0": f"Nivel: {percent:.0f}% {liters:.0f}L",
                    "line1": "Llenando...",
                    "clear": True
                })
                await record_audit("AUTO_REFILL_ON", device_id=device_id, details=f"Nivel {percent:.1f}% <= {min_lvl}%")
            elif percent >= max_lvl and relay_state:
                # Nivel máximo alcanzado -> Apagar bomba
                await server_state.send_to_device(device_id, {"command": "set_relay", "state": False})
                await server_state.send_to_device(device_id, {
                    "command": "display",
                    "line0": f"Nivel: {percent:.0f}% {liters:.0f}L",
                    "line1": "Tanque Lleno",
                    "clear": True
                })
                await record_audit("AUTO_REFILL_OFF", device_id=device_id, details=f"Nivel {percent:.1f}% >= {max_lvl}%")

        # Retransmitir en tiempo real a todos los paneles conectados
        await server_state.broadcast_to_panels({
            "event": "telemetry",
            "device_id": device_id,
            "distance_mm": distance_mm,
            "water_percent": round(percent, 1),
            "water_liters": liters,
            "relay_state": relay_state
        })

    # ==========================================
    # 3. PING / KEEPALIVE
    # ==========================================
    elif event == "ping":
        await websocket.send(json.dumps({"event": "pong", "device_id": device_id}))
