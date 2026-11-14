from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import Device, TankConfig
from backend.handlers.state import server_state
from backend.security.auth import (
    record_audit,
    verify_device_proof,
)
from backend.services import db_service
from backend.workers.thread_pool import worker_pool

logger = logging.getLogger("DispWatter.Device")

_telemetry_writes = 0


async def _send(websocket, payload: dict) -> None:
    try:
        await websocket.send(json.dumps(payload))
    except Exception:
        logger.debug("No se pudo enviar mensaje al dispositivo")


async def _send_pending_config(device_id: str) -> None:
    """Envía la configuración actual del TankConfig al dispositivo recién conectado.

    Si el panel modificó la configuración mientras el dispositivo estaba offline,
    este comando asegura que el ESP32 reciba los valores más recientes.
    """
    cfg = await db_service.get_tank_config(device_id)
    if cfg is None:
        return
    try:
        await server_state.send_to_device(
            device_id,
            {
                "command": "update_config",
                "config": {
                    "capacity": cfg.capacity_liters,
                    "bottom_dist_mm": cfg.bottom_dist_mm,
                    "mirror_dist_mm": cfg.mirror_dist_mm,
                    "min_level": cfg.min_level_percent,
                    "max_level": cfg.max_level_percent,
                    "auto_refill": cfg.auto_refill,
                    "min_relay_off_min": cfg.min_relay_off_min,
                    "overflow_protection": cfg.overflow_protection,
                    "menu_lock": cfg.menu_lock,
                },
            },
        )
        logger.info("[CONFIG] Configuración enviada al dispositivo %s al conectar", device_id)
    except Exception:
        logger.debug("No se pudo enviar configuración pendiente a %s", device_id)


async def _get_device(session, device_id: str) -> Optional[Device]:
    return await db_service.get_device_in_session(session, device_id)


async def _ensure_device(
    session,
    device_id: str,
    name: str,
    location: str,
    firmware: str,
) -> Device:
    return await db_service.ensure_device_in_session(session, device_id, name, location, firmware)


async def _issue_challenge(websocket, purpose: str = "auth") -> str:
    nonce = server_state.new_challenge(websocket, purpose)
    await _send(
        websocket,
        {"event": "challenge", "nonce": nonce, "expires_in": 30, "purpose": purpose},
    )
    return nonce


