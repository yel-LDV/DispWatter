"""Auth service: registro de usuarios simple y cambio de contraseña."""
from __future__ import annotations

import logging
from typing import Tuple

from backend.database.models import User
from backend.security.auth import hash_password
from backend.services import db_service

logger = logging.getLogger("DispWatter.AuthService")


async def register_user(
    email: str, password: str
) -> Tuple[bool, str]:
    """Register a new user without email verification.
    
    Returns:
        (success, message) tuple.
    """
    if "@" not in email or "." not in email:
        return False, "Correo electrónico no válido"
    
    email = email.strip().lower()
    
    existing = await db_service.get_user_by_email(email)
    if existing:
        return False, "Este correo ya está registrado"
    
    username = email.split("@")[0][:64]
    
    existing_user = await db_service.get_user_by_username(username)
    if existing_user:
        return False, "Este correo ya está registrado"
    
    password_hash = hash_password(password)
    user = await db_service.create_user(
        username=username,
        email=email,
        password_hash=password_hash,
        role="user",
        is_verified=True,
    )
    
    logger.info("Usuario registrado: %s (id %s)", email, user.id)
    return True, "Cuenta creada correctamente. Ya puedes iniciar sesión."


async def change_password(
    user_id: str, old_password: str, new_password: str
) -> Tuple[bool, str]:
    """Change a user's password after verifying the old one.
    
    Returns:
        (success, message) tuple.
    """
    from backend.security.auth import verify_password
    
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        return False, "Usuario no encontrado"
    
    if not verify_password(old_password, user.password_hash):
        return False, "La contraseña actual es incorrecta"
    
    if len(new_password) < 6:
        return False, "La nueva contraseña debe tener al menos 6 caracteres"
    
    if new_password == old_password:
        return False, "La nueva contraseña debe ser diferente de la actual"
    
    new_hash = hash_password(new_password)
    await db_service.update_user_password(user_id, new_hash)
    
    logger.info("Contraseña cambiada para usuario %s", user.email)
    return True, "Contraseña cambiada correctamente"
