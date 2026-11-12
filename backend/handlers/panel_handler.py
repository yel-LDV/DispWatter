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
        try:
            await worker_pool.submit(
                "panel",
                "update_device_name",
                device_id=device_id,
                name=name[:128],
            )
        except Exception:
            logger.exception("Error actualizando nombre del dispositivo")

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
