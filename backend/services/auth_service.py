"""Auth service: registro de usuarios, verificación por email y envío SMTP."""
from __future__ import annotations

import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional, Tuple

from backend.config import settings
from backend.database.models import User
from backend.security.auth import hash_password
from backend.services import db_service

logger = logging.getLogger("DispWatter.AuthService")

VERIFICATION_TOKEN_EXPIRY_HOURS = 24


def _generate_verification_token() -> str:
    """Generate a random verification token."""
    return secrets.token_urlsafe(32)


async def register_user(
    email: str, password: str
) -> Tuple[bool, str]:
    """Register a new user with email verification.
    
    Returns:
        (success, message) tuple.
    """
    # Validate email format
    if "@" not in email or "." not in email:
        return False, "Correo electrónico no válido"
    
    email = email.strip().lower()
    
    # Check if email already exists
    existing = await db_service.get_user_by_email(email)
    if existing:
        if existing.is_verified:
            return False, "Este correo ya está registrado"
        else:
            # Resend verification email for unverified account
            await send_verification_email(existing.id)
            return False, "Ya existe una cuenta pendiente de verificación. Se reenvió el email."
    
    # Generate username from email
    username = email.split("@")[0][:64]
    
    # Check if username already exists (unlikely but possible)
    existing_user = await db_service.get_user_by_username(username)
    if existing_user:
        return False, "Este correo ya está registrado"
    
    # Create user
    password_hash = hash_password(password)
    user = await db_service.create_user(
        username=username,
        email=email,
        password_hash=password_hash,
        role="user",
    )
    
    # Create verification token
    token = _generate_verification_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_EXPIRY_HOURS)
    await db_service.create_email_verification(
        email=email,
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    
    # Send verification email
    try:
        await smtp_send(
            to=email,
            subject="Verifica tu cuenta DispWatter",
            body=_build_verification_email_body(email, token),
        )
        logger.info("Email de verificación enviado a %s", email)
    except Exception as e:
        logger.error("Error enviando email de verificación a %s: %s", email, e)
        # Still return success; the user can request resend later
    
    return True, f"Cuenta creada. Revisa tu correo {email} para verificar tu cuenta."


async def verify_email(token: str) -> Tuple[bool, str]:
    """Verify user's email using the token from the verification email.
    
    Returns:
        (success, message) tuple.
    """
    ev = await db_service.get_email_verification(token)
    if ev is None:
        return False, "Token de verificación inválido"
    
    if ev.used:
        return False, "Este token ya fue utilizado"
    
    now = datetime.now(timezone.utc)
    if ev.expires_at.replace(tzinfo=None) < now or ev.expires_at < now:
        return False, "El token de verificación ha expirado. Solicita un nuevo email."
    
    # Verify the user
    if ev.user_id:
        await db_service.verify_user(ev.user_id)
        await db_service.mark_email_verification_used(token)
        
        user = await db_service.get_user_by_id(ev.user_id)
        username = user.username if user else ev.email
        logger.info("Email verificado: %s (usuario %s)", ev.email, username)
        return True, "Cuenta verificada correctamente. Ya puedes iniciar sesión."
    
    return False, "Token no asociado a ningún usuario"


async def send_verification_email(user_id: str) -> Tuple[bool, str]:
    """Resend verification email for an existing unverified user.
    
    Returns:
        (success, message) tuple.
    """
    user = await db_service.get_user_by_id(user_id)
    if user is None:
        return False, "Usuario no encontrado"
    
    if user.is_verified:
        return False, "Esta cuenta ya está verificada"
    
    # Delete old unused tokens
    # Create new verification token
    token = _generate_verification_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_EXPIRY_HOURS)
    await db_service.create_email_verification(
        email=user.email,
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    
    try:
        await smtp_send(
            to=user.email,
            subject="Verifica tu cuenta DispWatter",
            body=_build_verification_email_body(user.email, token),
        )
        logger.info("Email de verificación reenviado a %s", user.email)
        return True, f"Se reenvió el email de verificación a {user.email}"
    except Exception as e:
        logger.error("Error reenviando email de verificación a %s: %s", user.email, e)
        return False, f"Error enviando email: {e}"


def _build_verification_email_body(email: str, token: str) -> str:
    """Build the HTML body for the verification email."""
    # The verification link will be handled by the panel frontend
    # We include the token directly for the API endpoint
    verify_url = f"http://localhost:3000/verify?token={token}"
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Bienvenido a DispWatter</h2>
        <p>Para activar tu cuenta, haz clic en el siguiente enlace:</p>
        <p>
            <a href="{verify_url}" 
               style="background-color: #4CAF50; color: white; padding: 12px 24px; 
                      text-decoration: none; border-radius: 4px; display: inline-block;">
                Verificar mi cuenta
            </a>
        </p>
        <p>O copia y pega este enlace en tu navegador:</p>
        <p style="word-break: break-all; color: #666;">{verify_url}</p>
        <p>Este enlace expirará en {VERIFICATION_TOKEN_EXPIRY_HOURS} horas.</p>
        <p>Si no creaste esta cuenta, puedes ignorar este email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 20px;">
        <p style="color: #999; font-size: 12px;">DispWatter - Sistema de monitoreo de agua</p>
    </body>
    </html>
    """
    return html


async def smtp_send(to: str, subject: str, body: str) -> None:
    """Send an email via SMTP.
    
    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: HTML body content.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP no configurado. Configura SMTP_HOST, SMTP_USER y SMTP_PASSWORD en backend/.env")
    
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    
    context = ssl.create_default_context()
    
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls(context=context)
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(
            settings.SMTP_FROM or settings.SMTP_USER,
            to,
            msg.as_string(),
        )
    
    logger.info("Email enviado a %s: %s", to, subject)


async def check_smtp_configured() -> bool:
    """Check if SMTP is properly configured."""
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USER
        and settings.SMTP_PASSWORD
    )
