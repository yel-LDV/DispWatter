import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.config import settings
from backend.database.models import Base

# Motor de base de datos asíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL == "DEBUG"),
    future=True
)

# Fábrica de sesiones asíncronas
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def init_db() -> None:
    """Crea todas las tablas si no existen y aplica migraciones."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from backend.database.migrations import run_migrations

    await run_migrations()

async def reset_db() -> None:
    """Elimina todas las tablas y las vuelve a crear."""
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP TABLE IF EXISTS schema_meta")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from backend.database.migrations import run_migrations

    await run_migrations()

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Generador de contexto para sesiones de base de datos."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
