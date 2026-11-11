from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import Device, DeviceNetwork, TankConfig, Telemetry
from backend.handlers.state import server_state
from backend.security.auth import (
    record_audit,
    verify_device_proof,
)

logger = logging.getLogger("DispWatter.Device")

_telemetry_writes = 0


async def _send(websocket, payload: dict) -> None:
    try:
        await websocket.send(json.dumps(payload))
    except Exception:
        logger.debug("No se pudo enviar mensaje al dispositivo")


async def _get_device(session, device_id: str) -> Optional[Device]:
    result = await session.execute(select(Device).where(Device.id == device_id))
    return result.scalar_one_or_none()


async def _ensure_device(
    session,
    device_id: str,
    name: str,
    location: str,
    firmware: str,
) -> Device:
    device = await _get_device(session, device_id)
    if device is None:
        device = Device(
            id=device_id,
            name=name or f"Bebedero {device_id}",
            location=location or "Sin ubicación",
            firmware_version=firmware or "1.0.0",
            key_hash=None,
            status="PENDING_CLAIM",
            is_online=False,
        )
        session.add(device)
        session.add(TankConfig(device_id=device_id))
        await session.commit()
        await session.refresh(device)
        await record_audit(
            "DEVICE_AUTO_REGISTERED",
            device_id=device_id,
            details=f"Pendiente de vinculación ({device.name}, {device.location})",
        )
    else:
        if device.status == "PENDING_CLAIM":
            if name:
                device.name = name
            if location:
                device.location = location
        if firmware:
            device.firmware_version = firmware
        await session.commit()
    return device


async def _issue_challenge(websocket, purpose: str = "auth") -> str:
    nonce = server_state.new_challenge(websocket, purpose)
    await _send(
        websocket,
        {"event": "challenge", "nonce": nonce, "expires_in": 30, "purpose": purpose},
    )
    logger.info("[DEVICE_CHALLENGE] websocket=%s purpose=%s nonce=%s", id(websocket), purpose, nonce)
    return nonce


