"""Permission service: permisos granulares por dispositivo."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from backend.database.models import DevicePermission
from backend.services import db_service

logger = logging.getLogger("DispWatter.PermissionService")

# Roles y sus capacidades
ROLE_PERMISSIONS = {
    "owner": {
        "view", "control_pump", "edit_config", "edit_auto_refill",
        "restart_device", "delete_device", "manage_permissions",
        "edit_lcd", "get_history", "claim_device",
    },
    "editor": {
        "view", "control_pump", "edit_config", "edit_auto_refill",
        "edit_lcd", "get_history",
    },
    "viewer": {
        "view", "get_history",
    },
}

# Admin tiene todo implícitamente
ADMIN_PERMISSIONS = {
    "view", "control_pump", "edit_config", "edit_auto_refill",
    "restart_device", "delete_device", "manage_permissions",
    "edit_lcd", "get_history", "claim_device",
}


def get_role_permissions(role: str) -> set:
    """Get the set of permissions for a given role."""
    return ROLE_PERMISSIONS.get(role, set())


async def get_device_permissions(device_id: str) -> List[Dict[str, str]]:
    """Get all permissions for a device."""
    perms = await db_service.get_device_permissions(device_id)
    result = []
    for perm in perms:
        user = await db_service.get_user_by_id(perm.user_id)
        result.append({
            "id": perm.id,
            "device_id": perm.device_id,
            "user_id": perm.user_id,
            "username": user.username if user else "desconocido",
            "email": user.email if user else "",
            "role": perm.role,
            "granted_by": perm.granted_by,
            "granted_at": perm.granted_at.isoformat() if perm.granted_at else None,
        })
    return result


async def grant_permission(
    device_id: str, user_id: str, role: str, granted_by: Optional[str] = None
) -> Tuple[bool, str]:
    """Grant or update a permission for a user on a device.
    
    Returns:
        (success, message) tuple.
    """
    if role not in ROLE_PERMISSIONS:
        return False, f"Rol inválido. Usa: {', '.join(ROLE_PERMISSIONS.keys())}"
    
    # Check device exists
    device = await db_service.get_device(device_id)
    if device is None:
        return False, "Dispositivo no encontrado"
    
    # Check user exists
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        return False, "Usuario no encontrado"
    
    try:
        perm = await db_service.grant_permission(
            device_id=device_id,
            user_id=user_id,
            role=role,
            granted_by=granted_by,
        )
        logger.info(
            "Permiso %s otorgado a %s en dispositivo %s",
            role, user.email, device_id,
        )
        return True, f"Permiso '{role}' otorgado a {user.email}"
    except Exception as e:
        logger.error("Error otorgando permiso: %s", e)
        return False, f"Error: {e}"


async def revoke_permission(device_id: str, user_id: str) -> Tuple[bool, str]:
    """Revoke a permission for a user on a device.
    
    Returns:
        (success, message) tuple.
    """
    # Check device exists
    device = await db_service.get_device(device_id)
    if device is None:
        return False, "Dispositivo no encontrado"
    
    # Check user exists
    user = await db_service.get_user_by_id(user_id)
    email = user.email if user else "desconocido"
    
    try:
        await db_service.revoke_permission(device_id=device_id, user_id=user_id)
        logger.info("Permiso revocado para %s en dispositivo %s", email, device_id)
        return True, f"Permiso revocado para {email}"
    except Exception as e:
        logger.error("Error revocando permiso: %s", e)
        return False, f"Error: {e}"


async def check_permission(
    user_id: str, device_id: str, action: str
) -> bool:
    """Check if a user has permission to perform an action on a device.
    
    Admin users have implicit access to all devices.
    Device owners have full access.
    Other users need explicit permissions.
    
    Args:
        user_id: The user's ID.
        device_id: The device's ID.
        action: The action to check (e.g., "view", "control_pump", "edit_config").
    
    Returns:
        True if the user has permission, False otherwise.
    """
    # Get user
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        return False
    
    # Admin has implicit access to everything
    if user.role == "admin":
        return True
    
    # Get device
    device = await db_service.get_device(device_id)
    if device is None:
        return False
    
    # Device owner has full access
    if device.owner_id == user_id:
        return True
    
    # Check explicit permissions
    perm = await db_service.get_device_permission(device_id, user_id)
    if perm is None:
        return False
    
    # Check if the role has the required permission
    role_perms = get_role_permissions(perm.role)
    return action in role_perms


async def get_user_accessible_devices(user_id: str) -> List[str]:
    """Get all device IDs that a user can access.
    
    Includes:
    - All devices if user is admin
    - Devices owned by the user
    - Devices with explicit permissions
    
    Returns:
        List of device IDs.
    """
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        return []
    
    # Admin accesses all devices
    if user.role == "admin":
        devices = await db_service.get_all_devices_for_sync()
        return [d["id"] for d in devices]
    
    from backend.database.connect import get_db
    from backend.database.models import Device, DevicePermission as DP
    from sqlalchemy import select
    
    async with get_db() as session:
        # Owned devices
        result = await session.execute(
            select(Device.id).where(Device.owner_id == user_id)
        )
        owned = [row[0] for row in result.all()]
        
        # Devices with explicit permissions
        result = await session.execute(
            select(DP.device_id).where(DP.user_id == user_id)
        )
        permitted = [row[0] for row in result.all()]
    
    return list(set(owned + permitted))