async def _handle_hello(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_device_id"})
        return

    name = str(data.get("name") or "")
    location = str(data.get("location") or "")
    firmware = str(data.get("firmware") or "1.0.0")

    async with get_db() as session:
        await _ensure_device(session, device_id, name, location, firmware)

    # Permite enviar el challenge de claim incluso si aún no terminó su auth.
    server_state.register_pending_device(device_id, websocket)
    await _issue_challenge(websocket, "auth")


async def _handle_auth(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "").strip()
    nonce = str(data.get("nonce") or "")
    proof = str(data.get("proof") or "").lower()

    if not device_id or not nonce or len(proof) != 64:
        await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_params"})
        return

    challenge = server_state.consume_challenge(websocket, nonce)
    if not challenge:
        await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_nonce"})
        await record_audit("DEVICE_AUTH_FAILED", device_id=device_id, details="Nonce inválido o caducado")
        return

    name = str(data.get("name") or "")
    location = str(data.get("location") or "")
    firmware = str(data.get("firmware") or "1.0.0")
    wake_reason = str(data.get("wake_reason") or "")

    claim = server_state.claim_attempts.get(device_id)
    claim_nonce = claim.get("nonce") if claim else None

    async with get_db() as session:
        device = await _ensure_device(session, device_id, name, location, firmware)
        if device.status == "BLOCKED":
            await _send(websocket, {"event": "auth_status", "status": "error", "error": "blocked"})
            await record_audit("DEVICE_AUTH_BLOCKED", device_id=device_id)
            return

        # --- Flujo de vinculación (claim) ---
        if claim and claim_nonce == nonce:
            expected_hash = claim["expected_hash"]
            if verify_device_proof(expected_hash, nonce, proof):
                device.key_hash = expected_hash
                device.status = "CLAIMED"
                device.owner_id = claim["user"]["id"]
                device.is_online = True
                device.last_seen = datetime.utcnow()
                device.last_ip = str(data.get("ip") or "") or device.last_ip
                device.last_rssi = data.get("rssi")
                device.wake_reason = wake_reason or device.wake_reason
                await session.commit()

                server_state.claim_attempts.pop(device_id, None)
                future = claim.get("future")
                if future and not future.done():
                    future.set_result(
                        {
                            "ok": True,
                            "device_id": device.id,
                            "name": device.name,
                            "status": device.status,
                        }
                    )

                server_state.register_device(device_id, websocket)
                await _send(websocket, {"event": "auth_status", "status": "ok", "device_id": device_id})
                await record_audit(
                    "DEVICE_CLAIMED",
                    device_id=device_id,
                    actor=claim["user"].get("username", "USER"),
                    details="Vinculación verificada con challenge-response",
                )
                await server_state.broadcast_to_panels(
                    {"event": "device_status", "device_id": device_id, "is_online": True, "claimed": True}
                )
                await _send_pending_config(device_id)
            else:
                server_state.claim_attempts.pop(device_id, None)
                future = claim.get("future")
                if future and not future.done():
                    future.set_result({"ok": False, "error": "invalid_credentials"})
                await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_proof"})
                await record_audit(
                    "DEVICE_CLAIM_FAILED",
                    device_id=device_id,
                    actor=claim["user"].get("username", "USER"),
                    details="El proof HMAC no coincide con el secreto indicado",
                )
            return

        # --- Dispositivo todavía sin secreto verificado ---
        if not device.key_hash:
            device.is_online = True
            device.last_seen = datetime.utcnow()
            if name:
                device.name = name
            if location:
                device.location = location
            await session.commit()

            server_state.register_device(device_id, websocket)
            await _send(
                websocket,
                {"event": "auth_status", "status": "pending_claim", "device_id": device_id},
            )
            await record_audit(
                "DEVICE_PENDING_CONNECTED",
                device_id=device_id,
                details="Conectado sin vincular; solo telemetría",
            )
            await server_state.broadcast_to_panels(
                {"event": "device_status", "device_id": device_id, "is_online": True, "claimed": False}
            )
            await _send_pending_config(device_id)
            return

        # --- Autenticación normal de un dispositivo ya vinculado ---
        if not verify_device_proof(device.key_hash, nonce, proof):
            await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_proof"})
            await record_audit("DEVICE_AUTH_FAILED", device_id=device_id, details="Proof HMAC incorrecto")
            return

        device.is_online = True
        device.last_seen = datetime.utcnow()
        if name and device.status == "PENDING_CLAIM":
            device.name = name
        if location:
            device.location = location
        if firmware:
            device.firmware_version = firmware
        if wake_reason:
            device.wake_reason = wake_reason
        await session.commit()

        server_state.register_device(device_id, websocket)
        await _send(websocket, {"event": "auth_status", "status": "ok", "device_id": device_id})
        await record_audit("DEVICE_AUTH_SUCCESS", device_id=device_id, details="Challenge-response verificado")
        logger.info("[DISPOSITIVO] %s autenticado", device_id)
        await server_state.broadcast_to_panels(
            {"event": "device_status", "device_id": device_id, "is_online": True, "claimed": device.status == "CLAIMED"}
        )
        await _send_pending_config(device_id)


def _device_authorized(websocket, device_id: str) -> bool:
    return server_state.device_sockets.get(device_id) is websocket


def compute_level(
    distance_mm: float, bottom: float, mirror: float, capacity: float
) -> tuple[float, float, float]:
    """Convierte la distancia del sensor en (porcentaje, litros, altura del agua en mm).

    Modelo (todas las medidas se toman desde el sensor hacia abajo):
      - bottom : distancia sensor -> fondo del tanque (tanque vacío).
      - mirror : distancia sensor -> espejo de agua con el tanque al máximo.
      - altura útil      = bottom - mirror
      - altura del agua  = bottom - distancia medida
      - porcentaje       = altura del agua / altura útil
      - litros           = capacidad * porcentaje   (tanque de sección constante)
    """
    usable_height = max(1.0, bottom - mirror)
    water_height = max(0.0, bottom - distance_mm)
    percent = max(0.0, min(100.0, (water_height / usable_height) * 100.0))
    liters = round(capacity * percent / 100.0, 1)
    return percent, liters, water_height


async def _publish_relay_state(device_id: str, relay_state: bool, source: str) -> None:
    """Actualiza la caché y avisa a todos los paneles del estado REAL del relé."""
    cached = server_state.telemetry_cache.get(device_id)
    if cached is not None:
        cached["relay_state"] = relay_state
    await server_state.broadcast_to_panels(
        {
            "event": "relay_state",
            "device_id": device_id,
            "relay_state": relay_state,
            "source": source,
        }
    )


async def _handle_telemetry(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "")
    if not _device_authorized(websocket, device_id):
        return

    try:
        distance_mm = float(data.get("distance_mm", 0.0))
    except (TypeError, ValueError):
        return
    if not (0.0 <= distance_mm <= 12000.0):
        return

    relay_state = bool(data.get("relay_state", False))
    server_state.record_reading(device_id, distance_mm)

    # Obtener config del tanque
    cfg = await db_service.get_tank_config(device_id)

    bottom = cfg.bottom_dist_mm if cfg else 900.0
    mirror = cfg.mirror_dist_mm if cfg else 100.0
    capacity = cfg.capacity_liters if cfg else 50.0
    min_lvl = cfg.min_level_percent if cfg else 25.0
    max_lvl = cfg.max_level_percent if cfg else 90.0
    auto_refill = cfg.auto_refill if cfg else True

    percent, liters, water_height = compute_level(distance_mm, bottom, mirror, capacity)

    # Obtener dispositivo para verificar si está claimed
    device = await db_service.get_device(device_id)
    device_claimed = bool(device and device.status == "CLAIMED")

    # Enviar tarea al worker de device para guardar telemetría en BD
    try:
        await worker_pool.submit(
            "device",
            "save_telemetry",
            device_id=device_id,
            distance_mm=distance_mm,
            water_percent=percent,
            water_liters=liters,
            relay_state=relay_state,
        )
    except Exception:
        logger.exception("Error guardando telemetría en worker")

    global _telemetry_writes
    _telemetry_writes += 1
    if _telemetry_writes % 100 == 0:
        try:
            await worker_pool.submit(
                "device",
                "cleanup_telemetry",
                retention_hours=settings.TELEMETRY_RETENTION_HOURS,
            )
        except Exception:
            logger.exception("Error limpiando telemetría vieja")

    server_state.telemetry_cache[device_id] = {
        "distance_mm": distance_mm,
        "percent": round(percent, 1),
        "liters": liters,
        "height_mm": round(water_height, 1),
        "relay_state": relay_state,
        "updated_at": time.time(),
    }

    # Valores para la pantalla LCD del dispositivo (la distancia la mide el propio ESP32).
    if device_claimed:
        await server_state.send_to_device(
            device_id,
            {"event": "level", "percent": round(percent, 1), "liters": liters},
        )

    # --- Llenado automático con histéresis (enciende en el mínimo, apaga en el máximo) ---
    if percent >= max_lvl:
        # Tanque lleno: se levanta la pausa manual.
        server_state.clear_manual_hold(device_id)
    if not auto_refill:
        server_state.clear_manual_hold(device_id)

    on_hold = server_state.is_on_hold(device_id)

    if auto_refill and device_claimed:
        if percent <= min_lvl and not relay_state and not on_hold:
            await server_state.send_to_device(
                device_id, {"command": "set_relay", "state": True, "request_id": "auto-on"}
            )
            await record_audit("AUTO_REFILL_ON", device_id=device_id, details=f"Nivel {percent:.1f}% <= {min_lvl}%")
        elif percent >= max_lvl and relay_state:
            await server_state.send_to_device(
                device_id, {"command": "set_relay", "state": False, "request_id": "auto-off"}
            )
            await record_audit("AUTO_REFILL_OFF", device_id=device_id, details=f"Nivel {percent:.1f}% >= {max_lvl}%")

    await server_state.broadcast_to_panels(
        {
            "event": "telemetry",
            "device_id": device_id,
            "distance_mm": distance_mm,
            "water_percent": round(percent, 1),
            "water_liters": liters,
            "water_height_mm": round(water_height, 1),
            "relay_state": relay_state,
            "auto_paused": bool(auto_refill and on_hold),
        }
    )


async def _handle_device_status(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "")
    if not _device_authorized(websocket, device_id):
        return

    rssi = data.get("rssi")
    ip = data.get("ip")
    wake_reason = data.get("wake_reason")

    # Enviar tarea al worker para actualizar estado del dispositivo
    try:
        await worker_pool.submit(
            "device",
            "update_device_status",
            device_id=device_id,
            is_online=True,
            last_seen=True,
            last_ip=str(ip) if ip else None,
            last_rssi=rssi if isinstance(rssi, int) else None,
            wake_reason=str(wake_reason) if wake_reason else None,
        )
    except Exception:
        logger.exception("Error actualizando estado del dispositivo")

    await server_state.broadcast_to_panels(
        {
            "event": "device_status",
            "device_id": device_id,
            "is_online": True,
            "rssi": rssi,
            "ip": ip,
            "uptime_s": data.get("uptime_s"),
            "free_heap": data.get("free_heap"),
            "wake_reason": wake_reason,
            "firmware": data.get("firmware"),
            "pending_claim": bool(data.get("pending_claim")),
        }
    )


async def _update_network_cache(device_id: str, networks: list) -> None:
    try:
        await worker_pool.submit(
            "device",
            "update_device_networks",
            device_id=device_id,
            networks=networks,
        )
    except Exception:
        logger.exception("Error actualizando caché de redes")


async def _handle_command_result(websocket, data: dict) -> None:
    event = str(data.get("event") or "")
    request_id = str(data.get("request_id") or "")
    device_id = str(data.get("device_id") or "")

    if request_id:
        server_state.resolve_request(request_id, data)

    # El ack de set_relay incluye el estado REAL aplicado por el firmware.
    if event == "ack" and device_id and isinstance(data.get("relay_state"), bool):
        source = "auto" if request_id.startswith("auto-") else "manual"
        await _publish_relay_state(device_id, data["relay_state"], source)

    if event == "wifi_list" and device_id:
        networks = data.get("networks")
        if isinstance(networks, list):
            await _update_network_cache(device_id, networks)


async def handle_device_message(websocket, raw_message: str) -> None:
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        logger.warning("JSON no válido de dispositivo: %s", raw_message[:200])
        return

    if not isinstance(data, dict):
        return

    event = str(data.get("event") or "")

    if event == "hello":
        await _handle_hello(websocket, data)
        return

    if event == "auth":
        await _handle_auth(websocket, data)
        return

    mapped_id = server_state.device_ids.get(websocket)

    # El firmware no repite device_id en ack/wifi_list: se deriva del socket.
    if event in {"ack", "wifi_list"}:
        claimed_id = str(data.get("device_id") or "")
        if not mapped_id or (claimed_id and claimed_id != mapped_id):
            await _send(websocket, {"event": "error", "code": "unauthorized"})
            return
        data["device_id"] = mapped_id
        await _handle_command_result(websocket, data)
        return

    device_id = str(data.get("device_id") or "")
    if not _device_authorized(websocket, device_id):
        await _send(websocket, {"event": "error", "code": "unauthorized", "message": "Autenticación requerida"})
        return

    if event == "telemetry":
        await _handle_telemetry(websocket, data)
    elif event == "device_status":
        await _handle_device_status(websocket, data)
    elif event == "ping":
        await _send(websocket, {"event": "pong", "device_id": device_id})
    else:
        logger.debug("Evento de dispositivo no manejado: %s", event)
