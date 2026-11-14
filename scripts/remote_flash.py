#!/usr/bin/env python3
"""Notifica al backend que se compiló un firmware local.

Solo envía device_id, key_hash y versión del firmware.
No sube binarios, no envía WiFi ni contraseñas.

Uso desde flash.sh:
    python3 scripts/remote_flash.py \
        --host <IP:PUERTO> \
        --username <usuario> \
        --password <contraseña> \
        --device-id <ID> \
        --key-hash <HASH_SHA256> \
        --firmware-version <versión> \
        [--device-name <nombre>] \
        [--device-location <ubicación>]
"""

import argparse
import asyncio
import json
import sys
import uuid

try:
    import websockets
except ImportError:
    print("ERROR: Falta la libreria 'websockets'. Instálala con: pip install websockets", file=sys.stderr)
    sys.exit(1)


async def notify_firmware_compiled(
    host: str,
    username: str,
    password: str,
    device_id: str,
    key_hash: str,
    firmware_version: str,
    device_name: str = None,
    device_location: str = None,
):
    """Conecta al backend y notifica que se compiló firmware para un dispositivo."""

    # Construir URL WebSocket con puerto 8765 por defecto
    if host.startswith(("ws://", "wss://")):
        ws_url = f"{host}/ws/panel"
    else:
        # Si no hay puerto especificado, agregar 8765 por defecto
        if ":" not in host:
            host = f"{host}:8765"
        ws_url = f"ws://{host}/ws/panel"

    print(f"Conectando a {ws_url}...")

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
        except asyncio.TimeoutError:
            print("ERROR: Tiempo de espera agotado al iniciar sesión.", file=sys.stderr)
            sys.exit(1)

        if not data.get("ok"):
            error = data.get("error") or data.get("message") or "Login fallido"
            print(f"ERROR: No se pudo iniciar sesión: {error}", file=sys.stderr)
            sys.exit(1)

        print("Sesión iniciada correctamente.")

        # --- Notificar compilación ---
        print(f"Notificando compilación para dispositivo {device_id}...")
        request_id = str(uuid.uuid4())
        notify_msg = json.dumps({
            "event": "firmware_compiled",
            "request_id": request_id,
            "device_id": device_id,
            "key_hash": key_hash,
            "firmware_version": firmware_version,
        })
        if device_name:
            notify_msg = json.dumps({
                "event": "firmware_compiled",
                "request_id": request_id,
                "device_id": device_id,
                "key_hash": key_hash,
                "firmware_version": firmware_version,
                "device_name": device_name,
            })
        if device_location:
            msg_dict = json.loads(notify_msg)
            msg_dict["device_location"] = device_location
            notify_msg = json.dumps(msg_dict)

        await ws.send(notify_msg)

        # Esperar respuesta
        data = None
        try:
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=15)
                msg = json.loads(response)
                if msg.get("request_id") == request_id:
                    data = msg
                    break
        except asyncio.TimeoutError:
            print("ERROR: Tiempo de espera agotado al notificar compilación.", file=sys.stderr)
            sys.exit(1)

        if data.get("event") == "error":
            error = data.get("message") or data.get("error") or "Error al notificar"
            print(f"ERROR: {error}", file=sys.stderr)
            sys.exit(1)

        if data.get("event") == "firmware_compiled_result" and data.get("ok"):
            print(f"Compilación notificada: dispositivo {data.get('device_id')} v{data.get('firmware_version')}")
        else:
            print(f"ERROR: Respuesta inesperada: {data}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Notifica al backend de DispWatter que se compiló firmware local."
    )
    parser.add_argument("--host", required=True, help="Host del backend (ej: 192.168.1.100:8765)")
    parser.add_argument("--username", required=True, help="Usuario del panel")
    parser.add_argument("--password", required=True, help="Contraseña del panel")
    parser.add_argument("--device-id", required=True, help="ID del dispositivo")
    parser.add_argument("--key-hash", required=True, help="Hash SHA256 del secreto (id:secret)")
    parser.add_argument("--firmware-version", required=True, help="Versión del firmware compilado")
    parser.add_argument("--device-name", default=None, help="Nombre del dispositivo")
    parser.add_argument("--device-location", default=None, help="Ubicación del dispositivo")

    args = parser.parse_args()

    asyncio.run(notify_firmware_compiled(
        host=args.host,
        username=args.username,
        password=args.password,
        device_id=args.device_id,
        key_hash=args.key_hash,
        firmware_version=args.firmware_version,
        device_name=args.device_name,
        device_location=args.device_location,
    ))


if __name__ == "__main__":
    main()
