from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import joinedload

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import (
    AuditLog,
    Device,
    DeviceNetwork,
    DevicePermission,
    EmailVerification,
    LcdConfig,
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


async def get_device_by_serial(serial_number: str) -> Optional[Device]:
    async with get_db() as session:
        result = await session.execute(select(Device).where(Device.serial_number == serial_number))
        return result.scalar_one_or_none()


async def get_all_serial_numbers() -> List[str]:
    async with get_db() as session:
        result = await session.execute(select(Device.serial_number).where(Device.serial_number.isnot(None)))
        return [row[0] for row in result.all() if row[0]]


async def ensure_device(
    device_id: str,
    name: str,
    location: str,
    firmware: str,
    serial_number: str = "",
) -> Device:
    async with get_db() as session:
        device = await get_device_in_session(session, device_id)
        if device is None:
            device = Device(
                id=device_id,
                name=name or f"Bebedero {device_id}",
                location=location or "Sin ubicación",
                firmware_version=firmware or "1.0.0",
                serial_number=serial_number if serial_number else None,
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
            if serial_number and not device.serial_number:
                device.serial_number = serial_number
            await session.commit()
        return device


async def ensure_device_in_session(
    session,
    device_id: str,
    name: str,
    location: str,
    firmware: str,
    serial_number: str = "",
) -> Device:
    device = await get_device_in_session(session, device_id)
    if device is None:
        device = Device(
            id=device_id,
            name=name or f"Bebedero {device_id}",
            location=location or "Sin ubicación",
            firmware_version=firmware or "1.0.0",
            serial_number=serial_number if serial_number else None,
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
        if serial_number and not device.serial_number:
            device.serial_number = serial_number
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


async def add_device_manual(device_id: str, owner_id: str) -> Dict[str, Any]:
    """Manually add a device by ID from the panel.
    Creates the device in PENDING_CLAIM status and assigns it to the user."""
    async with get_db() as session:
        existing = await get_device_in_session(session, device_id)
        if existing is not None:
            return {"ok": False, "error": "already_exists", "message": f"El dispositivo {device_id} ya existe."}
        device = Device(
            id=device_id,
            name=f"Bebedero {device_id}",
            location="Sin ubicación",
            firmware_version="desconocido",
            serial_number=None,
            key_hash=None,
            owner_id=owner_id,
            status="PENDING_CLAIM",
            is_online=False,
        )
        session.add(device)
        session.add(TankConfig(device_id=device_id))
        await session.commit()
        await session.refresh(device)
        await record_audit(
            "DEVICE_MANUAL_ADD",
            device_id=device_id,
            actor=owner_id,
            details=f"Dispositivo agregado manualmente desde el panel.",
        )
        return {"ok": True, "device_id": device_id}


async def delete_device(device_id: str) -> None:
    async with get_db() as session:
        await session.execute(delete(Device).where(Device.id == device_id))
        await session.commit()


async def release_device(device_id: str) -> None:
    """Release a device: reset to PENDING_CLAIM without deleting.
    Clears key_hash, owner_id, and status so it can be re-claimed with the same token.
    Preserves device history, telemetry, tank config, and LCD config."""
    async with get_db() as session:
        device = await get_device_in_session(session, device_id)
        if device is None:
            return
        device.key_hash = None
        device.status = "PENDING_CLAIM"
        device.owner_id = None
        await session.commit()
        logger.info("Dispositivo %s liberado para re-vinculación", device_id)


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


async def update_user_password(user_id: str, password_hash: str) -> None:
    async with get_db() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash)
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
    min_relay_off_min: Optional[float] = None,
    overflow_protection: Optional[bool] = None,
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
        if min_relay_off_min is not None:
            cfg.min_relay_off_min = min_relay_off_min
        if overflow_protection is not None:
            cfg.overflow_protection = overflow_protection
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
    Uses joinedload to fetch all data in a single query instead of N+1."""
    from backend.handlers.state import server_state

    async with get_db() as session:
        result = await session.execute(
            select(Device)
            .options(
                joinedload(Device.config),
                joinedload(Device.networks),
            )
            .order_by(Device.created_at)
        )
        devices = result.scalars().unique().all()

        device_list = []
        for dev in devices:
            cfg = dev.config
            networks = dev.networks or []
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


# ---------------------------------------------------------------------------
# User extensions
# ---------------------------------------------------------------------------

async def get_user_by_email(email: str) -> Optional[User]:
    async with get_db() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def create_user(
    username: str, email: str, password_hash: str, role: str = "user", is_verified: bool = True
) -> User:
    async with get_db() as session:
        user = User(
            id=f"USR-{secrets.token_hex(8)}",
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            is_verified=is_verified,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def verify_user(user_id: str) -> None:
    async with get_db() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_verified=True)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# EmailVerification
# ---------------------------------------------------------------------------

async def create_email_verification(
    email: str, user_id: str, token: str, expires_at: datetime
) -> EmailVerification:
    async with get_db() as session:
        ev = EmailVerification(
            email=email,
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            used=False,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev


async def get_email_verification(token: str) -> Optional[EmailVerification]:
    async with get_db() as session:
        result = await session.execute(
            select(EmailVerification).where(EmailVerification.token == token)
        )
        return result.scalar_one_or_none()


async def mark_email_verification_used(token: str) -> None:
    async with get_db() as session:
        await session.execute(
            update(EmailVerification)
            .where(EmailVerification.token == token)
            .values(used=True)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# DevicePermission
# ---------------------------------------------------------------------------

async def get_device_permissions(device_id: str) -> List[DevicePermission]:
    async with get_db() as session:
        result = await session.execute(
            select(DevicePermission).where(DevicePermission.device_id == device_id)
        )
        return result.scalars().all()


async def get_device_permission(
    device_id: str, user_id: str
) -> Optional[DevicePermission]:
    async with get_db() as session:
        result = await session.execute(
            select(DevicePermission).where(
                DevicePermission.device_id == device_id,
                DevicePermission.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


async def grant_permission(
    device_id: str, user_id: str, role: str, granted_by: Optional[str] = None
) -> DevicePermission:
    async with get_db() as session:
        existing = await session.execute(
            select(DevicePermission).where(
                DevicePermission.device_id == device_id,
                DevicePermission.user_id == user_id,
            )
        )
        perm = existing.scalar_one_or_none()
        if perm:
            perm.role = role
            perm.granted_by = granted_by
        else:
            perm = DevicePermission(
                device_id=device_id,
                user_id=user_id,
                role=role,
                granted_by=granted_by,
            )
            session.add(perm)
        await session.commit()
        await session.refresh(perm)
        return perm


async def revoke_permission(device_id: str, user_id: str) -> None:
    async with get_db() as session:
        await session.execute(
            delete(DevicePermission).where(
                DevicePermission.device_id == device_id,
                DevicePermission.user_id == user_id,
            )
        )
        await session.commit()


async def set_granular_permission(
    device_id: str, user_id: str, permission: str, value: bool
) -> None:
    async with get_db() as session:
        perm = await session.execute(
            select(DevicePermission).where(
                DevicePermission.device_id == device_id,
                DevicePermission.user_id == user_id,
            )
        )
        perm = perm.scalar_one_or_none()
        if perm is None:
            perm = DevicePermission(device_id=device_id, user_id=user_id, role="viewer")
            session.add(perm)
        if hasattr(perm, permission):
            setattr(perm, permission, value)
        await session.commit()


async def set_all_granular_permissions(
    device_id: str, user_id: str, permissions: Dict[str, bool]
) -> None:
    async with get_db() as session:
        perm = await session.execute(
            select(DevicePermission).where(
                DevicePermission.device_id == device_id,
                DevicePermission.user_id == user_id,
            )
        )
        perm = perm.scalar_one_or_none()
        if perm is None:
            perm = DevicePermission(device_id=device_id, user_id=user_id, role="viewer")
            session.add(perm)
        for field, value in permissions.items():
            if hasattr(perm, field):
                setattr(perm, field, value)
        await session.commit()


# ---------------------------------------------------------------------------
# LcdConfig
# ---------------------------------------------------------------------------

async def get_lcd_config(device_id: str) -> Optional[LcdConfig]:
    async with get_db() as session:
        result = await session.execute(
            select(LcdConfig).where(LcdConfig.device_id == device_id)
        )
        return result.scalar_one_or_none()


async def upsert_lcd_config(
    device_id: str,
    *,
    line0_format: Optional[str] = None,
    line1_format: Optional[str] = None,
    scroll_speed: Optional[int] = None,
    scroll_pause: Optional[int] = None,
    distance_unit: Optional[str] = None,
    custom_text0: Optional[str] = None,
    custom_text1: Optional[str] = None,
    show_scroll0: Optional[bool] = None,
    show_scroll1: Optional[bool] = None,
) -> LcdConfig:
    async with get_db() as session:
        cfg = await session.execute(
            select(LcdConfig).where(LcdConfig.device_id == device_id)
        )
        cfg = cfg.scalar_one_or_none()
        if cfg is None:
            cfg = LcdConfig(device_id=device_id)
            session.add(cfg)
        if line0_format is not None:
            cfg.line0_format = line0_format
        if line1_format is not None:
            cfg.line1_format = line1_format
        if scroll_speed is not None:
            cfg.scroll_speed = scroll_speed
        if scroll_pause is not None:
            cfg.scroll_pause = scroll_pause
        if distance_unit is not None:
            cfg.distance_unit = distance_unit
        if custom_text0 is not None:
            cfg.custom_text0 = custom_text0
        if custom_text1 is not None:
            cfg.custom_text1 = custom_text1
        if show_scroll0 is not None:
            cfg.show_scroll0 = show_scroll0
        if show_scroll1 is not None:
            cfg.show_scroll1 = show_scroll1
        await session.commit()
        await session.refresh(cfg)
        return cfg


# ---------------------------------------------------------------------------
# Telemetry History
# ---------------------------------------------------------------------------

async def get_telemetry_history(
    device_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    async with get_db() as session:
        query = (
            select(Telemetry)
            .where(Telemetry.device_id == device_id)
            .order_by(Telemetry.created_at.desc())
        )
        if start:
            query = query.where(Telemetry.created_at >= start)
        if end:
            query = query.where(Telemetry.created_at <= end)
        query = query.limit(limit)
        result = await session.execute(query)
        return [t.to_dict() for t in result.scalars().all()]


async def get_telemetry_stats(
    device_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> Dict[str, Any]:
    """Return min, max, avg for water_percent and water_liters."""
    from sqlalchemy import func as sa_func

    async with get_db() as session:
        query = select(
            sa_func.avg(Telemetry.water_percent),
            sa_func.min(Telemetry.water_percent),
            sa_func.max(Telemetry.water_percent),
            sa_func.avg(Telemetry.water_liters),
            sa_func.min(Telemetry.water_liters),
            sa_func.max(Telemetry.water_liters),
            sa_func.count(Telemetry.id),
        ).where(Telemetry.device_id == device_id)
        if start:
            query = query.where(Telemetry.created_at >= start)
        if end:
            query = query.where(Telemetry.created_at <= end)
        row = await session.execute(query)
        result = row.one()
        return {
            "avg_percent": round(result[0], 2) if result[0] else 0,
            "min_percent": round(result[1], 2) if result[1] is not None else 0,
            "max_percent": round(result[2], 2) if result[2] is not None else 0,
            "avg_liters": round(result[3], 2) if result[3] else 0,
            "min_liters": round(result[4], 2) if result[4] is not None else 0,
            "max_liters": round(result[5], 2) if result[5] is not None else 0,
            "count": result[6],
        }
