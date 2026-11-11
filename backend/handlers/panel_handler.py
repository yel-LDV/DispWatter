from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import AuditLog, Device, DeviceNetwork, TankConfig, User
from backend.handlers.access import authorize_device
from backend.handlers.device_action import handle_device_action
from backend.handlers.device_command import request_device, send_ack, send_error, send_to_panel
from backend.handlers.state import server_state
from backend.handlers.system_handler import handle_system_action
from backend.handlers.wifi_handler import (
    handle_wifi_add,
    handle_wifi_list,
    handle_wifi_remove,
    handle_wifi_reorder,
)
from backend.security.auth import (
    create_token,
    decode_token,
    hash_credentials,
    record_audit,
    verify_password,
)

logger = logging.getLogger("DispWatter.Panel")


# ---------------------------------------------------------------------------
# Autenticación del panel
# ---------------------------------------------------------------------------
def _client_ip(websocket) -> str:
    try:
        return str(websocket.remote_address[0])
    except Exception:
        return "unknown"


async def _login(websocket, data: dict) -> Optional[dict]:
    ip = _client_ip(websocket)
    limiter = server_state.login_limiter
    if limiter.is_blocked(ip):
        await send_to_panel(
            websocket,
            {"event": "login_result", "ok": False, "error": "rate_limited",
             "message": "Demasiados intentos. Espera unos minutos."},
        )
        return None

    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        limiter.register_failure(ip)
        await asyncio.sleep(0.25)
        await send_to_panel(
            websocket,
            {"event": "login_result", "ok": False, "error": "unauthorized",
             "message": "Usuario o contraseña incorrectos"},
        )
        return None

    async with get_db() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            limiter.register_failure(ip)
            await asyncio.sleep(0.35)
            await send_to_panel(
                websocket,
                {"event": "login_result", "ok": False, "error": "unauthorized",
                 "message": "Usuario o contraseña incorrectos"},
            )
            await record_audit("LOGIN_FAILED", actor=username or "?", details=f"IP={ip}")
            return None

        user.last_login = datetime.utcnow()
        await session.commit()
        user_info = {"id": user.id, "username": user.username, "role": user.role}

    limiter.reset(ip)
    token = create_token(user_info["id"], user_info["role"])
    await send_to_panel(
        websocket,
        {"event": "login_result", "ok": True, "token": token, "user": user_info},
    )
    await record_audit("LOGIN_SUCCESS", actor=user_info["username"], details=f"IP={ip}")
    return user_info


async def _resume(websocket, data: dict) -> Optional[dict]:
    payload = decode_token(str(data.get("token") or ""))
    if not payload:
        await send_to_panel(
            websocket,
            {"event": "resume_result", "ok": False, "error": "unauthorized"},
        )
        return None

    async with get_db() as session:
        result = await session.execute(select(User).where(User.id == payload["sub"]))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            await send_to_panel(
                websocket,
                {"event": "resume_result", "ok": False, "error": "unauthorized"},
            )
            return None
        user_info = {"id": user.id, "username": user.username, "role": user.role}

    await send_to_panel(
        websocket,
        {"event": "resume_result", "ok": True, "user": user_info},
    )
    return user_info


