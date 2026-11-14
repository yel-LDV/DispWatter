"""Autenticación de usuarios y dispositivos DispWatter.

- Usuarios: contraseñas con Argon2id y sesiones JWT (HS256).
- Dispositivos: challenge-response HMAC-SHA256 con nonce de un solo uso.
- Auditoría: archivo de texto + tabla audit_logs.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from backend.config import settings
from backend.database.connect import get_db
from backend.database.models import AuditLog

logger = logging.getLogger("DispWatter.Auth")

_password_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Contraseñas de usuario
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    try:
        return bool(_password_hasher.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False
    except Exception:  # nunca filtrar detalles de argon2 al cliente
        logger.exception("Error verificando contraseña")
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if not payload.get("sub"):
        return None
    return payload


# ---------------------------------------------------------------------------
# Dispositivos
# ---------------------------------------------------------------------------
def hash_credentials(device_id: str, device_secret: str) -> str:
    """SHA256(id:secreto). Es el key_hash que guarda el ESP32."""
    raw = f"{device_id}:{device_secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_device_proof(key_hash: str, nonce: str) -> str:
    """HMAC-SHA256 usando el key_hash hexadecimal como clave (igual que el ESP32)."""
    return hmac.new(
        key_hash.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_device_proof(key_hash: str, nonce: str, proof: str) -> bool:
    if not key_hash or not nonce or not proof:
        return False
    expected = compute_device_proof(key_hash, nonce)
    return hmac.compare_digest(expected, proof.lower())


# ---------------------------------------------------------------------------
# Origen del WebSocket del panel
# ---------------------------------------------------------------------------

# Orígenes extra detectados automáticamente (IP pública del servidor).
_auto_origins: list[str] = []


def _detect_public_origin() -> None:
    """Detecta la IP pública del servidor y la agrega a los orígenes permitidos.

    Se ejecuta una vez al importar el módulo. Si no se puede obtener la IP
    pública (sin internet, curl/wget no instalados), no pasa nada: el panel
    seguirá funcionando desde localhost y la LAN.
    """
    import subprocess
    import urllib.request

    public_ip = None

    # Intentar con urllib (sin dependencias externas)
    try:
        req = urllib.request.Request(
            "https://api.ipify.org",
            headers={"User-Agent": "DispWatter/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            public_ip = resp.read().decode("utf-8").strip()
    except Exception:
        pass

    # Fallback: intentar con curl
    if not public_ip:
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "3", "https://api.ipify.org"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                public_ip = result.stdout.strip()
        except Exception:
            pass

    # Fallback: intentar con wget
    if not public_ip:
        try:
            result = subprocess.run(
                ["wget", "-qO-", "--timeout=3", "https://api.ipify.org"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                public_ip = result.stdout.strip()
        except Exception:
            pass

    if public_ip:
        for scheme in ("http", "https"):
            origin = f"{scheme}://{public_ip}:{settings.PANEL_PORT}"
            _auto_origins.append(origin)
        logger.info("[ORIGIN] IP pública detectada: %s (orígenes auto-agregados)", public_ip)


_detect_public_origin()


def is_origin_allowed(origin: Optional[str]) -> bool:
    """Valida el header Origin del panel.

    - Sin Origin (clientes de línea de comandos) se permite.
    - Si PANEL_ORIGINS contiene "*" se permite cualquiera.
    - Se permiten orígenes loopback o de red privada en el puerto del panel,
      para poder abrir el panel desde otro equipo de la LAN.
    - La IP pública del servidor se detecta automáticamente al arrancar.
    """
    if not origin:
        return True
    allowed = settings.PANEL_ORIGINS_LIST + _auto_origins
    normalized = origin.rstrip("/")
    if "*" in allowed or normalized in allowed:
        return True

    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.port != settings.PANEL_PORT:
        return False
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------
async def record_audit(
    action: str,
    device_id: Optional[str] = None,
    actor: str = "SYSTEM",
    details: Optional[str] = None,
) -> None:
    now_iso = datetime.now().isoformat()
    log_line = (
        f"[{now_iso}] [AUDIT] [{action}] Actor={actor} "
        f"Device={device_id or 'N/A'} Details={details or ''}\n"
    )

    try:
        settings.AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.AUDIT_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(log_line)
    except Exception as exc:
        logger.warning("No se pudo escribir audit.log: %s", exc)

    try:
        async with get_db() as session:
            session.add(
                AuditLog(
                    action=action,
                    device_id=device_id,
                    actor=actor,
                    details=details,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning("No se pudo guardar auditoría en BD: %s", exc)


class LoginRateLimiter:
    """Límite simple en memoria: N intentos por ventana y por IP."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        entries = [ts for ts in self._attempts.get(key, []) if ts >= cutoff]
        if entries:
            self._attempts[key] = entries
        else:
            self._attempts.pop(key, None)

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(key, now)
        return len(self._attempts.get(key, [])) >= self.max_attempts

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now)
        self._attempts.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)
