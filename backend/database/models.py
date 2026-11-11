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
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    devices: Mapped[list["Device"]] = relationship("Device", back_populates="owner")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="Nuevo Bebedero")
    location: Mapped[str] = mapped_column(String(128), default="Sin ubicación")
    firmware_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
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
