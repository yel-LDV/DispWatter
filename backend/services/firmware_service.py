"""Servicio para gestionar firmware subidos desde el panel."""
import hashlib
import logging
from typing import Optional

from sqlalchemy import select, delete

from backend.database.connect import AsyncSessionLocal
from backend.database.models import FirmwareUpload

logger = logging.getLogger("DispWatter.FirmwareService")

# Tamaño máximo del firmware: 2 MB
MAX_FIRMWARE_SIZE = 2 * 1024 * 1024


async def upload_firmware(
    name: str,
    version: str,
    binary_hex: str,
    description: Optional[str] = None,
    firmware_type: str = "custom",
) -> dict:
    """Subir un firmware binario (hex string) y guardarlo en la DB.
    
    Returns dict with id, name, version, sha256, size, etc.
    Raises ValueError si el binario es inválido o demasiado grande.
    """
    # Decodificar hex a bytes
    try:
        binary = bytes.fromhex(binary_hex)
    except ValueError:
        raise ValueError("El binario no es un string hex válido")
    
    if len(binary) == 0:
        raise ValueError("El binario está vacío")
    
    if len(binary) > MAX_FIRMWARE_SIZE:
        raise ValueError(f"El binario excede el tamaño máximo ({MAX_FIRMWARE_SIZE} bytes)")
    
    # Validar que parezca firmware ESP32 (debe empezar con 0xE9 magic byte)
    if len(binary) > 0 and binary[0] != 0xE9:
        logger.warning("El binario no comienza con el magic byte 0xE9 esperado de ESP32")
    
    sha256 = hashlib.sha256(binary).hexdigest()
    
    async with AsyncSessionLocal() as session:
        fw = FirmwareUpload(
            name=name.strip() or f"firmware-{version}",
            version=version.strip(),
            sha256=sha256,
            size=len(binary),
            binary=binary.hex(),  # Store as hex string in TEXT column
            description=description,
            firmware_type=firmware_type if firmware_type in ("stable", "experimental", "custom") else "custom",
        )
        session.add(fw)
        await session.commit()
        await session.refresh(fw)
        logger.info("Firmware subido: %s v%s (%d bytes, sha256=%s)", fw.name, fw.version, fw.size, fw.sha256)
        return fw.to_dict()


async def list_firmwares() -> list[dict]:
    """Listar todos los firmware subidos."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmwareUpload).order_by(FirmwareUpload.uploaded_at.desc())
        )
        firmwares = result.scalars().all()
        return [fw.to_dict() for fw in firmwares]


async def get_firmware(firmware_id: int) -> Optional[dict]:
    """Obtener un firmware por ID incluyendo el binario."""
    async with AsyncSessionLocal() as session:
        fw = await session.get(FirmwareUpload, firmware_id)
        if not fw:
            return None
        data = fw.to_dict()
        # Incluir el binario hex para OTA
        data["binary_hex"] = fw.binary
        return data


async def get_firmware_binary(firmware_id: int) -> Optional[bytes]:
    """Obtener solo el binario de un firmware por ID."""
    async with AsyncSessionLocal() as session:
        fw = await session.get(FirmwareUpload, firmware_id)
        if not fw:
            return None
        try:
            return bytes.fromhex(fw.binary)
        except ValueError:
            logger.error("Error decodificando binario hex para firmware %d", firmware_id)
            return None


async def delete_firmware(firmware_id: int) -> bool:
    """Eliminar un firmware subido."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(FirmwareUpload).where(FirmwareUpload.id == firmware_id))
        await session.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Firmware eliminado: id=%d", firmware_id)
        return deleted


async def check_duplicate_sha256(sha256: str) -> Optional[int]:
    """Verificar si ya existe un firmware con el mismo SHA256.
    
    Returns the existing firmware ID if found, None otherwise.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmwareUpload.id).where(FirmwareUpload.sha256 == sha256).limit(1)
        )
        row = result.scalar_one_or_none()
        return row
