import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
LOGS_DIR = PROJECT_ROOT / "logs"
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"


def _initialize_env_file() -> None:
    """Create a private first-run .env with a random JWT key/admin password."""
    if ENV_PATH.exists():
        return
    if not ENV_EXAMPLE_PATH.is_file():
        raise RuntimeError(f"No existe la plantilla de configuración: {ENV_EXAMPLE_PATH}")

    lines = ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    generated_password = secrets.token_urlsafe(24)
    replacements = {
        "JWT_SECRET": secrets.token_hex(48),
        "ADMIN_USER": "admin",
        "ADMIN_PASSWORD": generated_password,
    }
    output = []
    for line in lines:
        key, separator, _value = line.partition("=")
        if separator and key in replacements:
            line = f"{key}={replacements[key]}"
        output.append(line)

    content = "\n".join(output) + "\n"
    try:
        fd = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process initialized the configuration concurrently.
        return
    with os.fdopen(fd, "w", encoding="utf-8") as env_file:
        env_file.write(content)

    print(
        f"[CONFIG] Se creó {ENV_PATH} con una clave JWT y contraseña admin aleatorias. "
        "Consulta ADMIN_USER y ADMIN_PASSWORD en ese archivo para iniciar sesión."
    )


_initialize_env_file()
load_dotenv(ENV_PATH)


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

    # Cuenta administradora sincronizada desde backend/.env al iniciar.
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

if len(settings.JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET debe contener al menos 32 caracteres en backend/.env")
if not settings.ADMIN_USER.strip() or len(settings.ADMIN_USER.strip()) > 64:
    raise RuntimeError("ADMIN_USER debe tener entre 1 y 64 caracteres en backend/.env")
if not settings.ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD no puede estar vacío en backend/.env")
