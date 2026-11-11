from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Boolean, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="Nuevo Bebedero")
    location: Mapped[str] = mapped_column(String(128), default="Sin ubicación")
    firmware_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_CLAIM")  # PENDING_CLAIM, CLAIMED, BLOCKED
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relaciones
    config: Mapped[Optional["TankConfig"]] = relationship("TankConfig", back_populates="device", cascade="all, delete-orphan", uselist=False)
    telemetries: Mapped[list["Telemetry"]] = relationship("Telemetry", back_populates="device", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "firmware_version": self.firmware_version,
            "key_hash": self.key_hash,
            "owner_id": self.owner_id,
            "status": self.status,
            "is_online": self.is_online,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "config": self.config.to_dict() if self.config else None
        }

class TankConfig(Base):
    __tablename__ = "tank_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.id", ondelete="CASCADE"), unique=True)
    capacity_liters: Mapped[float] = mapped_column(Float, default=50.0)
    bottom_dist_mm: Mapped[float] = mapped_column(Float, default=900.0)
    mirror_dist_mm: Mapped[float] = mapped_column(Float, default=100.0)
    min_level_percent: Mapped[float] = mapped_column(Float, default=25.0)
    max_level_percent: Mapped[float] = mapped_column(Float, default=90.0)
    auto_refill: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    device: Mapped["Device"] = relationship("Device", back_populates="config")

    def to_dict(self):
        return {
            "capacity": self.capacity_liters,
            "bottom_dist_mm": self.bottom_dist_mm,
            "mirror_dist_mm": self.mirror_dist_mm,
            "min_level": self.min_level_percent,
            "max_level": self.max_level_percent,
            "auto_refill": self.auto_refill,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.id", ondelete="CASCADE"))
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
            "created_at": self.created_at.isoformat() if self.created_at else None
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
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
