"""History service: historial de telemetría por dispositivo."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.services import db_service

logger = logging.getLogger("DispWatter.HistoryService")


async def get_telemetry_history(
    device_id: str,
    period: str = "24h",
    limit: int = 500,
) -> Dict[str, Any]:
    """Get telemetry history for a device with date filtering.
    
    Args:
        device_id: The device ID.
        period: Time period string: "24h", "7d", "30d", or "all".
        limit: Max number of records to return.
    
    Returns:
        Dict with entries and stats.
    """
    now = datetime.now(timezone.utc)
    
    if period == "24h":
        start = now - timedelta(hours=24)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        start = None
    
    entries = await db_service.get_telemetry_history(
        device_id=device_id,
        start=start,
        end=now,
        limit=limit,
    )
    
    stats = await db_service.get_telemetry_stats(
        device_id=device_id,
        start=start,
        end=now,
    )
    
    return {
        "device_id": device_id,
        "period": period,
        "entries": entries,
        "stats": stats,
    }


async def get_telemetry_stats(
    device_id: str, period: str = "24h"
) -> Dict[str, Any]:
    """Get telemetry statistics for a device.
    
    Args:
        device_id: The device ID.
        period: Time period string.
    
    Returns:
        Dict with min, max, avg stats.
    """
    now = datetime.now(timezone.utc)
    
    if period == "24h":
        start = now - timedelta(hours=24)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        start = None
    
    return await db_service.get_telemetry_stats(
        device_id=device_id,
        start=start,
        end=now,
    )
