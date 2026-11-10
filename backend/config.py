import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
LOGS_DIR = PROJECT_ROOT / "logs"

# Cargar variables de entorno
load_dotenv(BASE_DIR / ".env")

class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8765"))
    PANEL_PORT: int = int(os.getenv("PANEL_PORT", "3000"))
    TOKEN: str = os.getenv("TOKEN", "1234567890")
    DB_NAME: str = os.getenv("DB_NAME", "data.db")
    MAX_MESSAGE_SIZE: int = int(os.getenv("MAX_MESSAGE_SIZE", "2048"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

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

settings = Settings()
LOGS_DIR.mkdir(parents=True, exist_ok=True)