async def wait_for_panel_auth(websocket) -> Optional[dict]:
    """Espera login/resume; cierra la conexión si no se autentica a tiempo."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.PANEL_AUTH_TIMEOUT

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            await send_to_panel(
                websocket,
                {"event": "auth_required", "message": "Sesión no autenticada"},
            )
            return None

        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            await send_to_panel(
                websocket,
                {"event": "auth_required", "message": "Sesión no autenticada"},
            )
            return None
        except Exception:
            return None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            await send_to_panel(websocket, {"event": "error", "code": "invalid_json"})
            continue

        event = str(data.get("event") or "")
        if event == "login":
            user = await _login(websocket, data)
        elif event == "resume":
            user = await _resume(websocket, data)
        else:
            await send_to_panel(
                websocket,
                {"event": "error", "code": "unauthorized", "message": "Inicia sesión primero"},
            )
            continue

        if user:
            return user


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------
async def send_full_sync(websocket) -> None:
    async with get_db() as session:
        result = await session.execute(select(Device).order_by(Device.created_at))
        devices = result.scalars().all()

        device_list = []
        for dev in devices:
            cfg_res = await session.execute(
                select(TankConfig).where(TankConfig.device_id == dev.id)
            )
            cfg = cfg_res.scalar_one_or_none()

            net_res = await session.execute(
                select(DeviceNetwork)
                .where(DeviceNetwork.device_id == dev.id)
                .order_by(DeviceNetwork.priority)
            )
            networks = net_res.scalars().all()

            cached = server_state.telemetry_cache.get(dev.id)
            device_list.append(
                {
                    "id": dev.id,
                    "name": dev.name,
                    "location": dev.location,
                    "firmware_version": dev.firmware_version,
                    "claimed": dev.status == "CLAIMED",
                    "status": dev.status,
                    "owner_id": dev.owner_id,
                    "online": dev.id in server_state.device_sockets,
                    "last_seen": dev.last_seen.isoformat() if dev.last_seen else None,
                    "rssi": dev.last_rssi,
                    "ip": dev.last_ip,
                    "wake_reason": dev.wake_reason,
                    "capacity": cfg.capacity_liters if cfg else 50.0,
                    "bottomDist": cfg.bottom_dist_mm if cfg else 900.0,
                    "mirrorDist": cfg.mirror_dist_mm if cfg else 100.0,
                    "minLevel": cfg.min_level_percent if cfg else 25.0,
                    "maxLevel": cfg.max_level_percent if cfg else 90.0,
                    "autoRefill": cfg.auto_refill if cfg else True,
                    "currentDist": cached["distance_mm"] if cached else None,
                    "waterPercent": cached["percent"] if cached else None,
                    "waterLiters": cached["liters"] if cached else None,
                    "relayState": cached["relay_state"] if cached else False,
                    "networks": [n.to_dict() for n in networks],
                }
            )

    await send_to_panel(websocket, {"event": "sync_all", "devices": device_list})


async def _broadcast_sync() -> None:
    for ws in list(server_state.panel_sockets):
        try:
            await send_full_sync(ws)
        except Exception:
            server_state.unregister_panel(ws)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------
async def _handle_claim(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    if user.get("role") != "admin":
        await send_error(websocket, request_id, "forbidden", "Solo un administrador puede vincular")
        return

    device_id = str(data.get("device_id") or "").strip()
    password = str(data.get("password") or "")
    name = str(data.get("name") or "").strip()

    if not device_id or len(password) < 16:
        await send_error(
            websocket,
            request_id,
            "invalid_params",
            "device_id y contraseña de al menos 16 caracteres son obligatorios",
        )
        return

    device_ws = server_state.device_socket_for_challenge(device_id)
    if device_ws is None:
        await send_error(
            websocket,
            request_id,
            "device_offline",
            "El dispositivo debe estar online para verificar el secreto",
        )
        return

    # Reemplaza cualquier challenge pendiente y lo asocia al claim.
    nonce = server_state.new_challenge(device_ws, "claim")
    future = asyncio.get_running_loop().create_future()
    server_state.claim_attempts[device_id] = {
        "nonce": nonce,
        "expected_hash": hash_credentials(device_id, password),
        "future": future,
        "panel_ws": websocket,
        "user": user,
        "expires": asyncio.get_running_loop().time() + 30,
        "name": name,
    }

    sent = await server_state.send_to_device(
        device_id,
        {"event": "challenge", "nonce": nonce, "expires_in": 30, "purpose": "claim"},
    )
    if not sent:
        server_state.claim_attempts.pop(device_id, None)
        await send_error(websocket, request_id, "device_offline")
        return

    try:
        result = await asyncio.wait_for(future, timeout=15.0)
    except asyncio.TimeoutError:
        server_state.claim_attempts.pop(device_id, None)
        await send_error(websocket, request_id, "timeout", "El dispositivo no respondió a tiempo")
        return

    if not result.get("ok"):
        await send_error(
            websocket,
            request_id,
            result.get("error", "invalid_credentials"),
            "El secreto no coincide con el dispositivo",
        )
        return

    if name:
        async with get_db() as session:
            dev = (
                await session.execute(select(Device).where(Device.id == device_id))
            ).scalar_one_or_none()
            if dev:
                dev.name = name[:128]
                await session.commit()

    await send_to_panel(
        websocket,
        {
            "event": "claim_result",
            "request_id": request_id,
            "status": "success",
            "device_id": device_id,
        },
    )
    await _broadcast_sync()


# ---------------------------------------------------------------------------
# Configuración del tanque
# ---------------------------------------------------------------------------
async def _handle_update_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    device_id = str(data.get("device_id") or "")
    cfg_data = data.get("config") or {}
    if not isinstance(cfg_data, dict):
        await send_error(websocket, request_id, "invalid_params")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    try:
        capacity = float(cfg_data.get("capacity", 50.0))
        bottom = float(cfg_data.get("bottom_dist_mm", 900.0))
        mirror = float(cfg_data.get("mirror_dist_mm", 100.0))
        min_level = float(cfg_data.get("min_level", 25.0))
        max_level = float(cfg_data.get("max_level", 90.0))
        auto_refill = bool(cfg_data.get("auto_refill", True))
    except (TypeError, ValueError):
        await send_error(websocket, request_id, "invalid_params", "Valores numéricos inválidos")
        return

    if not (0.1 <= capacity <= 100000):
        await send_error(websocket, request_id, "invalid_params", "Capacidad inválida")
        return
    if not (10 <= bottom <= 12000):
        await send_error(websocket, request_id, "invalid_params", "Distancia de fondo inválida")
        return
    if not (0 <= mirror < bottom):
        await send_error(websocket, request_id, "invalid_params", "Distancia espejo inválida")
        return
    if not (0 <= min_level <= 100 and 0 <= max_level <= 100 and min_level < max_level):
        await send_error(websocket, request_id, "invalid_params", "Niveles inválidos")
        return

    async with get_db() as session:
        result = await session.execute(select(TankConfig).where(TankConfig.device_id == device_id))
        cfg = result.scalar_one_or_none()
        if cfg is None:
            cfg = TankConfig(device_id=device_id)
            session.add(cfg)

        cfg.capacity_liters = capacity
        cfg.bottom_dist_mm = bottom
        cfg.mirror_dist_mm = mirror
        cfg.min_level_percent = min_level
        cfg.max_level_percent = max_level
        cfg.auto_refill = auto_refill
        await session.commit()

    await record_audit(
        "CONFIG_UPDATED",
        device_id=device_id,
        actor=user.get("username", "USER"),
        details=f"capacity={capacity} bottom={bottom} mirror={mirror} min={min_level} max={max_level} auto={auto_refill}",
    )
    await send_ack(websocket, request_id, True)
    await _broadcast_sync()


# ---------------------------------------------------------------------------
# Control directo
# ---------------------------------------------------------------------------
async def _handle_relay(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    device_id = str(data.get("device_id") or "")
    state_value = bool(data.get("state", False))
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    result = await request_device(
        websocket,
        user,
        device_id,
        {"command": "set_relay", "state": state_value, "request_id": request_id},
    )
    ok = bool(result.get("ok", False))
    if ok:
        await record_audit(
            "MANUAL_RELAY",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"state={state_value}",
        )
    await send_ack(websocket, result.get("request_id", request_id), ok, result.get("error", ""))


async def _handle_display(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    device_id = str(data.get("device_id") or "")
    line0 = str(data.get("line0") or "")[:16]
    line1 = str(data.get("line1") or "")[:16]
    clear = bool(data.get("clear", False))
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    result = await request_device(
        websocket,
        user,
        device_id,
        {"command": "display", "line0": line0, "line1": line1, "clear": clear, "request_id": request_id},
    )
    ok = bool(result.get("ok", False))
    if ok:
        await record_audit(
            "MANUAL_DISPLAY",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"l0={line0} l1={line1}",
        )
    await send_ack(websocket, result.get("request_id", request_id), ok, result.get("error", ""))


async def _handle_delete_device(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    if user.get("role") != "admin":
        await send_error(websocket, request_id, "forbidden")
        return
    device_id = str(data.get("device_id") or "")
    async with get_db() as session:
        await session.execute(delete(Device).where(Device.id == device_id))
        await session.commit()
    server_state.unregister_device(device_id)
    await record_audit("DEVICE_DELETED", device_id=device_id, actor=user.get("username", "USER"))
    await send_ack(websocket, request_id, True)
    await _broadcast_sync()


async def _handle_audit(websocket, data: dict, request_id: Optional[str]) -> None:
    action_filter = str(data.get("action") or "").strip()
    device_filter = str(data.get("device_id") or "").strip()

    async with get_db() as session:
        query = select(AuditLog).order_by(AuditLog.id.desc()).limit(250)
        if action_filter:
            query = query.where(AuditLog.action.like(f"{action_filter}%"))
        if device_filter:
            query = query.where(AuditLog.device_id == device_filter)
        result = await session.execute(query)
        logs = [entry.to_dict() for entry in result.scalars().all()]

    await send_to_panel(
        websocket,
        {"event": "audit_result", "request_id": request_id, "entries": logs},
    )


# ---------------------------------------------------------------------------
# Router de mensajes del panel
# ---------------------------------------------------------------------------
async def handle_panel_message(websocket, raw_message: str) -> None:
    user = server_state.panel_user(websocket)
    if user is None:
        await send_error(websocket, None, "unauthorized")
        return

    try:
        data = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        await send_error(websocket, None, "invalid_json")
        return
    if not isinstance(data, dict):
        return

    event = str(data.get("event") or "")
    command = str(data.get("command") or "")
    request_id = data.get("request_id")
    device_id = str(data.get("device_id") or "")

    try:
        if event == "ping":
            await send_to_panel(websocket, {"event": "pong"})
        elif event == "claim_device":
            await _handle_claim(user, websocket, data, request_id)
        elif event == "update_config":
            await _handle_update_config(user, websocket, data, request_id)
        elif event == "wifi_list":
            await handle_wifi_list(user, websocket, device_id, request_id)
        elif event == "wifi_add":
            await handle_wifi_add(
                user, websocket, device_id, request_id,
                str(data.get("ssid") or ""), str(data.get("password") or ""),
            )
        elif event == "wifi_remove":
            await handle_wifi_remove(user, websocket, device_id, request_id, str(data.get("ssid") or ""))
        elif event == "wifi_reorder":
            await handle_wifi_reorder(
                user, websocket, device_id, request_id,
                str(data.get("ssid") or ""), data.get("index", 0),
            )
        elif event == "device_action":
            await handle_device_action(
                user, websocket, device_id, request_id,
                str(data.get("action") or ""), data,
            )
        elif event == "system_action":
            await handle_system_action(
                user, websocket, request_id,
                str(data.get("target") or ""), str(data.get("action") or ""),
            )
        elif event == "delete_device":
            await _handle_delete_device(user, websocket, data, request_id)
        elif event == "get_audit":
            await _handle_audit(websocket, data, request_id)
        elif command == "set_relay":
            await _handle_relay(user, websocket, data, request_id)
        elif command == "display":
            await _handle_display(user, websocket, data, request_id)
        elif event == "sync":
            await send_full_sync(websocket)
        else:
            await send_error(websocket, request_id, "invalid_params", "Evento no soportado")
    except Exception:
        logger.exception("Error procesando mensaje de panel")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
