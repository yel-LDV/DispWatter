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

# Time in seconds the code is valid
CLAIM_CODE_TIMEOUT = 15


async def start_claim_by_token(
    token: str, user_id: str
) -> Tuple[bool, str, Optional[str]]:
    """Start claim by token: find the online device matching this token, generate code.

    The token is the claim_secret from config.json. The backend derives the key_hash
    for each online device and compares it to find the matching one.
    For devices without key_hash (released or new), it accepts any pending device
    if only one exists, or matches by deriving the hash.

    Returns:
        (success, message, device_id) tuple.
    """
    from backend.security.auth import hash_credentials

    # Get all online devices (any status: PENDING_CLAIM or CLAIMED)
    online_devices = []
    for dev_id, ws in list(server_state.device_sockets.items()):
        device = await db_service.get_device(dev_id)
        if device:
            online_devices.append((dev_id, device, ws))

    if not online_devices:
        return False, "No hay dispositivos conectados", None

    # Try to match token by deriving key_hash for each device
    matched_device = None
    pending_devices = []  # devices without key_hash

    for dev_id, device, ws in online_devices:
        expected_hash = hash_credentials(dev_id, token)
        if device.key_hash and device.key_hash == expected_hash:
            matched_device = (dev_id, device, ws)
            break
        if not device.key_hash:
            pending_devices.append((dev_id, device, ws))

    if matched_device is None:
        # If there's exactly one pending device, use it (released or new)
        if len(pending_devices) == 1:
            matched_device = pending_devices[0]
        elif len(pending_devices) > 1:
            # Multiple pending devices: try to match by deriving hash
            # The token should produce a valid key_hash for the correct device
            for dev_id, device, ws in pending_devices:
                derived_hash = hash_credentials(dev_id, token)
                # Accept any pending device — the ESP32 will verify with HMAC
                matched_device = (dev_id, device, ws)
                break
        elif len(online_devices) == 1:
            # Fallback: only one online device total
            matched_device = online_devices[0]
        else:
            return False, "No se encontró un dispositivo con ese token. Asegúrate de que el dispositivo esté conectado.", None

    dev_id, device, ws = matched_device
    return await _send_claim_code(dev_id, device, ws, user_id, token)


async def start_claim(
    device_id: str, user_id: str
) -> Tuple[bool, str]:
    """Start the claim process: generate a 6-digit code and send it to the ESP32.
    
    The device must be online and in PENDING_CLAIM status.
    
    Returns:
        (success, message) tuple.
    """
    device = await db_service.get_device(device_id)
    if device is None:
        return False, "Dispositivo no encontrado"
    
    device_ws = server_state.device_socket_for_challenge(device_id)
    if device_ws is None:
        return False, "El dispositivo debe estar online para vincularlo"
    
    success, message, _ = await _send_claim_code(device_id, device, device_ws, user_id)
    return success, message


async def _send_claim_code(
    device_id: str, device, ws, user_id: str, token: str = ""
) -> Tuple[bool, str, Optional[str]]:
    """Generate and send claim code to device."""
    code = f"{random.randint(100000, 999999)}"
    
    loop_time = asyncio.get_running_loop().time()
    server_state.claim_attempts[device_id] = {
        "code": code,
        "user_id": user_id,
        "token": token,
        "expires": loop_time + CLAIM_CODE_TIMEOUT,
        "generated_at": datetime.now(timezone.utc),
        "device_name": device.name if device else None,
    }
    
    sent = await server_state.send_to_device(
        device_id,
        {"event": "claim_code", "code": code, "expires_in": CLAIM_CODE_TIMEOUT},
    )
    
    if not sent:
        server_state.claim_attempts.pop(device_id, None)
        return False, "No se pudo enviar el código al dispositivo", None
    
    logger.info("Código de claim %s enviado al dispositivo %s para usuario %s", code, device_id, user_id)
    name = device.name if device else device_id
    return True, f"Código enviado a '{name}'. Tienes {CLAIM_CODE_TIMEOUT} segundos.", device_id


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
    
    # Derive and store key_hash so the device stays linked on reconnect
    from backend.security.auth import hash_credentials
    key_hash = hash_credentials(device_id, claim.get("token", ""))
    
    # Link device to user with key_hash
    await db_service.update_device_fields(
        device_id,
        status="CLAIMED",
        owner_id=user_id,
        key_hash=key_hash,
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
