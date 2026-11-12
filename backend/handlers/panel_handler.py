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

    # Usar worker para login
    try:
        result = await worker_pool.submit("panel", "login", username=username, password=password)
    except Exception:
        logger.exception("Error en login worker")
        result = {"ok": False, "error": "internal_error"}

    if not result.get("ok"):
        limiter.register_failure(ip)
        await asyncio.sleep(0.35)
        error = result.get("error", "unauthorized")
        if error == "not_verified":
            await send_to_panel(
                websocket,
                {"event": "login_result", "ok": False, "error": "not_verified",
                 "message": "Cuenta no verificada. Revisa tu correo o solicita un nuevo email de verificación."},
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

    # Usar worker para resume
    try:
        result = await worker_pool.submit("panel", "resume", user_id=payload["sub"])
    except Exception:
        logger.exception("Error en resume worker")
        result = {"ok": False, "error": "internal_error"}

    if not result.get("ok"):
        await send_to_panel(
            websocket,
            {"event": "resume_result", "ok": False, "error": "unauthorized"},
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
    try:
        result = await worker_pool.submit("panel", "get_all_devices")
        device_list = result.get("devices", [])
    except Exception:
        logger.exception("Error en sync worker")
        device_list = []

    await send_to_panel(websocket, {"event": "sync_all", "devices": device_list})


async def _broadcast_sync() -> None:
    for ws in list(server_state.panel_sockets):
        try:
            await send_full_sync(ws)
        except Exception:
            server_state.unregister_panel(ws)


# ---------------------------------------------------------------------------
# Claim con código de 6 dígitos
# ---------------------------------------------------------------------------
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
        await _broadcast_sync()
    else:
        await send_error(websocket, request_id, "claim_error", message)


# Keep old _handle_claim for backward compatibility (admin-only HMAC claim)
async def _handle_claim(user: dict, websocket, data: dict, request_id: Optional[str]) -> None:
    """Legacy claim handler — delegates to new code-based flow."""
    await _handle_start_claim(user, websocket, data, request_id)


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

    # Usar worker para actualizar config
    try:
        await worker_pool.submit(
            "panel",
            "update_tank_config",
            device_id=device_id,
            capacity_liters=capacity,
            bottom_dist_mm=bottom,
            mirror_dist_mm=mirror,
            min_level_percent=min_level,
            max_level_percent=max_level,
            auto_refill=auto_refill,
        )
    except Exception:
        logger.exception("Error actualizando config")
        await send_error(websocket, request_id, "hardware_error", "Error interno")
        return

    # Cambiar la configuración (p. ej. reactivar el automático) levanta la pausa manual.
    server_state.clear_manual_hold(device_id)

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


async def _handle_audit(websocket, data: dict, request_id: Optional[str]) -> None:
    action_filter = str(data.get("action") or "").strip()
    device_filter = str(data.get("device_id") or "").strip()

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
        elif event == "start_claim":
            await _handle_start_claim(user, websocket, data, request_id)
        elif event == "verify_claim":
            await _handle_verify_claim(user, websocket, data, request_id)
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
