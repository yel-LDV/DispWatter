from __future__ import annotations

import asyncio
import json
import logging
import secrets
import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import Device, TankConfig
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
from backend.services import db_service
from backend.workers.thread_pool import worker_pool

logger = logging.getLogger("DispWatter.Panel")

# Altura útil mínima del tanque (fondo - espejo máximo) y separación mínima
# entre nivel mínimo y máximo. El HC-SR04 no lee bien por debajo de ~20 mm.
MIN_USABLE_HEIGHT_MM = 20.0
MIN_LEVEL_GAP = 5.0
SENSOR_BLIND_ZONE_MM = 20.0

# Calibración: muestras necesarias y dispersión máxima admitida (mm).
CALIBRATION_MIN_SAMPLES = 3
CALIBRATION_MAX_SPREAD_MM = 15.0


# ---------------------------------------------------------------------------
# Autenticación del panel
# ---------------------------------------------------------------------------

async def _do_login(username: str, password: str) -> dict:
    """Login directo sin worker pool — consulta simple de DB."""
    from backend.security.auth import verify_password
    user = await db_service.get_user_by_username(username)
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        return {"ok": False, "error": "unauthorized"}
    if not user.is_verified:
        return {"ok": False, "error": "not_verified"}
    await db_service.update_user_last_login(user.id)
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }


async def _do_resume(user_id: str) -> dict:
    """Resume directo sin worker pool — consulta simple de DB."""
    user = await db_service.get_user_by_id(user_id)
    if user is None or not user.is_active:
        return {"ok": False, "error": "unauthorized"}
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }


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
        await send_to_panel(
            websocket,
            {"event": "login_result", "ok": False, "error": "unauthorized",
             "message": "Usuario o contraseña incorrectos"},
        )
        return None

    # Login directo sin worker pool: es una consulta simple de DB.
    # Evita el overhead de crear un event loop en un thread.
    try:
        result = await _do_login(username, password)
    except asyncio.TimeoutError:
        logger.warning("Login tardó más de 5 s para %s", username)
        result = {"ok": False, "error": "timeout"}
    except Exception:
        logger.exception("Error en login")
        result = {"ok": False, "error": "internal_error"}

    if not result.get("ok"):
        limiter.register_failure(ip)
        error = result.get("error", "unauthorized")
        if error == "not_verified":
            await send_to_panel(
                websocket,
                {"event": "login_result", "ok": False, "error": "not_verified",
                 "message": "Cuenta no verificada. Revisa tu correo o solicita un nuevo email de verificación."},
            )
        elif error == "timeout":
            await send_to_panel(
                websocket,
                {"event": "login_result", "ok": False, "error": "timeout",
                 "message": "El servidor tardó demasiado. Inténtalo de nuevo."},
            )
        else:
            await send_to_panel(
                websocket,
                {"event": "login_result", "ok": False, "error": "unauthorized",
                 "message": "Usuario o contraseña incorrectos"},
            )
        await record_audit("LOGIN_FAILED", actor=username or "?", details=f"IP={ip}")
        return None

    user_info = result["user"]
    limiter.reset(ip)
    token = create_token(user_info["id"], user_info["role"])
    await send_to_panel(
        websocket,
        {"event": "login_result", "ok": True, "token": token, "user": user_info},
    )
    # Auditoría en background para no retrasar la respuesta al panel
    asyncio.create_task(
        record_audit("LOGIN_SUCCESS", actor=user_info["username"], details=f"IP={ip}")
    )
    return user_info


async def _resume(websocket, data: dict) -> Optional[dict]:
    payload = decode_token(str(data.get("token") or ""))
    if not payload:
        await send_to_panel(
            websocket,
            {"event": "resume_result", "ok": False, "error": "unauthorized"},
        )
        return None

    # Resume directo sin worker pool: es una consulta simple de DB.
    try:
        result = await _do_resume(payload["sub"])
    except asyncio.TimeoutError:
        logger.warning("Resume tardó más de 5 s para user %s", payload["sub"])
        result = {"ok": False, "error": "timeout"}
    except Exception:
        logger.exception("Error en resume")
        result = {"ok": False, "error": "internal_error"}

    if not result.get("ok"):
        error = result.get("error", "unauthorized")
        message = "Sesión inválida" if error == "unauthorized" else "El servidor tardó demasiado. Inténtalo de nuevo."
        await send_to_panel(
            websocket,
            {"event": "resume_result", "ok": False, "error": error, "message": message},
        )
        return None

    user_info = result["user"]
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
        elif event == "register":
            await _handle_register(websocket, data)
            continue
        elif event == "verify_email":
            await _handle_verify_email(websocket, data)
            continue
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
# Registro y verificación de email
# ---------------------------------------------------------------------------
async def _handle_register(websocket, data: dict) -> None:
    """Handle user registration (pre-auth)."""
    from backend.services.auth_service import register_user

    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    
    if not email or not password:
        await send_to_panel(
            websocket,
            {"event": "register_result", "ok": False, "error": "invalid_params",
             "message": "Correo y contraseña son obligatorios"},
        )
        return
    
    if len(password) < 6:
        await send_to_panel(
            websocket,
            {"event": "register_result", "ok": False, "error": "invalid_params",
             "message": "La contraseña debe tener al menos 6 caracteres"},
        )
        return
    
    success, message = await register_user(email, password)
    await send_to_panel(
        websocket,
        {"event": "register_result", "ok": success, "message": message},
    )


