"""Claim service: nuevo flujo de claim con código de 6 dígitos."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from backend.handlers.state import server_state
from backend.services import db_service
from backend.services import permission_service
from backend.security.auth import record_audit

logger = logging.getLogger("DispWatter.ClaimService")

# Tiempo en segundos que el código es válido
CLAIM_CODE_TIMEOUT = 20


async def start_claim(
    device_id: str, user_id: str
) -> Tuple[bool, str]:
    """Start the claim process: generate a 6-digit code and send it to the ESP32.
    
    The device must be online and in PENDING_CLAIM status.
    
    Returns:
        (success, message) tuple.
    """
    # Check device exists
    device = await db_service.get_device(device_id)
    if device is None:
        return False, "Dispositivo no encontrado"
    
    # Check device is online
    device_ws = server_state.device_socket_for_challenge(device_id)
    if device_ws is None:
        return False, "El dispositivo debe estar online para vincularlo"
    
    # Generate 6-digit code
    code = f"{random.randint(100000, 999999)}"
    
    # Store claim state
    loop_time = asyncio.get_running_loop().time()
    server_state.claim_attempts[device_id] = {
        "code": code,
        "user_id": user_id,
        "expires": loop_time + CLAIM_CODE_TIMEOUT,
        "generated_at": datetime.now(timezone.utc),
    }
    
    # Send code to device
    sent = await server_state.send_to_device(
        device_id,
        {"event": "claim_code", "code": code, "expires_in": CLAIM_CODE_TIMEOUT},
    )
    
    if not sent:
        server_state.claim_attempts.pop(device_id, None)
        return False, "No se pudo enviar el código al dispositivo"
    
    logger.info("Código de claim %s enviado al dispositivo %s para usuario %s", code, device_id, user_id)
    return True, f"Código enviado al dispositivo. Tienes {CLAIM_CODE_TIMEOUT} segundos para ingresarlo."


async def verify_claim_code(
    device_id: str, code: str, user_id: str
) -> Tuple[bool, str]:
    """Verify the 6-digit claim code and link the device to the user.
    
    Returns:
        (success, message) tuple.
    """
    claim = server_state.claim_attempts.get(device_id)
    if claim is None:
        return False, "No hay un proceso de claim activo. Solicita un nuevo código."
    
    # Check expiration
    loop_time = asyncio.get_running_loop().time()
    if loop_time > claim["expires"]:
        server_state.claim_attempts.pop(device_id, None)
        return False, "El código expiró. Solicita un nuevo código."
    
    # Verify code
    if claim["code"] != code.strip():
        return False, "Código incorrecto. Verifica e intenta de nuevo."
    
    # Get device
    device = await db_service.get_device(device_id)
    if device is None:
        server_state.claim_attempts.pop(device_id, None)
        return False, "Dispositivo no encontrado"
    
    # Get user
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        server_state.claim_attempts.pop(device_id, None)
        return False, "Usuario no encontrado"
    
    # Link device to user
    await db_service.update_device_fields(
        device_id,
        status="CLAIMED",
        owner_id=user_id,
    )
    
    # Grant owner permission
    await permission_service.grant_permission(
        device_id=device_id,
        user_id=user_id,
        role="owner",
        granted_by=user_id,
    )
    
    # Clean up
    server_state.claim_attempts.pop(device_id, None)
    
    # Notify device
    await server_state.send_to_device(
        device_id,
        {"event": "claim_verified", "owner_id": user_id},
    )
    
    await record_audit(
        "DEVICE_CLAIMED",
        device_id=device_id,
        actor=user.username,
        details=f"Vinculado a {user.email}",
    )
    
    logger.info("Dispositivo %s vinculado a %s (%s)", device_id, user.username, user.email)
    return True, f"Dispositivo '{device.name}' vinculado a tu cuenta."


async def get_claim_status(device_id: str) -> Dict[str, str]:
    """Get the current claim status for a device.
    
    Returns:
        Dict with status info.
    """
    claim = server_state.claim_attempts.get(device_id)
    if claim is None:
        return {"status": "no_active_claim"}
    
    loop_time = asyncio.get_running_loop().time()
    remaining = max(0, int(claim["expires"] - loop_time))
    return {
        "status": "active_claim",
        "remaining_seconds": remaining,
    }
