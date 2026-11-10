import asyncio
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from backend.config import settings
from backend.database.connect import reset_db
from backend.security.auth import record_audit

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

async def main():
    force = ("--force" in sys.argv) or ("-y" in sys.argv)

    print(f"\n{YELLOW}=========================================={RESET}")
    print(f"{YELLOW}   REINICIALIZACIÓN DE BASE DE DATOS      {RESET}")
    print(f"{YELLOW}=========================================={RESET}\n")

    if not force:
        print(f"{RED}ADVERTENCIA:{RESET} Esta acción borrará permanentemente todos los")
        print("dispositivos, historiales de telemetría y configuraciones.\n")
        try:
            confirm = input("¿Estás seguro de continuar? (escribe 'si' para confirmar): ").strip().lower()
        except EOFError:
            confirm = "no"

        if confirm not in ("si", "s", "yes", "y"):
            print("\nOperación cancelada por el usuario.")
            return

    # 1. Crear copia de seguridad antes de borrar
    if settings.DB_PATH.exists():
        backup_dir = settings.BASE_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"data_backup_{timestamp}.db"
        shutil.copy2(settings.DB_PATH, backup_file)
        print(f"[{GREEN}OK{RESET}] Copia de seguridad creada en: {backup_file.name}")

    # 2. Resetear base de datos
    await reset_db()
    print(f"[{GREEN}OK{RESET}] Tablas eliminadas y regeneradas limpias.")

    # 3. Registrar auditoría
    await record_audit(
        action="DB_RESET_EXECUTED",
        actor="CLI_USER",
        details="Reinicio total de base de datos ejecutado con backup previo."
    )
    print(f"[{GREEN}OK{RESET}] Evento de reseteo registrado en auditoría.")

    print(f"\n{GREEN}✔ Base de datos reinicializada exitosamente.{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())