async def _handle_verify_email(websocket, data: dict) -> None:
    """Handle email verification (pre-auth)."""
    from backend.services.auth_service import verify_email

    token = str(data.get("token") or "").strip()
    
    if not token:
        await send_to_panel(
            websocket,
            {"event": "verify_result", "ok": False, "error": "invalid_params",
             "message": "Token de verificación requerido"},
        )
        return
    
    success, message = await verify_email(token)
    await send_to_panel(
        websocket,
        {"event": "verify_result", "ok": success, "message": message},
    )


async def _handle_resend_verification(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Resend verification email for the current user."""
    from backend.services.auth_service import send_verification_email

    if user.get("is_verified", False):
        await send_to_panel(
            websocket,
            {"event": "resend_result", "ok": True, "message": "Tu cuenta ya está verificada"},
        )
        return
    
    success, message = await send_verification_email(user["id"])
    await send_to_panel(
        websocket,
        {"event": "resend_result", "ok": success, "message": message},
    )


# ---------------------------------------------------------------------------
# Permisos por dispositivo
# ---------------------------------------------------------------------------
async def _handle_get_permissions(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Get all permissions for a device."""
    from backend.services import permission_service
    
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    
    perms = await permission_service.get_device_permissions(device_id)
    await send_to_panel(
        websocket,
        {"event": "permissions_result", "request_id": request_id, "permissions": perms},
    )


async def _handle_grant_permission(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Grant a permission to a user on a device."""
    from backend.services import permission_service
    
    device_id = str(data.get("device_id") or "").strip()
    target_email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "viewer").strip()
    
    if not device_id or not target_email:
        await send_error(websocket, request_id, "invalid_params", "device_id y email son requeridos")
        return
    
    # Find user by email
    target_user = await db_service.get_user_by_email(target_email)
    if target_user is None:
        await send_error(websocket, request_id, "not_found", f"No existe usuario con correo {target_email}")
        return
    
    success, message = await permission_service.grant_permission(
        device_id=device_id,
        user_id=target_user.id,
        role=role,
        granted_by=user["id"],
    )
    
    if success:
        await send_ack(websocket, request_id, True)
        await _broadcast_sync()
    else:
        await send_error(websocket, request_id, "permission_error", message)


async def _handle_revoke_permission(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Revoke a permission for a user on a device."""
    from backend.services import permission_service
    
    device_id = str(data.get("device_id") or "").strip()
    target_email = str(data.get("email") or "").strip().lower()
    
    if not device_id or not target_email:
        await send_error(websocket, request_id, "invalid_params", "device_id y email son requeridos")
        return
    
    target_user = await db_service.get_user_by_email(target_email)
    if target_user is None:
        await send_error(websocket, request_id, "not_found", f"No existe usuario con correo {target_email}")
        return
    
    success, message = await permission_service.revoke_permission(
        device_id=device_id,
        user_id=target_user.id,
    )
    
    if success:
        await send_ack(websocket, request_id, True)
        await _broadcast_sync()
    else:
        await send_error(websocket, request_id, "permission_error", message)


# ---------------------------------------------------------------------------
# Historial de telemetría
# ---------------------------------------------------------------------------
async def _handle_get_history(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Get telemetry history for a device."""
    from backend.services.history_service import get_telemetry_history
    
    device_id = str(data.get("device_id") or "").strip()
    period = str(data.get("period") or "24h").strip()
    
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    
    result = await get_telemetry_history(device_id, period=period)
    await send_to_panel(
        websocket,
        {"event": "history_result", "request_id": request_id, **result},
    )


# ---------------------------------------------------------------------------
# Configuración LCD
# ---------------------------------------------------------------------------
async def _handle_get_lcd_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Get LCD config for a device."""
    from backend.services.lcd_service import get_lcd_config
    
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    
    config = await get_lcd_config(device_id)
    await send_to_panel(
        websocket,
        {"event": "lcd_config_result", "request_id": request_id, "config": config},
    )


async def _handle_update_lcd_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Update LCD config for a device."""
    from backend.services.lcd_service import update_lcd_config
    
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    
    config_data = data.get("config") or {}
    success, message = await update_lcd_config(device_id, config_data)
    
    if success:
        await send_ack(websocket, request_id, True)
    else:
        await send_error(websocket, request_id, "lcd_error", message)


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------
async def send_full_sync(websocket) -> None:
    """Enviar sincronización completa al panel.

    Se ejecuta de forma asíncrona (fire-and-forget) para no bloquear
    el login. Si falla, el panel pedirá sync manualmente.
    """
    try:
        result = await asyncio.wait_for(
            worker_pool.submit("panel", "get_all_devices"),
            timeout=5.0,
        )
        device_list = result.get("devices", [])
    except asyncio.TimeoutError:
        logger.warning("Sync tardó más de 5 s; se enviará lista vacía")
        device_list = []
    except Exception:
        logger.exception("Error en sync worker")
        device_list = []

    online_devices = [d for d in device_list if d.get("online", False)]
    all_devices = device_list

    await send_to_panel(websocket, {
        "event": "sync_all",
        "online_devices": online_devices,
        "all_devices": all_devices,
    })


async def _broadcast_sync() -> None:
    for ws in list(server_state.panel_sockets):
        try:
            await send_full_sync(ws)
        except Exception:
            server_state.unregister_panel(ws)


# ---------------------------------------------------------------------------
# Claim con código de 6 dígitos
# ---------------------------------------------------------------------------
async def _handle_start_claim_by_token(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Start claim by token: panel only enters the token, backend finds the device."""
    from backend.services.claim_service import start_claim_by_token
    
    token = str(data.get("token") or "").strip()
    if not token:
        await send_error(websocket, request_id, "invalid_params", "Token requerido")
        return
    
    success, message, device_id = await start_claim_by_token(token, user["id"])
    if success:
        await send_to_panel(
            websocket,
            {"event": "claim_code_sent", "request_id": request_id, "message": message, "device_id": device_id},
        )
    else:
        await send_error(websocket, request_id, "claim_error", message)


async def _handle_start_claim(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Start claim: generate and send 6-digit code to device."""
    from backend.services.claim_service import start_claim
    
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    
    success, message = await start_claim(device_id, user["id"])
    if success:
        await send_to_panel(
            websocket,
            {"event": "claim_code_sent", "request_id": request_id, "message": message},
        )
    else:
        await send_error(websocket, request_id, "claim_error", message)


async def _handle_verify_claim(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Verify the 6-digit claim code and link device to user."""
    from backend.services.claim_service import verify_claim_code
    
    device_id = str(data.get("device_id") or "").strip()
    code = str(data.get("code") or "").strip()
    
    if not device_id or not code:
        await send_error(websocket, request_id, "invalid_params", "device_id y código son requeridos")
        return
    
    success, message = await verify_claim_code(device_id, code, user["id"])
    if success:
        await send_to_panel(
            websocket,
            {"event": "claim_verified", "request_id": request_id, "message": message, "device_id": device_id},
        )
        # Broadcast sync to ALL panels so the newly claimed device appears immediately
        await _broadcast_sync()
        # Also send device_status so panels update real-time status
        await server_state.broadcast_to_panels(
            {"event": "device_status", "device_id": device_id, "is_online": True, "claimed": True}
        )
    else:
        await send_error(websocket, request_id, "claim_error", message)


# Keep old _handle_claim for backward compatibility (admin-only HMAC claim)
async def _handle_claim(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Legacy claim handler — delegates to new code-based flow."""
    await _handle_start_claim(user, websocket, data, request_id)


# ---------------------------------------------------------------------------
# Configuración del tanque
# ---------------------------------------------------------------------------
async def _handle_update_device_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Update device name, location and tank config (including menu_lock). Sends config to ESP32."""
    device_id = str(data.get("device_id") or "")
    name = str(data.get("name") or "").strip()
    location = str(data.get("location") or "").strip()
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
        min_relay_off = float(cfg_data.get("min_relay_off_min", 3.0))
        overflow_protection = bool(cfg_data.get("overflow_protection", True))
        menu_lock = bool(cfg_data.get("menu_lock", False))
        wifi_lock = bool(cfg_data.get("wifi_lock", False))
        device_lock = bool(cfg_data.get("device_lock", False))
        pump_lock = bool(cfg_data.get("pump_lock", False))
        sensor_lock = bool(cfg_data.get("sensor_lock", False))
        firmware_lock = bool(cfg_data.get("firmware_lock", False))
        security_lock = bool(cfg_data.get("security_lock", False))
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
    if bottom - mirror < MIN_USABLE_HEIGHT_MM:
        await send_error(
            websocket, request_id, "invalid_params",
            f"La altura útil (fondo - espejo máximo) debe ser de al menos {MIN_USABLE_HEIGHT_MM:.0f} mm",
        )
        return
    if not (0 <= min_level <= 100 and 0 <= max_level <= 100 and min_level < max_level):
        await send_error(websocket, request_id, "invalid_params", "Niveles inválidos")
        return
    if max_level - min_level < MIN_LEVEL_GAP:
        await send_error(
            websocket, request_id, "invalid_params",
            f"Entre el mínimo y el máximo debe haber al menos {MIN_LEVEL_GAP:.0f} puntos para evitar encendidos continuos",
        )
        return

    async with get_db() as session:
        dev = await session.execute(select(Device).where(Device.id == device_id))
        dev = dev.scalar_one_or_none()
        if dev is None:
            await send_error(websocket, request_id, "not_found", "Dispositivo no encontrado")
            return

        # Update device name and location
        if name:
            dev.name = name
        if location:
            dev.location = location

        # Update or create tank config
        if dev.config is None:
            from backend.database.models import TankConfig
            dev.config = TankConfig(device_id=device_id)
        tc = dev.config
        tc.capacity_liters = capacity
        tc.bottom_dist_mm = bottom
        tc.mirror_dist_mm = mirror
        tc.min_level_percent = min_level
        tc.max_level_percent = max_level
        tc.auto_refill = auto_refill
        tc.min_relay_off_min = min_relay_off
        tc.overflow_protection = overflow_protection
        tc.menu_lock = menu_lock
        tc.wifi_lock = wifi_lock
        tc.device_lock = device_lock
        tc.pump_lock = pump_lock
        tc.sensor_lock = sensor_lock
        tc.firmware_lock = firmware_lock
        tc.security_lock = security_lock

        await session.commit()

    # Clear manual hold when config changes
    server_state.clear_manual_hold(device_id)

    # Send config to ESP32 device — fire-and-forget so the panel doesn't
    # wait 10 s for an ack when the device is offline.
    asyncio.create_task(
        request_device(
            websocket,
            user,
            device_id,
            {
                "command": "update_config",
                "config": {
                    "capacity": capacity,
                    "bottom_dist_mm": bottom,
                    "mirror_dist_mm": mirror,
                    "min_level": min_level,
                    "max_level": max_level,
                    "auto_refill": auto_refill,
                    "min_relay_off_min": min_relay_off,
                    "overflow_protection": overflow_protection,
                    "menu_lock": menu_lock,
                    "wifi_lock": wifi_lock,
                    "device_lock": device_lock,
                    "pump_lock": pump_lock,
                    "sensor_lock": sensor_lock,
                    "firmware_lock": firmware_lock,
                    "security_lock": security_lock,
                },
                "request_id": request_id,
            },
        )
    )

    await record_audit(
        "CONFIG_UPDATED",
        device_id=device_id,
        actor=user.get("username", "USER"),
        details=f"name={name} location={location} capacity={capacity} bottom={bottom} mirror={mirror} min={min_level} max={max_level} auto={auto_refill} min_off={min_relay_off} overflow={overflow_protection} menu_lock={menu_lock}",
    )
    await _broadcast_sync()


async def _handle_get_device_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Get fresh device config from DB for a specific device."""
    device_id = str(data.get("device_id") or "")
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    # Get fresh data from DB
    cfg = await db_service.get_tank_config(device_id)
    cfg_dict = {
        "capacity": cfg.capacity_liters if cfg else 50.0,
        "bottom_dist_mm": cfg.bottom_dist_mm if cfg else 900.0,
        "mirror_dist_mm": cfg.mirror_dist_mm if cfg else 100.0,
        "min_level": cfg.min_level_percent if cfg else 25.0,
        "max_level": cfg.max_level_percent if cfg else 90.0,
        "auto_refill": cfg.auto_refill if cfg else True,
        "min_relay_off_min": cfg.min_relay_off_min if cfg else 3.0,
        "overflow_protection": cfg.overflow_protection if cfg else True,
        "menu_lock": cfg.menu_lock if cfg else False,
        "wifi_lock": cfg.wifi_lock if cfg else False,
        "device_lock": cfg.device_lock if cfg else False,
        "pump_lock": cfg.pump_lock if cfg else False,
        "sensor_lock": cfg.sensor_lock if cfg else False,
        "firmware_lock": cfg.firmware_lock if cfg else False,
        "security_lock": cfg.security_lock if cfg else False,
    }

    await send_to_panel(
        websocket,
        {
            "event": "device_config_result",
            "request_id": request_id,
            "ok": True,
            "device_id": device_id,
            "name": device.name or "",
            "location": device.location or "",
            "config": cfg_dict,
        },
    )


async def _handle_update_config(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Legacy handler — delegates to update_device_config for backward compatibility."""
    wrapped = dict(data)
    wrapped.setdefault("config", {})
    wrapped.setdefault("name", "")
    wrapped.setdefault("location", "")
    await _handle_update_device_config(user, websocket, wrapped, request_id)


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
    actual = result.get("relay_state")
    if not isinstance(actual, bool):
        actual = state_value if ok else None

    if ok:
        # Apagar a mano pausa el llenado automático; si no, el siguiente dato de
        # telemetría (cada 2 s) volvería a encender la bomba bajo el mínimo.
        if state_value:
            server_state.clear_manual_hold(device_id)
        else:
            server_state.set_manual_hold(device_id, settings.MANUAL_HOLD_MINUTES)
        await record_audit(
            "MANUAL_RELAY",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"state={state_value} actual={actual}",
        )

    payload = {
        "event": "ack",
        "request_id": result.get("request_id", request_id),
        "ok": ok,
        "relay_state": actual,
    }
    if not ok and result.get("error"):
        payload["error"] = result["error"]
    await send_to_panel(websocket, payload)


async def _handle_set_auto_refill(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Toggle auto refill for a device via update_config."""
    device_id = str(data.get("device_id") or "")
    auto_refill = bool(data.get("auto_refill", False))
    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    # Update auto_refill in DB
    await db_service.update_tank_config(device_id, auto_refill=auto_refill)

    # Send command to device
    result = await request_device(
        websocket,
        user,
        device_id,
        {"command": "set_auto_refill", "auto_refill": auto_refill, "request_id": request_id},
    )
    ok = bool(result.get("ok", False))

    if ok:
        await record_audit(
            "AUTO_REFILL_CHANGED",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"auto_refill={auto_refill}",
        )

    await send_ack(websocket, request_id, ok, result.get("error", ""))
    await _broadcast_sync()


async def _handle_device_command(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Handle direct device commands: reboot, sleep, factory_reset."""
    device_id = str(data.get("device_id") or "")
    command = str(data.get("command") or "")
    if not command:
        # Fallback: use the event name as the command
        command = str(data.get("event") or "")

    if command not in {"reboot", "sleep", "factory_reset"}:
        await send_error(websocket, request_id, "invalid_params", "Comando desconocido")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    if command == "factory_reset" and user.get("role") != "admin":
        await send_error(websocket, request_id, "forbidden", "Solo un administrador puede resetear")
        return

    cmd_payload = {"command": command, "request_id": request_id}
    if command == "sleep":
        try:
            minutes = int(data.get("minutes", 60))
        except (TypeError, ValueError):
            await send_error(websocket, request_id, "invalid_params", "Minutos inválidos")
            return
        if not 1 <= minutes <= 1440:
            await send_error(websocket, request_id, "invalid_params", "Minutos fuera de rango")
            return
        cmd_payload["minutes"] = minutes

    result = await request_device(
        websocket,
        user,
        device_id,
        cmd_payload,
    )
    ok = bool(result.get("ok", False))
    if ok:
        details = f"command={command}"
        if command == "sleep":
            details += f" minutes={cmd_payload['minutes']}"
        await record_audit(
            f"DEVICE_{command.upper()}",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=details,
        )
    await send_ack(websocket, request_id, ok, result.get("error", ""))


async def _handle_panel_logout(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Logout a panel user by removing their session."""
    server_state.unregister_panel(websocket)
    await send_to_panel(websocket, {"event": "logout_result", "ok": True})


# ---------------------------------------------------------------------------
# Calibración del sensor
# ---------------------------------------------------------------------------
async def _handle_calibrate(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Fija el fondo o el máximo a partir de lecturas reales del sensor.

    point = "bottom": tanque VACÍO -> distancia sensor-fondo (bottom_dist_mm)
    point = "max"   : tanque en su nivel MÁXIMO -> distancia sensor-espejo (mirror_dist_mm)
    """
    device_id = str(data.get("device_id") or "")
    point = str(data.get("point") or "")
    if point not in {"bottom", "max"}:
        await send_error(websocket, request_id, "invalid_params", "Punto de calibración desconocido")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return
    if not server_state.device_is_online(device_id):
        await send_error(websocket, request_id, "device_offline", "El dispositivo debe estar online para calibrar")
        return

    readings = server_state.recent_distances(device_id, max_age=15.0)
    if len(readings) < CALIBRATION_MIN_SAMPLES:
        await send_error(
            websocket, request_id, "invalid_params",
            "Faltan lecturas recientes del sensor; espera unos segundos e inténtalo de nuevo",
        )
        return

    spread = max(readings) - min(readings)
    if spread > CALIBRATION_MAX_SPREAD_MM:
        await send_error(
            websocket, request_id, "invalid_params",
            f"Lectura inestable (variación de {spread:.0f} mm). Espera a que el agua se calme y repite",
        )
        return

    measured = float(statistics.median(readings))
    if measured < SENSOR_BLIND_ZONE_MM:
        await send_error(
            websocket, request_id, "invalid_params",
            f"El agua está dentro de la zona ciega del sensor (< {SENSOR_BLIND_ZONE_MM:.0f} mm)",
        )
        return

    # Obtener config actual para validaciones
    cfg_result = await db_service.get_tank_config(device_id)
    if cfg_result is None:
        cfg_result = TankConfig(device_id=device_id)
        cfg_result.bottom_dist_mm = 900.0
        cfg_result.mirror_dist_mm = 100.0

    if point == "bottom":
        if measured - cfg_result.mirror_dist_mm < MIN_USABLE_HEIGHT_MM:
            await send_error(
                websocket, request_id, "invalid_params",
                "El fondo medido queda demasiado cerca del nivel máximo configurado; "
                "revisa que el tanque esté vacío o calibra primero el máximo",
            )
            return
        bottom_dist_mm = round(measured, 1)
        mirror_dist_mm = cfg_result.mirror_dist_mm
    else:
        if cfg_result.bottom_dist_mm - measured < MIN_USABLE_HEIGHT_MM:
            await send_error(
                websocket, request_id, "invalid_params",
                "El máximo medido queda demasiado cerca del fondo configurado; "
                "revisa que el tanque esté lleno o calibra primero el fondo",
            )
            return
        bottom_dist_mm = cfg_result.bottom_dist_mm
        mirror_dist_mm = round(measured, 1)

    # Guardar en BD vía worker
    try:
        await worker_pool.submit(
            "panel",
            "update_tank_config",
            device_id=device_id,
            bottom_dist_mm=bottom_dist_mm,
            mirror_dist_mm=mirror_dist_mm,
        )
    except Exception:
        logger.exception("Error guardando calibración")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
        return

    sensor_height = bottom_dist_mm
    max_height = bottom_dist_mm - mirror_dist_mm

    await record_audit(
        "CALIBRATION",
        device_id=device_id,
        actor=user.get("username", "USER"),
        details=f"point={point} measured={measured:.1f}mm samples={len(readings)} spread={spread:.1f}mm",
    )
    await send_to_panel(
        websocket,
        {
            "event": "calibrate_result",
            "request_id": request_id,
            "ok": True,
            "point": point,
            "measured_mm": round(measured, 1),
            "samples": len(readings),
            "spread_mm": round(spread, 1),
            "sensor_height_mm": round(sensor_height, 1),
            "max_water_height_mm": round(max_height, 1),
        },
    )
    await _broadcast_sync()


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


async def _handle_add_device(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Add a device manually by ID from the panel."""
    if user.get("role") != "admin":
        await send_error(websocket, request_id, "forbidden")
        return
    device_id = str(data.get("device_id") or "").strip()
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    try:
        result = await worker_pool.submit(
            "panel", "add_device", device_id=device_id, owner_id=user["id"]
        )
    except Exception:
        logger.exception("Error agregando dispositivo")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
        return
    if result.get("ok"):
        await record_audit(
            "DEVICE_MANUAL_ADDED",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"Dispositivo {device_id} agregado manualmente.",
        )
        await send_ack(websocket, request_id, True)
        await _broadcast_sync()
    else:
        error = result.get("error", "unknown")
        message = result.get("message", "Error desconocido")
        await send_error(websocket, request_id, error, message)


async def _handle_delete_device(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    if user.get("role") != "admin":
        await send_error(websocket, request_id, "forbidden")
        return
    device_id = str(data.get("device_id") or "")
    try:
        await worker_pool.submit("panel", "delete_device", device_id=device_id)
    except Exception:
        logger.exception("Error eliminando dispositivo")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
        return
    server_state.unregister_device(device_id)
    await record_audit("DEVICE_DELETED", device_id=device_id, actor=user.get("username", "USER"))
    await send_ack(websocket, request_id, True)
    await _broadcast_sync()


async def _handle_release_device(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Release a device: reset to PENDING_CLAIM so it can be re-claimed with the same token.
    Unlike delete, this preserves device history, telemetry, and config."""
    device_id = str(data.get("device_id") or "")
    if not device_id:
        await send_error(websocket, request_id, "invalid_params", "device_id requerido")
        return
    try:
        await worker_pool.submit("panel", "release_device", device_id=device_id)
    except Exception:
        logger.exception("Error liberando dispositivo")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
        return
    server_state.unregister_device(device_id)
    await record_audit("DEVICE_RELEASED", device_id=device_id, actor=user.get("username", "USER"),
                       details="Dispositivo liberado para re-vinculación")
    await send_ack(websocket, request_id, True)
    await _broadcast_sync()


async def _handle_audit(websocket, data: dict, request_id: Optional[str]) -> None:
    action_filter = str(data.get("action") or "").strip()
    device_filter = str(data.get("device_id") or "").strip()
    user_filter = str(data.get("actor") or "").strip()

    try:
        result = await worker_pool.submit(
            "panel",
            "get_audit_logs",
            action_filter=action_filter,
            device_filter=device_filter,
        )
        logs = result.get("entries", [])
    except Exception:
        logger.exception("Error obteniendo audit logs")
        logs = []

    if user_filter:
        logs = [l for l in logs if l.get("actor", "").lower() == user_filter.lower()]

    await send_to_panel(
        websocket,
        {"event": "audit_result", "request_id": request_id, "entries": logs},
    )


# ---------------------------------------------------------------------------
# Cambio de contraseña
# ---------------------------------------------------------------------------
async def _handle_change_password(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Change user password."""
    from backend.services.auth_service import change_password

    # Panel envía "current", el handler original esperaba "old_password"
    old_password = str(data.get("old_password") or data.get("current") or "")
    new_password = str(data.get("new_password") or "")

    if not old_password or not new_password:
        await send_error(websocket, request_id, "invalid_params", "Contraseñas requeridas")
        return

    success, message = await change_password(user["id"], old_password, new_password)
    if success:
        await send_ack(websocket, request_id, True)
        await record_audit(
            "PASSWORD_CHANGED",
            actor=user.get("username", "USER"),
            details="Contraseña actualizada",
        )
    else:
        await send_error(websocket, request_id, "password_error", message)


# ---------------------------------------------------------------------------
# Permisos granulares
# ---------------------------------------------------------------------------
async def _handle_get_granular_permissions(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Get granular permissions for a user on a device."""
    from backend.services import permission_service

    device_id = str(data.get("device_id") or "").strip()
    target_email = str(data.get("email") or "").strip().lower()

    if not device_id or not target_email:
        await send_error(websocket, request_id, "invalid_params", "device_id y email son requeridos")
        return

    target_user = await db_service.get_user_by_email(target_email)
    if target_user is None:
        await send_error(websocket, request_id, "not_found", f"No existe usuario con correo {target_email}")
        return

    perms = await permission_service.get_granular_permissions(device_id, target_user.id)
    await send_to_panel(
        websocket,
        {"event": "granular_permissions_result", "request_id": request_id, "permissions": perms},
    )


async def _handle_set_permission(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Set a single granular permission."""
    from backend.services import permission_service

    device_id = str(data.get("device_id") or "").strip()
    target_email = str(data.get("email") or "").strip().lower()
    permission = str(data.get("permission") or "").strip()
    value = bool(data.get("value", False))

    if not device_id or not target_email or not permission:
        await send_error(websocket, request_id, "invalid_params", "device_id, email y permission son requeridos")
        return

    target_user = await db_service.get_user_by_email(target_email)
    if target_user is None:
        await send_error(websocket, request_id, "not_found", f"No existe usuario con correo {target_email}")
        return

    success, message = await permission_service.set_permission(
        device_id=device_id,
        user_id=target_user.id,
        permission=permission,
        value=value,
    )

    if success:
        await send_ack(websocket, request_id, True)
        await record_audit(
            "PERMISSION_CHANGED",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"{target_email}: {permission}={value}",
        )
    else:
        await send_error(websocket, request_id, "permission_error", message)


async def _handle_set_all_permissions(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Set all granular permissions (master toggle)."""
    from backend.services import permission_service

    device_id = str(data.get("device_id") or "").strip()
    target_email = str(data.get("email") or "").strip().lower()
    all_value = bool(data.get("all_value", False))

    if not device_id or not target_email:
        await send_error(websocket, request_id, "invalid_params", "device_id y email son requeridos")
        return

    target_user = await db_service.get_user_by_email(target_email)
    if target_user is None:
        await send_error(websocket, request_id, "not_found", f"No existe usuario con correo {target_email}")
        return

    all_perms = {field: all_value for field in permission_service.GRANULAR_PERMISSIONS}
    success, message = await permission_service.set_all_permissions(
        device_id=device_id,
        user_id=target_user.id,
        all_permissions=all_perms,
    )

    if success:
        await send_ack(websocket, request_id, True)
        await record_audit(
            "PERMISSIONS_MASTER_CHANGED",
            device_id=device_id,
            actor=user.get("username", "USER"),
            details=f"{target_email}: all={all_value}",
        )
    else:
        await send_error(websocket, request_id, "permission_error", message)


# ---------------------------------------------------------------------------
# OTA Updates
# ---------------------------------------------------------------------------
async def _handle_list_ota_versions(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """List all available firmware versions from GitHub Releases."""
    from backend.services.ota_service import list_versions

    try:
        versions = await list_versions()
    except Exception:
        logger.exception("Error listing OTA versions")
        versions = []

    await send_to_panel(
        websocket,
        {"event": "ota_versions_result", "request_id": request_id, "versions": versions},
    )


async def _handle_start_ota_update(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Start OTA update: download binary and push to device."""
    from backend.services.ota_service import get_version, push_to_device

    device_id = str(data.get("device_id") or "").strip()
    version_tag = str(data.get("version") or "").strip()

    if not device_id or not version_tag:
        await send_error(websocket, request_id, "invalid_params", "device_id y version son requeridos")
        return

    device, error = await authorize_device(user, device_id)
    if error:
        await send_error(websocket, request_id, error)
        return

    if not server_state.device_is_online(device_id):
        await send_error(websocket, request_id, "device_offline", "El dispositivo debe estar online")
        return

    version_info = await get_version(version_tag)
    if not version_info:
        await send_error(websocket, request_id, "not_found", f"Version {version_tag} no encontrada")
        return

    device_ws = server_state.device_socket(device_id)
    if not device_ws:
        await send_error(websocket, request_id, "device_offline", "No se pudo conectar al dispositivo")
        return

    await send_to_panel(
        websocket,
        {"event": "ota_progress", "request_id": request_id, "status": "downloading", "version": version_tag},
    )

    try:
        success = await push_to_device(device_ws, version_tag)
        if success:
            await send_to_panel(
                websocket,
                {"event": "ota_progress", "request_id": request_id, "status": "complete", "version": version_tag},
            )
            await record_audit(
                "OTA_UPDATE",
                device_id=device_id,
                actor=user.get("username", "USER"),
                details=f"version={version_tag}",
            )
        else:
            await send_error(websocket, request_id, "ota_error", "La actualización falló")
    except Exception:
        logger.exception("OTA update failed")
        await send_error(websocket, request_id, "ota_error", "Error durante la actualización")


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
        elif event == "start_claim_by_token":
            await _handle_start_claim_by_token(user, websocket, data, request_id)
        elif event == "start_claim":
            await _handle_start_claim(user, websocket, data, request_id)
        elif event == "verify_claim":
            await _handle_verify_claim(user, websocket, data, request_id)
        elif event == "update_config":
            await _handle_update_config(user, websocket, data, request_id)
        elif event == "update_device_config":
            await _handle_update_device_config(user, websocket, data, request_id)
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
        elif event == "add_device":
            await _handle_add_device(user, websocket, data, request_id)
        elif event == "delete_device":
            await _handle_delete_device(user, websocket, data, request_id)
        elif event == "release_device":
            await _handle_release_device(user, websocket, data, request_id)
        elif event == "get_audit":
            await _handle_audit(websocket, data, request_id)
        elif event == "resend_verification":
            await _handle_resend_verification(user, websocket, data, request_id)
        elif event == "get_permissions":
            await _handle_get_permissions(user, websocket, data, request_id)
        elif event == "grant_permission":
            await _handle_grant_permission(user, websocket, data, request_id)
        elif event == "revoke_permission":
            await _handle_revoke_permission(user, websocket, data, request_id)
        elif event == "get_history":
            await _handle_get_history(user, websocket, data, request_id)
        elif event == "get_lcd_config":
            await _handle_get_lcd_config(user, websocket, data, request_id)
        elif event == "update_lcd_config":
            await _handle_update_lcd_config(user, websocket, data, request_id)
        elif event == "calibrate":
            await _handle_calibrate(user, websocket, data, request_id)
        elif event == "set_relay":
            await _handle_relay(user, websocket, data, request_id)
        elif command == "set_relay":
            await _handle_relay(user, websocket, data, request_id)
        elif event == "set_auto_refill":
            await _handle_set_auto_refill(user, websocket, data, request_id)
        elif event in ("reboot", "sleep", "factory_reset"):
            await _handle_device_command(user, websocket, data, request_id)
        elif event == "logout":
            await _handle_panel_logout(user, websocket, data, request_id)
        elif command == "display":
            await _handle_display(user, websocket, data, request_id)
        elif event == "list_ota_versions":
            await _handle_list_ota_versions(user, websocket, data, request_id)
        elif event == "start_ota_update":
            await _handle_start_ota_update(user, websocket, data, request_id)
        elif event == "change_password":
            await _handle_change_password(user, websocket, data, request_id)
        elif event == "get_device_config":
            await _handle_get_device_config(user, websocket, data, request_id)
        elif event == "get_granular_permissions":
            await _handle_get_granular_permissions(user, websocket, data, request_id)
        elif event == "set_permission":
            await _handle_set_permission(user, websocket, data, request_id)
        elif event == "set_all_permissions":
            await _handle_set_all_permissions(user, websocket, data, request_id)
        elif event == "sync":
            await send_full_sync(websocket)
        elif event == "resume":
            # El panel puede enviar resume después de reconectar.
            # Si ya está autenticado, ignorar; si no, pedir login.
            if user:
                await send_to_panel(
                    websocket,
                    {"event": "resume_result", "ok": True, "user": user},
                )
            else:
                await send_to_panel(
                    websocket,
                    {"event": "resume_result", "ok": False, "error": "unauthorized"},
                )
        else:
            await send_error(websocket, request_id, "invalid_params", "Evento no soportado")
    except Exception:
        logger.exception("Error procesando mensaje de panel")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
