"""Migraciones idempotentes para bases de datos DispWatter existentes."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime

from sqlalchemy import select, text

from backend.database.connect import AsyncSessionLocal, engine
from backend.database.models import User

logger = logging.getLogger("DispWatter.Migrations")

DEVICE_COLUMNS = {
    "last_seen": "DATETIME",
    "last_rssi": "INTEGER",
    "last_ip": "TEXT",
    "wake_reason": "TEXT",
}


async def _columns(conn, table: str) -> set[str]:
    def _read(sync_conn):
        rows = sync_conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    return await conn.run_sync(_read)


async def _meta_get(conn, key: str) -> str | None:
    def _read(sync_conn):
        try:
            row = sync_conn.exec_driver_sql(
                "SELECT value FROM schema_meta WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    return await conn.run_sync(_read)


async def _meta_set(conn, key: str, value: str) -> None:
    def _write(sync_conn):
        sync_conn.exec_driver_sql(
            "INSERT INTO schema_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    await conn.run_sync(_write)


async def _bootstrap_admin() -> None:
    """Create and synchronize the managed root administrator from backend/.env."""
    from backend.config import settings
    from backend.security.auth import hash_password, verify_password

    username = settings.ADMIN_USER.strip()
    password = settings.ADMIN_PASSWORD
    if not username or not password:
        raise RuntimeError("ADMIN_USER y ADMIN_PASSWORD deben estar configurados en backend/.env")

    async with AsyncSessionLocal() as session:
        # Persist an internal marker so changing ADMIN_USER can rename the same
        # managed account instead of creating orphaned administrators.
        root_id = await session.scalar(
            text("SELECT value FROM schema_meta WHERE key = 'root_admin_id'")
        )
        root_user = await session.get(User, root_id) if root_id else None

        if root_user is None:
            # Adopt an existing admin on first upgrade, preferring the configured
            # username; otherwise create a new managed root account.
            root_user = await session.scalar(
                select(User).where(User.username == username, User.role == "admin").limit(1)
            )
            if root_user is None:
                root_user = await session.scalar(
                    select(User).where(User.role == "admin").order_by(User.created_at).limit(1)
                )
            if root_user is None:
                root_user = User(
                    id=f"USR-ROOT-{secrets.token_hex(6)}",
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
                session.add(root_user)
                await session.flush()

            root_id = root_user.id
            await session.execute(
                text(
                    "INSERT INTO schema_meta (key, value) VALUES ('root_admin_id', :value) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                ),
                {"value": root_id},
            )

        username_owner = await session.scalar(
            select(User.id).where(User.username == username, User.id != root_id).limit(1)
        )
        if username_owner:
            raise RuntimeError(
                f"ADMIN_USER '{username}' ya pertenece a otra cuenta; cambia ADMIN_USER "
                "o resuelve el usuario duplicado antes de iniciar."
            )

        root_user.username = username
        root_user.role = "admin"
        root_user.is_active = True
        if not verify_password(root_user.password_hash, password):
            root_user.password_hash = hash_password(password)
        await session.commit()

    logger.info("Cuenta administradora root sincronizada desde backend/.env (%s)", username)


async def run_migrations() -> None:
    """Añade columnas/tablas nuevas y prepara la autenticación v2."""
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        existing = await _columns(conn, "devices")
        for column, ddl in DEVICE_COLUMNS.items():
            if column not in existing:
                await conn.exec_driver_sql(
                    f"ALTER TABLE devices ADD COLUMN {column} {ddl}"
                )
                logger.info("Columna añadida: devices.%s", column)

        # La autenticación antigua guardaba un token provisional en key_hash.
        # Una única vez se invalida para exigir re-vinculación con challenge-response.
        if await _meta_get(conn, "auth_v2_migrated") != "1":
            await conn.exec_driver_sql(
                "UPDATE devices SET status = 'PENDING_CLAIM', "
                "key_hash = NULL, owner_id = NULL"
            )
            await _meta_set(conn, "auth_v2_migrated", "1")
            logger.info("Dispositivos existentes marcados como PENDING_CLAIM")

    await _bootstrap_admin()
