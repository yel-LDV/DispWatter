import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
LOGS_DIR = PROJECT_ROOT / "logs"

# Cargar variables de entorno
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8765"))
    PANEL_PORT: int = int(os.getenv("PANEL_PORT", "3000"))
    DB_NAME: str = os.getenv("DB_NAME", "data.db")
    MAX_MESSAGE_SIZE: int = int(os.getenv("MAX_MESSAGE_SIZE", "2048"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Autenticación de usuarios
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "12"))
    PANEL_ORIGINS: str = os.getenv("PANEL_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_WINDOW_SECONDS: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
    PANEL_AUTH_TIMEOUT: int = int(os.getenv("PANEL_AUTH_TIMEOUT", "10"))

    # Bootstrap del primer administrador
    ADMIN_USER: str = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # Helper de systemd
    DISPWATTER_CTL: str = os.getenv("DISPWATTER_CTL", "/usr/local/bin/dispwatter-ctl")
    SYSTEM_ACTIONS_ENABLED: bool = _env_bool("SYSTEM_ACTIONS_ENABLED", True)

    # Retención de telemetría
    TELEMETRY_RETENTION_HOURS: int = int(os.getenv("TELEMETRY_RETENTION_HOURS", "24"))

    # Rutas absolutas
    BASE_DIR: Path = BASE_DIR
    PROJECT_ROOT: Path = PROJECT_ROOT
    PANEL_DIR: Path = PROJECT_ROOT / "panel"
    LOGS_DIR: Path = LOGS_DIR
    DB_PATH: Path = BASE_DIR / DB_NAME
    AUDIT_LOG_FILE: Path = LOGS_DIR / "audit.log"
    BACKEND_LOG_FILE: Path = LOGS_DIR / "backend.log"

    @property
    def DATABASE_URL(self) -> str:
        return f"sqlite+aiosqlite:///{self.DB_PATH.as_posix()}"

    @property
    def PANEL_ORIGINS_LIST(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.PANEL_ORIGINS.split(",") if item.strip()]


settings = Settings()
LOGS_DIR.mkdir(parents=True, exist_ok=True)

if not settings.JWT_SECRET:
    raise RuntimeError(
        "Falta JWT_SECRET en backend/.env. Copia backend/.env.example y genera uno con: "
        "openssl rand -hex 48"
    )
