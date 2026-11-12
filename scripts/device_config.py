#!/usr/bin/env python3
"""Gestión de la configuración de dispositivos DispWatter.

Uso:
    python3 scripts/device_config.py configure --file hardware/esp32/main/device_config.json
    python3 scripts/device_config.py validate  --file hardware/esp32/main/device_config.json
    python3 scripts/device_config.py to-device --input device_config.json --output data/config.json
    python3 scripts/device_config.py hash      --id WATTER-001 --secret mi-secreto
    python3 scripts/device_config.py show      --file device_config.json

El archivo del host contiene el secreto del dispositivo (claim_secret) y las
contraseñas WiFi. El archivo del dispositivo solo contiene key_hash; nunca el
secreto en claro.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any

SCHEMA = 1
MAX_NETWORKS = 8

ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FW_RE = re.compile(r"^\d+\.\d+\.\d+$")
HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252})$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

DEFAULT_SAMPLING = {"interval_ms": 2000, "retry_ms": 5000}
DEFAULT_POWER = {"wake_pin": 33, "wake_active_low": True, "sleep_timer_min": 60}
DEFAULT_SAFETY = {"max_relay_on_min": 10, "max_offline_min": 5}
DEFAULT_RELAY = {"active_low": False}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def die(message: str, code: int = 2) -> None:
    print(f"\n[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def sha256_credentials(device_id: str, secret: str) -> str:
    raw = f"{device_id}:{secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"No existe el archivo: {path}")
    except json.JSONDecodeError as exc:
        die(f"JSON inválido en {path}: {exc}")


def save_json(path: Path, data: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def normalize(cfg: dict[str, Any]) -> dict[str, Any]:
    cfg.setdefault("schema", SCHEMA)
    cfg.setdefault("sampling", dict(DEFAULT_SAMPLING))
    cfg.setdefault("power", dict(DEFAULT_POWER))
    cfg.setdefault("safety", dict(DEFAULT_SAFETY))
    cfg.setdefault("relay", dict(DEFAULT_RELAY))
    for key, default in DEFAULT_SAMPLING.items():
        cfg["sampling"].setdefault(key, default)
    for key, default in DEFAULT_POWER.items():
        cfg["power"].setdefault(key, default)
    for key, default in DEFAULT_SAFETY.items():
        cfg["safety"].setdefault(key, default)
    cfg.setdefault("backend", {})
    cfg["backend"].setdefault("path", "/ws/device")
    cfg["backend"].setdefault("tls", False)
    cfg.setdefault("device", {})
    cfg.setdefault("wifi", [])
    return cfg


def validate(cfg: dict[str, Any], *, device_mode: bool = False) -> list[str]:
    errors: list[str] = []
    cfg = normalize(cfg)

    if cfg.get("schema") != SCHEMA:
        errors.append(f"schema debe ser {SCHEMA}")

    dev = cfg.get("device") or {}
    if not ID_RE.match(str(dev.get("id", ""))):
        errors.append("device.id debe cumplir ^[A-Za-z0-9._-]{1,64}$")
    for field in ("name", "location"):
        value = str(dev.get(field, "")).strip()
        if not value:
            errors.append(f"device.{field} es obligatorio")
        elif len(value) > 128:
            errors.append(f"device.{field} no puede superar 128 caracteres")
    if not FW_RE.match(str(dev.get("firmware", ""))):
        errors.append("device.firmware debe tener formato X.Y.Z")

    key_hash = str(dev.get("key_hash", ""))
    if not HEX64_RE.match(key_hash):
        errors.append("device.key_hash debe ser 64 caracteres hexadecimales")

    if not device_mode:
        secret = str(dev.get("claim_secret", ""))
        if len(secret) < 16:
            errors.append("device.claim_secret debe tener al menos 16 caracteres")
        elif HEX64_RE.match(key_hash) and key_hash != sha256_credentials(dev.get("id", ""), secret):
            errors.append("device.key_hash no coincide con SHA256(id:claim_secret)")

    backend = cfg.get("backend") or {}
    host = str(backend.get("host", ""))
    if not HOST_RE.match(host):
        errors.append("backend.host debe ser una IP o hostname sin esquema ni ruta")
    port = backend.get("port")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        errors.append("backend.port debe ser un entero entre 1 y 65535")
    path = str(backend.get("path", ""))
    if not path.startswith("/"):
        errors.append("backend.path debe comenzar por /")

    wifi = cfg.get("wifi")
    if not isinstance(wifi, list) or not (1 <= len(wifi) <= MAX_NETWORKS):
        errors.append(f"wifi debe tener entre 1 y {MAX_NETWORKS} redes")
    else:
        seen: set[str] = set()
        for index, entry in enumerate(wifi):
            if not isinstance(entry, dict):
                errors.append(f"wifi[{index}] debe ser un objeto")
                continue
            ssid = str(entry.get("ssid", ""))
            password = str(entry.get("password", ""))
            if not ssid:
                errors.append(f"wifi[{index}].ssid está vacío")
            elif len(ssid.encode("utf-8")) > 31:
                errors.append(f"wifi[{index}].ssid supera 31 bytes")
            if ssid in seen:
                errors.append(f"wifi[{index}].ssid está duplicado: {ssid}")
            seen.add(ssid)
            if password and not (8 <= len(password) <= 63):
                errors.append(f"wifi[{index}].password debe tener 8..63 caracteres o estar vacía")

    sampling = cfg.get("sampling") or {}
    if not isinstance(sampling.get("interval_ms"), int) or sampling["interval_ms"] < 500:
        errors.append("sampling.interval_ms debe ser >= 500")
    if not isinstance(sampling.get("retry_ms"), int) or sampling["retry_ms"] < 1000:
        errors.append("sampling.retry_ms debe ser >= 1000")

    power = cfg.get("power") or {}
    if not isinstance(power.get("wake_pin"), int) or not (0 <= power["wake_pin"] <= 39):
        errors.append("power.wake_pin debe ser un GPIO válido")
    if not isinstance(power.get("sleep_timer_min"), int) or power["sleep_timer_min"] < 1:
        errors.append("power.sleep_timer_min debe ser >= 1")

    safety = cfg.get("safety") or {}
    if not isinstance(safety.get("max_relay_on_min"), int) or safety["max_relay_on_min"] < 1:
        errors.append("safety.max_relay_on_min debe ser >= 1")
    if not isinstance(safety.get("max_offline_min"), int) or safety["max_offline_min"] < 1:
        errors.append("safety.max_offline_min debe ser >= 1")

    relay = cfg.get("relay") or {}
    if not isinstance(relay.get("active_low"), bool):
        errors.append("relay.active_low debe ser true (módulo activo en LOW) o false (activo en HIGH)")

    return errors


# ---------------------------------------------------------------------------
# Prompts interactivos
# ---------------------------------------------------------------------------

def ask(text: str, default: str | None = None, *, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default not in (None, "") else ""
        value = input(f"  {text}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        if value or not required:
            return value
        print("    Este campo es obligatorio.")


def ask_yes_no(text: str, default: bool = False) -> bool:
    hint = "S/n" if default else "s/N"
    while True:
        value = input(f"  {text} ({hint}): ").strip().lower()
        if not value:
            return default
        if value in ("s", "si", "sí", "y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("    Responde s o n.")


def ask_int(text: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        raw = ask(f"{text} ({minimum}..{maximum})", str(default))
        try:
            value = int(raw)
        except ValueError:
            print("    Introduce un número entero.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"    Debe estar entre {minimum} y {maximum}.")


def ask_secret(text: str) -> str:
    while True:
        value = getpass.getpass(f"  {text}: ")
        if value:
            return value
        print("    No puede estar vacío.")


def show_networks(wifi: list[dict[str, str]]) -> None:
    if not wifi:
        print("  (sin redes guardadas)")
        return
    for index, entry in enumerate(wifi, 1):
        ssid = entry.get("ssid", "")
        has_password = "sí" if entry.get("password") else "no"
        print(f"  {index}. {ssid}  (contraseña: {has_password})")


def prompt_wifi_password() -> str:
    while True:
        value = getpass.getpass("    Contraseña WiFi (vacío = red abierta): ")
        if not value:
            if ask_yes_no("    ¿Confirmas que la red es abierta?", False):
                return ""
            continue
        if 8 <= len(value) <= 63:
            return value
        print("    La contraseña debe tener entre 8 y 63 caracteres.")


def prompt_network(existing: bool = False) -> dict[str, str] | None:
    ssid = ask("SSID", required=True)
    if existing and not ssid:
        return None
    if len(ssid.encode("utf-8")) > 31:
        print("    El SSID no puede superar 31 bytes.")
        return prompt_network(existing)
    password = prompt_wifi_password()
    return {"ssid": ssid, "password": password}


def rebuild_networks() -> list[dict[str, str]]:
    print("\n  Introduce las redes en orden de prioridad.")
    print("  La primera es obligatoria. Deja el SSID vacío para terminar.")
    networks: list[dict[str, str]] = []
    while len(networks) < MAX_NETWORKS:
        if networks and not ask_yes_no(f"¿Añadir la red {len(networks) + 1}?", False):
            break
        label = "SSID de la red 1 (obligatoria)" if not networks else f"SSID de la red {len(networks) + 1} (vacío = terminar)"
        ssid = ask(label, required=not networks)
        if not ssid:
            break
        if any(n["ssid"] == ssid for n in networks):
            print("    Esa red ya está en la lista; se omite.")
            continue
        if len(ssid.encode("utf-8")) > 31:
            print("    El SSID no puede superar 31 bytes.")
            continue
        password = prompt_wifi_password()
        networks.append({"ssid": ssid, "password": password})
    if not networks:
        die("Debe existir al menos una red WiFi.")
    return networks


def add_networks(networks: list[dict[str, str]]) -> list[dict[str, str]]:
    print("\n  Añadir redes. Deja el SSID vacío para terminar.")
    while len(networks) < MAX_NETWORKS:
        ssid = ask("SSID (vacío = terminar)")
        if not ssid:
            break
        if any(n["ssid"] == ssid for n in networks):
            print("    Esa red ya está en la lista; se omite.")
            continue
        if len(ssid.encode("utf-8")) > 31:
            print("    El SSID no puede superar 31 bytes.")
            continue
        networks.append({"ssid": ssid, "password": prompt_wifi_password()})
    return networks


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_configure(args: argparse.Namespace) -> int:
    path = Path(args.file)
    existing: dict[str, Any] | None = None
    if path.exists() and not args.reset:
        existing = normalize(load_json(path))
        errors = validate(existing)
        if errors:
            print("[AVISO] La configuración existente tiene errores:")
            for error in errors:
                print(f"  - {error}")
            if not ask_yes_no("¿Continuar y corregirla?", True):
                return 1

    if args.non_interactive:
        if existing is None:
            die("Modo no interactivo: no existe el archivo de configuración.")
        errors = validate(existing)
        if errors:
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        save_json(path, existing)
        print(f"[OK] Configuración validada: {path}")
        return 0

    print("\n============================================================")
    print("  CONFIGURACIÓN DEL DISPOSITIVO DISPWATTER")
    print("============================================================")

    # 1. Redes WiFi
    if existing:
        print("\n[1/4] Redes WiFi guardadas:")
        show_networks(existing.get("wifi", []))
        print("\n  Opciones: [1] Conservar  [2] Añadir  [3] Reemplazar")
        choice = ask("Elige una opción", "1")
        while choice not in ("1", "2", "3"):
            choice = ask("Elige 1, 2 o 3", "1")
        networks = list(existing.get("wifi", []))
        if choice == "2":
            networks = add_networks(networks)
        elif choice == "3":
            networks = rebuild_networks()
    else:
        print("\n[1/4] Redes WiFi")
        networks = rebuild_networks()

    # 2. Backend
    print("\n[2/4] Servidor backend")
    default_host = args.default_host or (existing or {}).get("backend", {}).get("host", "192.168.1.100")
    while True:
        host = ask("IP o hostname del backend", default_host, required=True)
        if HOST_RE.match(host):
            break
        print("    Formato no válido (sin ws:// ni rutas).")
    port = ask_int("Puerto WebSocket", int((existing or {}).get("backend", {}).get("port", 8765)), 1, 65535)

    # 3. Identidad
    print("\n[3/4] Identidad del dispositivo")
    dev = (existing or {}).get("device", {})
    device_id = ask("ID único", dev.get("id", "WATTER-001"), required=True)
    while not ID_RE.match(device_id):
        print("    Solo letras, números, punto, guion y guion bajo (máx. 64).")
        device_id = ask("ID único", dev.get("id", "WATTER-001"), required=True)
    name = ask("Nombre", dev.get("name", "Bebedero Huerto"), required=True)
    location = ask("Ubicación", dev.get("location", "Patio Principal"), required=True)
    firmware = ask("Versión de firmware", dev.get("firmware", "1.0.0"), required=True)
    while not FW_RE.match(firmware):
        print("    Formato X.Y.Z")
        firmware = ask("Versión de firmware", dev.get("firmware", "1.0.0"), required=True)

    # 4. Secreto del dispositivo
    print("\n[4/4] Secreto de vinculación")
    print("  Se usa para reclamar el dispositivo desde el panel.")
    existing_secret = str(dev.get("claim_secret", ""))
    if existing_secret and ask_yes_no("¿Conservar el secreto actual?", True):
        secret = existing_secret
    elif ask_yes_no("¿Generar un secreto aleatorio seguro?", True):
        secret = secrets.token_hex(32)
        print(f"  Secreto generado: {secret}")
        print("  Guárdalo: se muestra solo esta vez y queda en device_config.json.")
    else:
        while True:
            secret = ask_secret("Secreto (mínimo 16 caracteres)")
            if len(secret) >= 16:
                break
            print("    Demasiado corto.")

    config = {
        "schema": SCHEMA,
        "device": {
            "id": device_id,
            "name": name,
            "location": location,
            "firmware": firmware,
            "key_hash": sha256_credentials(device_id, secret),
            "claim_secret": secret,
        },
        "backend": {
            "host": host,
            "port": port,
            "path": "/ws/device",
            "tls": False,
        },
        "wifi": networks,
        "sampling": dict((existing or {}).get("sampling", DEFAULT_SAMPLING)),
        "power": dict((existing or {}).get("power", DEFAULT_POWER)),
        "safety": dict((existing or {}).get("safety", DEFAULT_SAFETY)),
        "relay": dict((existing or {}).get("relay", DEFAULT_RELAY)),
    }
    config = normalize(config)

    errors = validate(config)
    if errors:
        print("\n[ERROR] La configuración no es válida:")
        for error in errors:
            print(f"  - {error}")
        return 1

    save_json(path, config)
    print("\n------------------------------------------------------------")
    print("  RESUMEN")
    print("------------------------------------------------------------")
    print(f"  Archivo:     {path}")
    print(f"  Dispositivo: {device_id}  ({name} @ {location})")
    print(f"  Firmware:    v{firmware}")
    print(f"  Backend:     ws://{host}:{port}/ws/device")
    print(f"  Redes:       {len(networks)}")
    for index, entry in enumerate(networks, 1):
        print(f"    {index}. {entry['ssid']}")
    print("  Secreto:     (guardado en device_config.json)")
    print("------------------------------------------------------------\n")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = normalize(load_json(Path(args.file)))
    errors = validate(cfg, device_mode=args.device)
    if errors:
        print("[ERROR] Configuración inválida:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"[OK] Configuración válida: {args.file}")
    return 0


def cmd_to_device(args: argparse.Namespace) -> int:
    cfg = normalize(load_json(Path(args.input)))
    errors = validate(cfg)
    if errors:
        print("[ERROR] Configuración del host inválida:")
        for error in errors:
            print(f"  - {error}")
        return 1
    device_cfg = json.loads(json.dumps(cfg))
    device_cfg["device"].pop("claim_secret", None)
    errors = validate(device_cfg, device_mode=True)
    if errors:
        print("[ERROR] Configuración del dispositivo inválida:")
        for error in errors:
            print(f"  - {error}")
        return 1
    save_json(Path(args.output), device_cfg)
    print(f"[OK] Configuración del dispositivo generada: {args.output}")
    return 0


def cmd_hash(args: argparse.Namespace) -> int:
    print(sha256_credentials(args.device_id, args.secret))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg = normalize(load_json(Path(args.file)))
    show_networks(cfg.get("wifi", []))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configuración de dispositivos DispWatter")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("configure", help="Configura o actualiza device_config.json")
    p.add_argument("--file", required=True)
    p.add_argument("--default-host", default=None)
    p.add_argument("--reset", action="store_true", help="Ignora la configuración existente")
    p.add_argument("--non-interactive", action="store_true")
    p.set_defaults(func=cmd_configure)

    p = sub.add_parser("validate", help="Valida un JSON")
    p.add_argument("--file", required=True)
    p.add_argument("--device", action="store_true", help="Valida el formato del dispositivo")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("to-device", help="Genera data/config.json sin claim_secret")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_to_device)

    p = sub.add_parser("hash", help="Calcula SHA256(id:secreto)")
    p.add_argument("--id", required=True, dest="device_id")
    p.add_argument("--secret", required=True)
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("show", help="Muestra las redes guardadas")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_show)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
