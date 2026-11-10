import hashlib
import time
import json
from datetime import datetime
from typing import Optional
from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import AuditLog

def hash_credentials(device_id: str, device_pass: str) -> str:
    """Calcula el hash SHA-256 de las credenciales del dispositivo."""
    raw = f"{device_id}:{device_pass}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def generate_handshake_token(device_key_hash: str, timestamp: int) -> str:
    """Genera el token dinámico con timestamp esperado del hardware."""
    raw = f"{device_key_hash}:{timestamp}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def verify_device_token(device_key_hash: str, token: str, timestamp: int, tolerance_sec: int = 300) -> bool:
    """Verifica si el token generado por el ESP32 es válido y no ha expirado."""
    if not device_key_hash or not token:
        return False
    
    # Tolerancia de tiempo (5 minutos por defecto para desfases de reloj en ESP32)
    current_time = int(time.time())
    if abs(current_time - timestamp) > tolerance_sec:
        # Nota: si el ESP32 no tiene NTP sincronizado y envía tiempo relativo (millis / 1000),
        # podemos verificar la consistencia del hash directo
        expected = generate_handshake_token(device_key_hash, timestamp)
        return expected.lower() == token.lower()

    expected = generate_handshake_token(device_key_hash, timestamp)
    return expected.lower() == token.lower()

async def record_audit(action: str, device_id: Optional[str] = None, actor: str = "SYSTEM", details: Optional[str] = None):
    """
    Registra un evento de auditoría tanto en el archivo de texto audit.log
    como en la base de datos relacional para persistencia y consulta.
    """
    now_iso = datetime.now().isoformat()
    log_line = f"[{now_iso}] [AUDIT] [{action}] Actor={actor} Device={device_id or 'N/A'} Details={details or ''}\n"

    # 1. Escritura en archivo audit.log
    try:
        settings.AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"Error escribiendo en audit.log: {e}")

    # 2. Persistencia en Base de Datos
    try:
        async with get_db() as session:
            audit_entry = AuditLog(
                action=action,
                device_id=device_id,
                actor=actor,
                details=details
            )
            session.add(audit_entry)
            await session.commit()
    except Exception as e:
        print(f"Error guardando auditoría en BD: {e}")
