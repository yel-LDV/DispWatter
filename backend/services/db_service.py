from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import (
    AuditLog,
    Device,
    DeviceNetwork,
    TankConfig,
    Telemetry,
    User,
)
from backend.security.auth import record_audit

logger = logging.getLogger("DispWatter.DBService")


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

async def get_device(device_id: str) -> Optional[Device]:
    async with get_db() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()


async def get_device_in_session(session, device_id: str) -> Optional[Device]:
    result = await session.execute(select(Device).where(Device.id == device_id))
    return result.scalar_one_or_none()


async def ensure_device(
    device_id: str,
    name: str,
    location: str,
    firmware: str,
) -> Device:
    async with get_db() as session:
        device = await get_device_in_session(session, device_id)
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


async def ensure_device_in_session(
    session,
    device_id: str,
    name: str,
    location: str,
    firmware: str,
) -> Device:
    device = await get_device_in_session(session, device_id)
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


async def update_device_online(device_id: str, is_online: bool) -> None:
    async with get_db() as session:
        await session.execute(
            update(Device)
            .where(Device.id == device_id)
            .values(is_online=is_online, last_seen=datetime.utcnow())
        )
        await session.commit()


async def update_device_fields(
    device_id: str,
    *,
    is_online: Optional[bool] = None,
    last_seen: Optional[datetime] = None,
    last_ip: Optional[str] = None,
    last_rssi: Optional[int] = None,
    wake_reason: Optional[str] = None,
    name: Optional[str] = None,
    location: Optional[str] = None,
    firmware_version: Optional[str] = None,
    key_hash: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> None:
    async with get_db() as session:
        device = await get_device_in_session(session, device_id)
        if device is None:
            return
        if is_online is not None:
            device.is_online = is_online
        if last_seen is not None:
            device.last_seen = last_seen
        if last_ip is not None:
            device.last_ip = last_ip
        if last_rssi is not None:
            device.last_rssi = last_rssi
        if wake_reason is not None:
            device.wake_reason = wake_reason
        if name is not None:
            device.name = name
        if location is not None:
            device.location = location
        if firmware_version is not None:
            device.firmware_version = firmware_version
        if key_hash is not None:
            device.key_hash = key_hash
        if status is not None:
            device.status = status
        if owner_id is not None:
            device.owner_id = owner_id
        await session.commit()


async def update_device_fields_in_session(
    session,
    device: Device,
    *,
    is_online: Optional[bool] = None,
    last_seen: Optional[datetime] = None,
    last_ip: Optional[str] = None,
    last_rssi: Optional[int] = None,
    wake_reason: Optional[str] = None,
    name: Optional[str] = None,
    location: Optional[str] = None,
    firmware_version: Optional[str] = None,
    key_hash: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> None:
    if is_online is not None:
        device.is_online = is_online
    if last_seen is not None:
        device.last_seen = last_seen
    if last_ip is not None:
        device.last_ip = last_ip
    if last_rssi is not None:
        device.last_rssi = last_rssi
    if wake_reason is not None:
        device.wake_reason = wake_reason
    if name is not None:
        device.name = name
    if location is not None:
        device.location = location
    if firmware_version is not None:
        device.firmware_version = firmware_version
    if key_hash is not None:
        device.key_hash = key_hash
    if status is not None:
        device.status = status
    if owner_id is not None:
        device.owner_id = owner_id
    await session.commit()


async def delete_device(device_id: str) -> None:
    async with get_db() as session:
        await session.execute(delete(Device).where(Device.id == device_id))
        await session.commit()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

async def get_user_by_username(username: str) -> Optional[User]:
    async with get_db() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: str) -> Optional[User]:
    async with get_db() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def update_user_last_login(user_id: str) -> None:
    async with get_db() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.utcnow())
        )
        await session.commit()


# ---------------------------------------------------------------------------
# TankConfig
# ---------------------------------------------------------------------------

async def get_tank_config(device_id: str) -> Optional[TankConfig]:
    async with get_db() as session:
        result = await session.execute(
            select(TankConfig).where(TankConfig.device_id == device_id)
        )
        return result.scalar_one_or_none()


async def get_tank_config_in_session(session, device_id: str) -> Optional[TankConfig]:
    result = await session.execute(
        select(TankConfig).where(TankConfig.device_id == device_id)
    )
    return result.scalar_one_or_none()


