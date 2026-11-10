import json
import logging
from sqlalchemy import select
from backend.database.connect import get_db
from backend.database.models import Device, TankConfig, Telemetry
from backend.security.auth import record_audit
from backend.handlers.state import server_state

logger = logging.getLogger("DispWatter.Panel")

async def send_full_sync(websocket):
    """Envía la lista completa de dispositivos, configuración y últimas métricas al panel recién conectado."""
    async with get_db() as session:
        result = await session.execute(select(Device))
        devices = result.scalars().all()

        device_list = []
        for dev in devices:
            # Obtener configuración
            cfg_res = await session.execute(select(TankConfig).where(TankConfig.device_id == dev.id))
            cfg = cfg_res.scalar_one_or_none()
            
            # Obtener última telemetría
            cached_tel = server_state.telemetry_cache.get(dev.id)

            device_list.append({
                "id": dev.id,
                "name": dev.name,
                "hash": dev.key_hash,
                "claimed": (dev.status == "CLAIMED"),
                "online": (dev.id in server_state.device_sockets),
                "capacity": cfg.capacity_liters if cfg else 50.0,
                "bottomDist": cfg.bottom_dist_mm if cfg else 900.0,
                "mirrorDist": cfg.mirror_dist_mm if cfg else 100.0,
                "minLevel": cfg.min_level_percent if cfg else 25.0,
                "maxLevel": cfg.max_level_percent if cfg else 90.0,
                "autoRefill": cfg.auto_refill if cfg else True,
                "currentDist": cached_tel["distance_mm"] if cached_tel else 500.0,
                "relayState": cached_tel["relay_state"] if cached_tel else False
            })

    await websocket.send(json.dumps({
        "event": "sync_all",
        "devices": device_list
    }))

async def handle_panel_message(websocket, raw_message: str):
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        logger.warning(f"Mensaje de panel JSON inválido: {raw_message}")
        return

    event = data.get("event")
    command = data.get("command")

    # ==========================================
    # 1. RECLAMAR / VINCULAR DISPOSITIVO
    # ==========================================
    if event == "claim_device":
        device_id = data.get("device_id")
        device_hash = data.get("device_hash")
        name = data.get("name", f"Bebedero {device_id}")

        async with get_db() as session:
            result = await session.execute(select(Device).where(Device.id == device_id))
            device = result.scalar_one_or_none()

            if not device:
                device = Device(
                    id=device_id,
                    name=name,
                    key_hash=device_hash,
                    status="CLAIMED",
                    owner_id="USER-PRIMARY"
                )
                session.add(device)
                cfg = TankConfig(device_id=device_id)
                session.add(cfg)
            else:
                device.name = name
                device.key_hash = device_hash
                device.status = "CLAIMED"
                device.owner_id = "USER-PRIMARY"

            await session.commit()
            await record_audit("DEVICE_CLAIMED", device_id=device_id, actor="USER", details=f"Dispositivo {device_id} reclamado exitosamente.")

        await websocket.send(json.dumps({
            "event": "claim_result",
            "status": "success",
            "device_id": device_id
        }))
        logger.info(f"[PANEL] Dispositivo {device_id} reclamado por el usuario.")

    # ==========================================
    # 2. ACTUALIZAR CONFIGURACIÓN DE TANQUE
    # ==========================================
    elif event == "update_config":
        device_id = data.get("device_id")
        cfg_data = data.get("config", {})

        async with get_db() as session:
            result = await session.execute(select(TankConfig).where(TankConfig.device_id == device_id))
            cfg = result.scalar_one_or_none()

            if not cfg:
                cfg = TankConfig(device_id=device_id)
                session.add(cfg)

            if "capacity" in cfg_data: cfg.capacity_liters = float(cfg_data["capacity"])
            if "bottom_dist_mm" in cfg_data: cfg.bottom_dist_mm = float(cfg_data["bottom_dist_mm"])
            if "mirror_dist_mm" in cfg_data: cfg.mirror_dist_mm = float(cfg_data["mirror_dist_mm"])
            if "min_level" in cfg_data: cfg.min_level_percent = float(cfg_data["min_level"])
            if "max_level" in cfg_data: cfg.max_level_percent = float(cfg_data["max_level"])
            if "auto_refill" in cfg_data: cfg.auto_refill = bool(cfg_data["auto_refill"])

            await session.commit()
            await record_audit("CONFIG_UPDATED", device_id=device_id, actor="USER", details=str(cfg_data))

        logger.info(f"[PANEL] Configuración actualizada para {device_id}")

    # ==========================================
    # 3. CONTROL MANUAL DE RELÉ
    # ==========================================
    elif command == "set_relay":
        device_id = data.get("device_id")
        state = bool(data.get("state", False))

        # Enviar comando directo al hardware ESP32
        sent = await server_state.send_to_device(device_id, {"command": "set_relay", "state": state})
        await record_audit("MANUAL_RELAY", device_id=device_id, actor="USER", details=f"Comando Relé={state} (Enviado al ESP32: {sent})")
        logger.info(f"[PANEL] Orden Relé={state} para {device_id} (Hardware notificado: {sent})")

    # ==========================================
    # 4. COMANDO DE TEXTO PARA PANTALLA LCD
    # ==========================================
    elif command == "display":
        device_id = data.get("device_id")
        line0 = data.get("line0", "")
        line1 = data.get("line1", "")
        clear = bool(data.get("clear", True))

        sent = await server_state.send_to_device(device_id, {
            "command": "display",
            "line0": line0,
            "line1": line1,
            "clear": clear
        })
        await record_audit("MANUAL_DISPLAY", device_id=device_id, actor="USER", details=f"LCD l0='{line0}' l1='{line1}'")
        logger.info(f"[PANEL] Texto enviado a LCD de {device_id}: {line0} / {line1}")