async def _handle_hello(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await _send(websocket, {"event": "auth_status", "status": "error", "error": "invalid_device_id"})
        return

    name = str(data.get("name") or "")
    location = str(data.get("location") or "")
    firmware = str(data.get("firmware") or "1.0.0")

    logger.info(
        "[DEVICE_HELLO] device_id=%s firmware=%s name=%s location=%s",
        device_id,
        firmware,
        name,
        location,
    )

    async with get_db() as session:
        await _ensure_device(session, device_id, name, location, firmware)

    server_state.register_pending_device(device_id, websocket)
    await _issue_challenge(websocket, "auth")


async def _handle_auth(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "").strip()
    nonce = str(data.get("nonce") or "")
    proof = str(data.get("proof") or "").lower()

    logger.info("[DEVICE_AUTH] device_id=%s nonce=%s proof_len=%s", device_id, nonce, len(proof))

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
    claim_nonce = claim["nonce"] if claim else None

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
            return

        # --- Autenticación normal de un dispositivo ya vinculado ---
        if not verify_device_proof(device.key_hash, nonce, proof):
            logger.warning("[DEVICE_AUTH_FAILED] device_id=%s proof_invalid=%s", device_id, proof)
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


def _device_authorized(websocket, device_id: str) -> bool:
    return server_state.device_sockets.get(device_id) is websocket


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

    async with get_db() as session:
        result = await session.execute(select(TankConfig).where(TankConfig.device_id == device_id))
        cfg = result.scalar_one_or_none()

        bottom = cfg.bottom_dist_mm if cfg else 900.0
        mirror = cfg.mirror_dist_mm if cfg else 100.0
        capacity = cfg.capacity_liters if cfg else 50.0
        min_lvl = cfg.min_level_percent if cfg else 25.0
        max_lvl = cfg.max_level_percent if cfg else 90.0
        auto_refill = cfg.auto_refill if cfg else True

        usable_height = max(1.0, bottom - mirror)
        water_height = bottom - distance_mm
        percent = max(0.0, min(100.0, (water_height / usable_height) * 100.0))
        liters = round(capacity * percent / 100.0, 1)

        session.add(
            Telemetry(
                device_id=device_id,
                distance_mm=distance_mm,
                water_percent=percent,
                water_liters=liters,
                relay_state=relay_state,
            )
        )

        device = await _get_device(session, device_id)
        if device:
            device.last_seen = datetime.utcnow()
            device.is_online = True

        await session.commit()

    global _telemetry_writes
    _telemetry_writes += 1
    if _telemetry_writes % 100 == 0:
        cutoff = datetime.utcnow() - timedelta(hours=settings.TELEMETRY_RETENTION_HOURS)
        async with get_db() as session:
            await session.execute(delete(Telemetry).where(Telemetry.created_at < cutoff))
            await session.commit()

    server_state.telemetry_cache[device_id] = {
        "distance_mm": distance_mm,
        "percent": round(percent, 1),
        "liters": liters,
        "relay_state": relay_state,
        "updated_at": time.time(),
    }

    if auto_refill and device.status == "CLAIMED":
        if percent <= min_lvl and not relay_state:
            await server_state.send_to_device(
                device_id, {"command": "set_relay", "state": True, "request_id": "auto-on"}
            )
            await server_state.send_to_device(
                device_id,
                {
                    "command": "display",
                    "line0": f"Nivel {percent:.0f}% {liters:.0f}L",
                    "line1": "Llenando...",
                    "clear": False,
                    "request_id": "auto-on-lcd",
                },
            )
            await record_audit("AUTO_REFILL_ON", device_id=device_id, details=f"Nivel {percent:.1f}% <= {min_lvl}%")
        elif percent >= max_lvl and relay_state:
            await server_state.send_to_device(
                device_id, {"command": "set_relay", "state": False, "request_id": "auto-off"}
            )
            await server_state.send_to_device(
                device_id,
                {
                    "command": "display",
                    "line0": f"Nivel {percent:.0f}% {liters:.0f}L",
                    "line1": "Tanque lleno",
                    "clear": False,
                    "request_id": "auto-off-lcd",
                },
            )
            await record_audit("AUTO_REFILL_OFF", device_id=device_id, details=f"Nivel {percent:.1f}% >= {max_lvl}%")

    await server_state.broadcast_to_panels(
        {
            "event": "telemetry",
            "device_id": device_id,
            "distance_mm": distance_mm,
            "water_percent": round(percent, 1),
            "water_liters": liters,
            "relay_state": relay_state,
        }
    )


async def _handle_device_status(websocket, data: dict) -> None:
    device_id = str(data.get("device_id") or "")
    if not _device_authorized(websocket, device_id):
        return

    rssi = data.get("rssi")
    ip = data.get("ip")
    wake_reason = data.get("wake_reason")

    async with get_db() as session:
        device = await _get_device(session, device_id)
        if device:
            device.last_seen = datetime.utcnow()
            device.is_online = True
            if isinstance(rssi, int):
                device.last_rssi = rssi
            if ip:
                device.last_ip = str(ip)
            if wake_reason:
                device.wake_reason = str(wake_reason)
            await session.commit()

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
    async with get_db() as session:
        await session.execute(delete(DeviceNetwork).where(DeviceNetwork.device_id == device_id))
        for item in networks:
            if not isinstance(item, dict):
                continue
            ssid = str(item.get("ssid") or "").strip()
            if not ssid:
                continue
            session.add(
                DeviceNetwork(
                    device_id=device_id,
                    ssid=ssid[:64],
                    priority=int(item.get("priority") or 0),
                    has_password=bool(item.get("has_password", True)),
                    rssi=item.get("rssi"),
                    visible=bool(item.get("visible", False)),
                    connected=bool(item.get("connected", False)),
                )
            )
        await session.commit()


async def _handle_command_result(websocket, data: dict) -> None:
    event = str(data.get("event") or "")
    request_id = str(data.get("request_id") or "")
    device_id = str(data.get("device_id") or "")

    if request_id:
        server_state.resolve_request(request_id, data)

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























































































































































