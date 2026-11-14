#!/usr/bin/env python3
"""Remote flash helper — sube firmware al backend y opcionalmente inicia OTA.

Uso desde flash.sh:
    python3 scripts/remote_flash.py \
        --host <IP:PUERTO> \
        --username <usuario> \
        --password <contraseña> \
        --firmware <ruta_al_bin> \
        [--device-id <ID>] \
        [--name <nombre>] \
        [--version <versión>] \
        [--description <descripción>] \
        [--type <stable|experimental|custom>] \
        [--ota]

Si --ota se pasa y --device-id está definido, inicia la OTA después de subir.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid

try:
    import websockets
except ImportError:
    print("ERROR: Falta la libreria 'websockets'. Instálala con: pip install websockets", file=sys.stderr)
    sys.exit(1)


def read_firmware(path: str) -> tuple[str, str, int]:
    """Lee el binario y retorna (hex_string, sha256, size)."""
    with open(path, "rb") as f:
        binary = f.read()
    if not binary:
        print("ERROR: El archivo de firmware está vacío.", file=sys.stderr)
        sys.exit(1)
    return binary.hex(), hashlib.sha256(binary).hexdigest(), len(binary)


async def remote_flash(
    host: str,
    username: str,
    password: str,
    firmware_path: str,
    device_id: str = None,
    name: str = None,
    version: str = None,
    description: str = None,
    firmware_type: str = "custom",
    do_ota: bool = False,
):
    """Conecta al backend, sube el firmware y opcionalmente inicia OTA."""

    # Construir URL WebSocket
    if not host.startswith(("ws://", "wss://")):
        # Detectar si es HTTPS/WS basado en puerto o asumir ws
        ws_url = f"ws://{host}/ws/panel"
    else:
        ws_url = f"{host}/ws/panel"

    print(f"Conectando a {ws_url}...")

    # Leer firmware
    firmware_hex, sha256, size = read_firmware(firmware_path)
    print(f"Firmware: {firmware_path} ({size} bytes, sha256={sha256[:12]}...)")

    # Nombre por defecto
    if not name:
        name = os.path.basename(firmware_path).replace(".bin", "")

    # Versión por defecto
    if not version:
        version = "1.0.0"

    async with websockets.connect(ws_url) as ws:
        # --- Login ---
        print(f"Iniciando sesión como '{username}'...")
        login_msg = json.dumps({
            "event": "login",
            "username": username,
            "password": password,
        })
        await ws.send(login_msg)

        # Esperar login_result (filtrar otros mensajes)
        data = None
        try:
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(response)
                if msg.get("event") == "login_result":
                    data = msg
                    break
                # Ignorar otros mensajes (sync, etc.)
        except asyncio.TimeoutError:
            print("ERROR: Tiempo de espera agotado al iniciar sesión.", file=sys.stderr)
            sys.exit(1)

        if not data.get("ok"):
            error = data.get("error") or data.get("message") or "Login fallido"
            print(f"ERROR: No se pudo iniciar sesión: {error}", file=sys.stderr)
            sys.exit(1)

        print("Sesión iniciada correctamente.")

        # --- Upload firmware ---
        print("Subiendo firmware al backend...")
        upload_id = str(uuid.uuid4())
        upload_msg = json.dumps({
            "event": "upload_firmware",
            "request_id": upload_id,
            "name": name,
            "version": version,
            "binary_hex": firmware_hex,
            "description": description,
            "firmware_type": firmware_type,
        })
        await ws.send(upload_msg)

        # Esperar respuesta (filtrar hasta encontrar la con nuestro request_id)
        data = None
        try:
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=60)
                msg = json.loads(response)
                if msg.get("request_id") == upload_id:
                    data = msg
                    break
                # Ignorar otros mensajes (sync, broadcast, etc.)
        except asyncio.TimeoutError:
            print("ERROR: Tiempo de espera agotado al subir firmware.", file=sys.stderr)
            sys.exit(1)

        if data.get("event") == "error":
            error = data.get("message") or data.get("error") or "Error al subir"
            print(f"ERROR: {error}", file=sys.stderr)
            sys.exit(1)

        if data.get("event") == "firmware_upload_result" and data.get("ok"):
            fw = data.get("firmware", {})
            print(f"Firmware subido: {fw.get('name')} v{fw.get('version')} (id={fw.get('id')})")
            firmware_id = fw.get("id")
        else:
            print(f"ERROR: Respuesta inesperada al subir firmware: {data}", file=sys.stderr)
            sys.exit(1)

        # --- OTA opcional ---
        if do_ota and device_id:
            print(f"Iniciando OTA en dispositivo {device_id}...")
            ota_id = str(uuid.uuid4())
            ota_msg = json.dumps({
                "event": "start_ota_from_upload",
                "request_id": ota_id,
                "device_id": device_id,
                "firmware_id": firmware_id,
            })
            await ws.send(ota_msg)

            # Escuchar progreso OTA (filtrar por request_id)
            print("Esperando progreso de OTA...")
            while True:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=120)
                    msg = json.loads(response)
                    # Filtrar solo los mensajes de este request
                    if msg.get("request_id") != ota_id:
                        continue
                    status = msg.get("status", "")
                    progress = msg.get("progress", "")
                    event = msg.get("event", "")

                    if event == "ota_progress":
                        if status == "complete":
                            print("OTA completada exitosamente.")
                            break
                        elif status == "error":
                            error = msg.get("error", "Error desconocido")
                            print(f"ERROR en OTA: {error}", file=sys.stderr)
                            sys.exit(1)
                        elif status == "preparing":
                            print(f"Preparando OTA para versión {msg.get('version', '?')}...")
                        elif status == "pushing":
                            print(f"Enviando firmware: {progress}%")
                        elif status == "verifying":
                            print(f"Verificando firmware: {progress}%")
                        else:
                            print(f"  Estado: {status}")
                    elif event == "error":
                        error = msg.get("message") or msg.get("error") or "Error desconocido"
                        print(f"ERROR: {error}", file=sys.stderr)
                        sys.exit(1)
                except asyncio.TimeoutError:
                    print("ERROR: Tiempo de espera agotado durante OTA.", file=sys.stderr)
                    sys.exit(1)

        elif do_ota and not device_id:
            print("AVISO: --ota requiere --device-id. Solo se subió el firmware.")
            print("Puedes iniciar OTA desde el panel web.")


def main():
    parser = argparse.ArgumentParser(
        description="Sube firmware al backend de DispWatter y opcionalmente inicia OTA."
    )
    parser.add_argument("--host", required=True, help="Host del backend (ej: 192.168.1.100:8765)")
    parser.add_argument("--username", required=True, help="Usuario del panel")
    parser.add_argument("--password", required=True, help="Contraseña del panel")
    parser.add_argument("--firmware", required=True, help="Ruta al archivo .bin del firmware")
    parser.add_argument("--device-id", default=None, help="ID del dispositivo para OTA")
    parser.add_argument("--name", default=None, help="Nombre del firmware (default: nombre del archivo)")
    parser.add_argument("--version", default=None, help="Versión del firmware (default: 1.0.0)")
    parser.add_argument("--description", default=None, help="Descripción del firmware")
    parser.add_argument("--type", default="custom", choices=["stable", "experimental", "custom"],
                        help="Tipo de firmware (default: custom)")
    parser.add_argument("--ota", action="store_true", help="Iniciar OTA después de subir (requiere --device-id)")

    args = parser.parse_args()

    if not os.path.isfile(args.firmware):
        print(f"ERROR: No se encuentra el archivo: {args.firmware}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(remote_flash(
        host=args.host,
        username=args.username,
        password=args.password,
        firmware_path=args.firmware,
        device_id=args.device_id,
        name=args.name,
        version=args.version,
        description=args.description,
        firmware_type=args.type,
        do_ota=args.ota,
    ))


if __name__ == "__main__":
    main()