async def update_tank_config(
    device_id: str,
    *,
    capacity_liters: Optional[float] = None,
    bottom_dist_mm: Optional[float] = None,
    mirror_dist_mm: Optional[float] = None,
    min_level_percent: Optional[float] = None,
    max_level_percent: Optional[float] = None,
    auto_refill: Optional[bool] = None,
) -> None:
    async with get_db() as session:
        cfg = await get_tank_config_in_session(session, device_id)
        if cfg is None:
            cfg = TankConfig(device_id=device_id)
            session.add(cfg)
        if capacity_liters is not None:
            cfg.capacity_liters = capacity_liters
        if bottom_dist_mm is not None:
            cfg.bottom_dist_mm = bottom_dist_mm
        if mirror_dist_mm is not None:
            cfg.mirror_dist_mm = mirror_dist_mm
        if min_level_percent is not None:
            cfg.min_level_percent = min_level_percent
        if max_level_percent is not None:
            cfg.max_level_percent = max_level_percent
        if auto_refill is not None:
            cfg.auto_refill = auto_refill
        await session.commit()


async def update_tank_config_in_session(
    session,
    device_id: str,
    *,
    capacity_liters: Optional[float] = None,
    bottom_dist_mm: Optional[float] = None,
    mirror_dist_mm: Optional[float] = None,
    min_level_percent: Optional[float] = None,
    max_level_percent: Optional[float] = None,
    auto_refill: Optional[bool] = None,
) -> TankConfig:
    cfg = await get_tank_config_in_session(session, device_id)
    if cfg is None:
        cfg = TankConfig(device_id=device_id)
        session.add(cfg)
    if capacity_liters is not None:
        cfg.capacity_liters = capacity_liters
    if bottom_dist_mm is not None:
        cfg.bottom_dist_mm = bottom_dist_mm
    if mirror_dist_mm is not None:
        cfg.mirror_dist_mm = mirror_dist_mm
    if min_level_percent is not None:
        cfg.min_level_percent = min_level_percent
    if max_level_percent is not None:
        cfg.max_level_percent = max_level_percent
    if auto_refill is not None:
        cfg.auto_refill = auto_refill
    await session.commit()
    return cfg


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

async def save_telemetry(
    device_id: str,
    distance_mm: float,
    water_percent: float,
    water_liters: float,
    relay_state: bool,
) -> None:
    async with get_db() as session:
        session.add(
            Telemetry(
                device_id=device_id,
                distance_mm=distance_mm,
                water_percent=water_percent,
                water_liters=water_liters,
                relay_state=relay_state,
            )
        )
        await session.commit()


async def cleanup_old_telemetry(retention_hours: int) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
    async with get_db() as session:
        await session.execute(
            delete(Telemetry).where(Telemetry.created_at < cutoff)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# DeviceNetwork
# ---------------------------------------------------------------------------

async def get_device_networks(device_id: str) -> List[DeviceNetwork]:
    async with get_db() as session:
        result = await session.execute(
            select(DeviceNetwork)
            .where(DeviceNetwork.device_id == device_id)
            .order_by(DeviceNetwork.priority)
        )
        return result.scalars().all()


async def update_device_networks(device_id: str, networks: list) -> None:
    async with get_db() as session:
        await session.execute(
            delete(DeviceNetwork).where(DeviceNetwork.device_id == device_id)
        )
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


# ---------------------------------------------------------------------------
# Full sync data
# ---------------------------------------------------------------------------

async def get_all_devices_for_sync() -> List[Dict[str, Any]]:
    """Returns all devices with config and networks for panel sync.
    Callers must merge telemetry_cache and server_state data."""
    from backend.handlers.state import server_state

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
                    "maxWaterHeightMm": (
                        (cfg.bottom_dist_mm - cfg.mirror_dist_mm) if cfg else 800.0
                    ),
                    "currentDist": cached["distance_mm"] if cached else None,
                    "waterPercent": cached["percent"] if cached else None,
                    "waterLiters": cached["liters"] if cached else None,
                    "waterHeightMm": cached.get("height_mm") if cached else None,
                    "relayState": cached["relay_state"] if cached else False,
                    "autoPaused": bool(
                        (cfg.auto_refill if cfg else True) and server_state.is_on_hold(dev.id)
                    ),
                    "networks": [n.to_dict() for n in networks],
                }
            )

    return device_list


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

async def get_audit_logs(
    action_filter: str = "",
    device_filter: str = "",
    limit: int = 250,
) -> List[Dict[str, Any]]:
    async with get_db() as session:
        query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if action_filter:
            query = query.where(AuditLog.action.like(f"{action_filter}%"))
        if device_filter:
            query = query.where(AuditLog.device_id == device_filter)
        result = await session.execute(query)
        return [entry.to_dict() for entry in result.scalars().all()]


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

async def mark_all_devices_offline() -> None:
    async with get_db() as session:
        await session.execute(update(Device).values(is_online=False))
        await session.commit()
