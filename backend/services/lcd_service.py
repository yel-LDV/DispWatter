"""LCD service: configuración del LCD por dispositivo."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from backend.database.models import LcdConfig
from backend.handlers.state import server_state
from backend.services import db_service

logger = logging.getLogger("DispWatter.LcdService")

VALID_FORMATS = {"percent", "liters", "distance", "pump_status", "custom", "empty"}
VALID_DISTANCE_UNITS = {"cm", "mm", "m"}


async def get_lcd_config(device_id: str) -> Dict[str, Any]:
    """Get LCD config for a device, creating defaults if not exists.
    
    Returns:
        Dict with LCD config values.
    """
    cfg = await db_service.get_lcd_config(device_id)
    if cfg is None:
        # Create default config
        cfg = await db_service.upsert_lcd_config(device_id)
    
    return cfg.to_dict()


async def update_lcd_config(
    device_id: str,
    data: Dict[str, Any]
) -> Tuple[bool, str]:
    """Update LCD config for a device.
    
    Args:
        device_id: The device ID.
        data: Dict with config fields to update.
    
    Returns:
        (success, message) tuple.
    """
    # Validate formats
    line0_format = str(data.get("line0_format") or "").strip()
    line1_format = str(data.get("line1_format") or "").strip()
    
    if line0_format and line0_format not in VALID_FORMATS:
        return False, f"Formato línea 0 inválido. Usa: {', '.join(VALID_FORMATS)}"
    if line1_format and line1_format not in VALID_FORMATS:
        return False, f"Formato línea 1 inválido. Usa: {', '.join(VALID_FORMATS)}"
    
    # Validate distance unit
    distance_unit = str(data.get("distance_unit") or "").strip()
    if distance_unit and distance_unit not in VALID_DISTANCE_UNITS:
        return False, f"Unidad de distancia inválida. Usa: {', '.join(VALID_DISTANCE_UNITS)}"
    
    # Validate scroll speed
    scroll_speed = data.get("scroll_speed")
    if scroll_speed is not None:
        scroll_speed = int(scroll_speed)
        if not (100 <= scroll_speed <= 500):
            return False, "Velocidad de scroll debe estar entre 100 y 500 ms"
    
    # Validate scroll pause
    scroll_pause = data.get("scroll_pause")
    if scroll_pause is not None:
        scroll_pause = int(scroll_pause)
        if not (1 <= scroll_pause <= 10):
            return False, "Pausa de scroll debe estar entre 1 y 10 segundos"
    
    try:
        cfg = await db_service.upsert_lcd_config(
            device_id=device_id,
            line0_format=line0_format or None,
            line1_format=line1_format or None,
            scroll_speed=scroll_speed,
            scroll_pause=scroll_pause,
            distance_unit=distance_unit or None,
            custom_text0=str(data.get("custom_text0") or "")[:64] or None,
            custom_text1=str(data.get("custom_text1") or "")[:64] or None,
            show_scroll0=data.get("show_scroll0"),
            show_scroll1=data.get("show_scroll1"),
        )
        
        # Sync to device if online
        await sync_lcd_config_to_device(device_id)
        
        logger.info("Config LCD actualizada para dispositivo %s", device_id)
        return True, "Configuración LCD actualizada"
    except Exception as e:
        logger.error("Error actualizando config LCD: %s", e)
        return False, f"Error: {e}"


async def sync_lcd_config_to_device(device_id: str) -> bool:
    """Send LCD config to the device via WebSocket.
    
    Returns:
        True if sent successfully, False otherwise.
    """
    cfg = await db_service.get_lcd_config(device_id)
    if cfg is None:
        return False
    
    device_ws = server_state.device_socket_for_challenge(device_id)
    if device_ws is None:
        return False
    
    config_data = cfg.to_dict()
    sent = await server_state.send_to_device(
        device_id,
        {"event": "lcd_config", "config": config_data},
    )
    
    if sent:
        logger.info("Config LCD sincronizada al dispositivo %s", device_id)
    
    return sent


async def get_default_lcd_config() -> Dict[str, Any]:
    """Return the default LCD config values."""
    return {
        "line0_format": "percent",
        "line1_format": "liters",
        "scroll_speed": 200,
        "scroll_pause": 3,
        "distance_unit": "cm",
        "custom_text0": None,
        "custom_text1": None,
        "show_scroll0": True,
        "show_scroll1": True,
    }
