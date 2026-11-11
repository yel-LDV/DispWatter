import asyncio
import time
import sys
from sqlalchemy import select, func
from backend.config import settings
from backend.database.connect import init_db, get_db
from backend.database.models import Device, TankConfig, Telemetry, AuditLog
from backend.security.auth import (
    compute_device_proof,
    hash_credentials,
    record_audit,
    verify_device_proof,
)

GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

async def run_tests():
    print(f"\n{BLUE}=========================================={RESET}")
    print(f"{BLUE}     EJECUTANDO TEST DE BASE DE DATOS     {RESET}")
    print(f"{BLUE}=========================================={RESET}\n")

    start_time = time.time()
    errors = 0

    # 1. Inicialización de Tablas
    try:
        await init_db()
        print(f"[{GREEN}OK{RESET}] Conexión con SQLite e inicialización de tablas.")
    except Exception as e:
        print(f"[{RED}FAIL{RESET}] Error inicializando tablas: {e}")
        return 1

    # 2. Test de Criptografía
    test_id = "TEST-DEVICE-01"
    test_pass = "secreto_seguro_123"
    expected_hash = hash_credentials(test_id, test_pass)
    nonce = "nonce-de-prueba"
    proof = compute_device_proof(expected_hash, nonce)
    if not verify_device_proof(expected_hash, nonce, proof):
        print(f"[{RED}FAIL{RESET}] Verificación HMAC del dispositivo falló.")
        errors += 1
    else:
        print(f"[{GREEN}OK{RESET}] HMAC-SHA256 de dispositivo verificado.")
        print(f"[{GREEN}OK{RESET}] Hash SHA-256 de credenciales generado: {expected_hash[:16]}...")

    # 3. Test de Inserción de Dispositivo
    async with get_db() as session:
        # Limpiar previo de test si existía
        prev = await session.execute(select(Device).where(Device.id == test_id))
        if prev_dev := prev.scalar_one_or_none():
            await session.delete(prev_dev)
            await session.commit()

        # Insertar
        dev = Device(
            id=test_id,
            name="Bebedero de Pruebas",
            key_hash=expected_hash,
            status="CLAIMED",
            owner_id="OWNER-TEST"
        )
        session.add(dev)

        cfg = TankConfig(
            device_id=test_id,
            capacity_liters=60.0,
            bottom_dist_mm=1000.0,
            mirror_dist_mm=150.0,
            min_level_percent=20.0,
            max_level_percent=95.0,
            auto_refill=True
        )
        session.add(cfg)
        await session.commit()
        print(f"[{GREEN}OK{RESET}] Inserción de Dispositivo y TankConfig completada.")

    # 4. Test de Telemetría
    async with get_db() as session:
        telemetry_entry = Telemetry(
            device_id=test_id,
            distance_mm=300.0,
            water_percent=82.3,
            water_liters=49.4,
            relay_state=False
        )
        session.add(telemetry_entry)
        await session.commit()
        print(f"[{GREEN}OK{RESET}] Inserción de registro de telemetría completada.")

    # 5. Test de Consultas y Auditoría
    async with get_db() as session:
        # Contar telemetría
        tel_count = await session.scalar(select(func.count()).select_from(Telemetry).where(Telemetry.device_id == test_id))
        if tel_count >= 1:
            print(f"[{GREEN}OK{RESET}] Consulta de telemetría verificada ({tel_count} registro(s)).")
        else:
            print(f"[{RED}FAIL{RESET}] No se encontró la telemetría insertada.")
            errors += 1

        # Registrar evento de auditoría
        await record_audit("TEST_SUITE_RUN", device_id=test_id, actor="TEST_RUNNER", details="Validación automática ejecutada")

        # Verificar auditoría
        audit_res = await session.execute(select(AuditLog).where(AuditLog.action == "TEST_SUITE_RUN"))
        if audit_res.scalar_one_or_none():
            print(f"[{GREEN}OK{RESET}] Registro y persistencia de Auditoría verificados.")
        else:
            print(f"[{RED}FAIL{RESET}] Registro de auditoría no encontrado.")
            errors += 1

    elapsed = time.time() - start_time
    print(f"\n------------------------------------------")
    if errors == 0:
        print(f"{GREEN}✔ TODOS LOS TESTS PASARON CON ÉXITO ({elapsed:.2f}s){RESET}\n")
        return 0
    else:
        print(f"{RED}✖ SE ENCONTRARON {errors} FALLO(S) ({elapsed:.2f}s){RESET}\n")
        return 1

if __name__ == "__main__":
    code = asyncio.run(run_tests())
    sys.exit(code)
