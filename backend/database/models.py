from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    devices: Mapped[list["Device"]] = relationship("Device", back_populates="owner")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="Nuevo Bebedero")
    location: Mapped[str] = mapped_column(String(128), default="Sin ubicación")
    firmware_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    # Unique hardware serial (ESP32 MAC-based). Prevents duplicate device_id on flash.
    serial_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Puede ser NULL mientras el dispositivo está pendiente de vinculación.
    key_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="PENDING_CLAIM")
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_rssi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wake_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    owner: Mapped[Optional["User"]] = relationship("User", back_populates="devices")
    config: Mapped[Optional["TankConfig"]] = relationship(
        "TankConfig", back_populates="device", cascade="all, delete-orphan", uselist=False
    )
    telemetries: Mapped[list["Telemetry"]] = relationship(
        "Telemetry", back_populates="device", cascade="all, delete-orphan"
    )
    networks: Mapped[list["DeviceNetwork"]] = relationship(
        "DeviceNetwork", back_populates="device", cascade="all, delete-orphan"
    )

    def to_dict(self):
        # Nunca se expone key_hash al panel.
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "firmware_version": self.firmware_version,
            "serial_number": self.serial_number,
            "owner_id": self.owner_id,
            "status": self.status,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "last_rssi": self.last_rssi,
            "last_ip": self.last_ip,
            "wake_reason": self.wake_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "config": self.config.to_dict() if self.config else None,
        }


class TankConfig(Base):
    __tablename__ = "tank_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), unique=True
    )
    capacity_liters: Mapped[float] = mapped_column(Float, default=50.0)
    bottom_dist_mm: Mapped[float] = mapped_column(Float, default=900.0)
    mirror_dist_mm: Mapped[float] = mapped_column(Float, default=100.0)
    min_level_percent: Mapped[float] = mapped_column(Float, default=25.0)
    max_level_percent: Mapped[float] = mapped_column(Float, default=90.0)
    auto_refill: Mapped[bool] = mapped_column(Boolean, default=True)
    # Protección de bomba: tiempo mínimo de apagado entre arranques (en minutos)
    min_relay_off_min: Mapped[float] = mapped_column(Float, default=3.0)
    # Protección contra desborde: apagar bomba al superar máximo aunque auto esté off
    overflow_protection: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    device: Mapped["Device"] = relationship("Device", back_populates="config")

    def to_dict(self):
        return {
            "capacity": self.capacity_liters,
            "bottom_dist_mm": self.bottom_dist_mm,
            "mirror_dist_mm": self.mirror_dist_mm,
            "min_level": self.min_level_percent,
            "max_level": self.max_level_percent,
            "auto_refill": self.auto_refill,
            "min_relay_off_min": self.min_relay_off_min,
            "overflow_protection": self.overflow_protection,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DeviceNetwork(Base):
    """Caché de redes del dispositivo. Nunca guarda contraseñas."""

    __tablename__ = "device_networks"
    __table_args__ = (UniqueConstraint("device_id", "ssid", name="uq_device_network"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    ssid: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    has_password: Mapped[bool] = mapped_column(Boolean, default=True)
    rssi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=False)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    device: Mapped["Device"] = relationship("Device", back_populates="networks")

    def to_dict(self):
        return {
            "ssid": self.ssid,
            "priority": self.priority,
            "has_password": self.has_password,
            "rssi": self.rssi,
            "visible": self.visible,
            "connected": self.connected,
        }


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE")
    )
    distance_mm: Mapped[float] = mapped_column(Float, nullable=False)
    water_percent: Mapped[float] = mapped_column(Float, nullable=False)
    water_liters: Mapped[float] = mapped_column(Float, nullable=False)
    relay_state: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    device: Mapped["Device"] = relationship("Device", back_populates="telemetries")

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "distance_mm": self.distance_mm,
            "water_percent": self.water_percent,
            "water_liters": self.water_liters,
            "relay_state": self.relay_state,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(64), default="SYSTEM")
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "device_id": self.device_id,
            "actor": self.actor,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmailVerification(Base):
    """Tokens de verificación de email para registro de usuarios."""

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "user_id": self.user_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used": self.used,
        }


class DevicePermission(Base):
    """Permisos granulares por dispositivo para usuarios."""

    __tablename__ = "device_permissions"
    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="uq_device_permission"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="viewer"
    )  # owner, editor, viewer
    # Granular boolean toggles
    view_telemetry: Mapped[bool] = mapped_column(Boolean, default=True)
    control_pump: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_refill: Mapped[bool] = mapped_column(Boolean, default=False)
    configure_tank: Mapped[bool] = mapped_column(Boolean, default=False)
    reboot_device: Mapped[bool] = mapped_column(Boolean, default=False)
    factory_reset: Mapped[bool] = mapped_column(Boolean, default=False)
    delete_device: Mapped[bool] = mapped_column(Boolean, default=False)
    view_history: Mapped[bool] = mapped_column(Boolean, default=True)
    view_audit: Mapped[bool] = mapped_column(Boolean, default=False)
    ota_update: Mapped[bool] = mapped_column(Boolean, default=False)
    manage_lcd: Mapped[bool] = mapped_column(Boolean, default=False)
    change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    GRANULAR_FIELDS = [
        "view_telemetry", "control_pump", "auto_refill", "configure_tank",
        "reboot_device", "factory_reset", "delete_device", "view_history",
        "view_audit", "ota_update", "manage_lcd", "change_password",
    ]

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "user_id": self.user_id,
            "role": self.role,
            "view_telemetry": self.view_telemetry,
            "control_pump": self.control_pump,
            "auto_refill": self.auto_refill,
            "configure_tank": self.configure_tank,
            "reboot_device": self.reboot_device,
            "factory_reset": self.factory_reset,
            "delete_device": self.delete_device,
            "view_history": self.view_history,
            "view_audit": self.view_audit,
            "ota_update": self.ota_update,
            "manage_lcd": self.manage_lcd,
            "change_password": self.change_password,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }


class LcdConfig(Base):
    """Configuración del LCD por dispositivo."""

    __tablename__ = "lcd_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Formato de cada línea: percent, liters, distance, pump_status, custom, empty
    line0_format: Mapped[str] = mapped_column(String(32), default="percent", nullable=False)
    line1_format: Mapped[str] = mapped_column(String(32), default="liters", nullable=False)
    # Velocidad del scroll en ms por paso (100-500)
    scroll_speed: Mapped[int] = mapped_column(Integer, default=200)
    # Pausa al final del scroll en segundos
    scroll_pause: Mapped[int] = mapped_column(Integer, default=3)
    # Unidad de distancia: cm, mm, m
    distance_unit: Mapped[str] = mapped_column(String(8), default="cm")
    # Textos personalizados
    custom_text0: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    custom_text1: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Activar scroll en cada línea
    show_scroll0: Mapped[bool] = mapped_column(Boolean, default=True)
    show_scroll1: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    device: Mapped["Device"] = relationship("Device")

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "line0_format": self.line0_format,
            "line1_format": self.line1_format,
            "scroll_speed": self.scroll_speed,
            "scroll_pause": self.scroll_pause,
            "distance_unit": self.distance_unit,
            "custom_text0": self.custom_text0,
            "custom_text1": self.custom_text1,
            "show_scroll0": self.show_scroll0,
            "show_scroll1": self.show_scroll1,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
