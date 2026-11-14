"""Migraciones idempotentes para bases de datos DispWatter existentes."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime

from sqlalchemy import select, text

from backend.database.connect import AsyncSessionLocal, engine
from backend.database.models import User

logger = logging.getLogger("DispWatter.Migrations")

USER_COLUMNS = {
    "email": "TEXT NOT NULL DEFAULT ''",
    "is_verified": "BOOLEAN NOT NULL DEFAULT 0",
}

TANK_CONFIG_COLUMNS = {
    "min_relay_off_min": "FLOAT NOT NULL DEFAULT 3.0",
    "overflow_protection": "BOOLEAN NOT NULL DEFAULT 1",
    "menu_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "wifi_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "device_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "pump_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "sensor_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "firmware_lock": "BOOLEAN NOT NULL DEFAULT 0",
    "security_lock": "BOOLEAN NOT NULL DEFAULT 0",
}

DEVICE_COLUMNS = {
    "last_seen": "DATETIME",
    "last_rssi": "INTEGER",
    "last_ip": "TEXT",
    "wake_reason": "TEXT",
    "serial_number": "TEXT",
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
                    email=f"{username}@local",
                    password_hash=hash_password(password),
                    role="admin",
                    is_active=True,
                    is_verified=True,
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
        # Ensure email is set for users created before email column was added
        if not root_user.email:
            root_user.email = f"{username}@local"
        root_user.is_verified = True
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

        # --- devices columns ---
        existing = await _columns(conn, "devices")
        for column, ddl in DEVICE_COLUMNS.items():
            if column not in existing:
                await conn.exec_driver_sql(
                    f"ALTER TABLE devices ADD COLUMN {column} {ddl}"
                )
                logger.info("Columna añadida: devices.%s", column)

        # --- users columns ---
        if await _meta_get(conn, "users_v2_migrated") != "1":
            existing_users = await _columns(conn, "users")
            for column, ddl in USER_COLUMNS.items():
                if column not in existing_users:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE users ADD COLUMN {column} {ddl}"
                    )
                    logger.info("Columna añadida: users.%s", column)
            # Set default email for existing users based on username
            await conn.exec_driver_sql(
                "UPDATE users SET email = username || '@local' WHERE email = '' OR email IS NULL"
            )
            # Mark admin as verified by default
            await conn.exec_driver_sql(
                "UPDATE users SET is_verified = 1 WHERE role = 'admin'"
            )
            await _meta_set(conn, "users_v2_migrated", "1")
            logger.info("Tabla users actualizada con email e is_verified")

        # --- tank_configs columns (always check, no flag — columns are idempotent) ---
        existing_tank = await _columns(conn, "tank_configs")
        for column, ddl in TANK_CONFIG_COLUMNS.items():
            if column not in existing_tank:
                await conn.exec_driver_sql(
                    f"ALTER TABLE tank_configs ADD COLUMN {column} {ddl}"
                )
                logger.info("Columna añadida: tank_configs.%s", column)
        if await _meta_get(conn, "tank_config_v2_migrated") != "1":
            await _meta_set(conn, "tank_config_v2_migrated", "1")
        logger.info("Tabla tank_configs actualizada con protecciones de bomba")

        # --- New tables ---
        # email_verifications
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS email_verifications ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "email TEXT NOT NULL,"
            "user_id TEXT,"
            "token TEXT UNIQUE NOT NULL,"
            "expires_at DATETIME NOT NULL,"
            "used BOOLEAN NOT NULL DEFAULT 0,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)"
        )
        logger.info("Tabla email_verifications lista")

        # device_permissions
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS device_permissions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "device_id TEXT NOT NULL,"
            "user_id TEXT NOT NULL,"
            "role TEXT NOT NULL DEFAULT 'viewer',"
            "granted_by TEXT,"
            "granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "UNIQUE(device_id, user_id),"
            "FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,"
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,"
            "FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL)"
        )
        logger.info("Tabla device_permissions lista")

        # lcd_configs
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS lcd_configs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "device_id TEXT UNIQUE NOT NULL,"
            "line0_format TEXT NOT NULL DEFAULT 'percent',"
            "line1_format TEXT NOT NULL DEFAULT 'liters',"
            "scroll_speed INTEGER NOT NULL DEFAULT 200,"
            "scroll_pause INTEGER NOT NULL DEFAULT 3,"
            "distance_unit TEXT NOT NULL DEFAULT 'cm',"
            "custom_text0 TEXT,"
            "custom_text1 TEXT,"
            "show_scroll0 BOOLEAN NOT NULL DEFAULT 1,"
            "show_scroll1 BOOLEAN NOT NULL DEFAULT 1,"
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE)"
        )
        logger.info("Tabla lcd_configs lista")

        # device_permissions granular columns
        if await _meta_get(conn, "device_permissions_v2_migrated") != "1":
            GRANULAR_COLS = {
                "view_telemetry": "BOOLEAN NOT NULL DEFAULT 1",
                "control_pump": "BOOLEAN NOT NULL DEFAULT 0",
                "auto_refill": "BOOLEAN NOT NULL DEFAULT 0",
                "configure_tank": "BOOLEAN NOT NULL DEFAULT 0",
                "reboot_device": "BOOLEAN NOT NULL DEFAULT 0",
                "factory_reset": "BOOLEAN NOT NULL DEFAULT 0",
                "delete_device": "BOOLEAN NOT NULL DEFAULT 0",
                "view_history": "BOOLEAN NOT NULL DEFAULT 1",
                "view_audit": "BOOLEAN NOT NULL DEFAULT 0",
                "ota_update": "BOOLEAN NOT NULL DEFAULT 0",
                "manage_lcd": "BOOLEAN NOT NULL DEFAULT 0",
                "change_password": "BOOLEAN NOT NULL DEFAULT 1",
            }
            existing_perm = await _columns(conn, "device_permissions")
            for column, ddl in GRANULAR_COLS.items():
                if column not in existing_perm:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE device_permissions ADD COLUMN {column} {ddl}"
                    )
                    logger.info("Columna añadida: device_permissions.%s", column)
            await _meta_set(conn, "device_permissions_v2_migrated", "1")
            logger.info("Tabla device_permissions actualizada con toggles granulares")

        # telemetry index for history queries
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_telemetry_device_created "
            "ON telemetry(device_id, created_at DESC)"
        )
        logger.info("Índice telemetry(device_id, created_at) listo")

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
