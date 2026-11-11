# DispWatter — Arquitectura

Sistema de bebedero/dispensador de agua con ESP32, backend WebSocket en Python,
panel web y almacenamiento SQLite.

---

## 1. Visión general

```
┌──────────────────────────────────────────────────────────────┐
│ ESP32                                                        │
│  HC-SR04 ──► muestreo mm ──► telemetría                      │
│  LCD 16x2 I2C ◄── estado + comandos display                  │
│  Relé GPIO4 ◄── set_relay (fail-safe local)                  │
│  LittleFS /config.json ◄── identidad, WiFi, backend          │
│  Deep sleep ◄── temporizador + botón GPIO33                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ ws://…/ws/device
                            │ hello → challenge → auth (HMAC)
┌───────────────────────────▼──────────────────────────────────┐
│ Backend Python                                               │
│  - Router WebSocket (/ws/device y /ws/panel)                 │
│  - Autenticación de usuarios (Argon2id + JWT)                │
│  - Challenge-response de dispositivos                        │
│  - Lógica de tanque, llenado automático y fail-safe          │
│  - Acciones WiFi, dispositivo y systemd                      │
│  - SQLite + auditoría                                        │
└───────────────────────────▲──────────────────────────────────┘
                            │ ws://…/ws/panel (JWT)
┌───────────────────────────┴──────────────────────────────────┐
│ Panel web estático                                           │
│  - Login, dashboard, redes WiFi, dispositivo, sistema, audit │
│  - Tema oscuro con acentos neón                              │
│  - Nunca recibe contraseñas WiFi ni key_hash                 │
└──────────────────────────────────────────────────────────────┘
```

Componentes:

- `hardware/esp32/main/` — firmware PlatformIO.
- `backend/` — servidor WebSocket, BD y seguridad.
- `panel/` — HTML/CSS/JS sin build step.
- `deploy/` — systemd, sudoers y helper.
- `scripts/device_config.py` — generación/validación de configuración.
- `flash.sh` — configuración y flasheo.

---

## 2. Configuración persistente

### 2.1 Dos archivos, un origen de verdad

| Archivo | Dónde vive | Contenido |
| --- | --- | --- |
| `device_config.json` | Host, ignorado por git | Identidad, `claim_secret`, WiFi, backend, límites |
| `data/config.json` | LittleFS del ESP32 | Lo mismo, pero solo `key_hash` (nunca el secreto) |

`flash.sh` genera `data/config.json` con `scripts/device_config.py` y lo sube
junto al firmware. En flasheos posteriores **pregunta** si se conserva la
configuración del ESP32; la opción por defecto es conservarla.

`config.h` es estático: solo pines, dirección I2C y valores por defecto. No
contiene credenciales ni datos de usuario.

### 2.2 Estructura de `config.json`

```json
{
  "schema": 1,
  "device": {
    "id": "WATTER-001",
    "name": "Bebedero Huerto",
    "location": "Patio Principal",
    "firmware": "1.0.0",
    "key_hash": "64 hex"
  },
  "backend": {
    "host": "192.168.1.100",
    "port": 8765,
    "path": "/ws/device",
    "tls": false
  },
  "wifi": [
    { "ssid": "Casa", "password": "…" },
    { "ssid": "Taller", "password": "…" }
  ],
  "sampling": { "interval_ms": 2000, "retry_ms": 5000 },
  "power": { "wake_pin": 33, "wake_active_low": true, "sleep_timer_min": 60 },
  "safety": { "max_relay_on_min": 10, "max_offline_min": 5 }
}
```

Reglas:

- 1..8 redes; la primera es obligatoria.
- En el asistente, dejar el SSID vacío a partir de la segunda red termina la
  lista (no se guarda).
- El orden del array es la **prioridad manual** de conexión.
- El ESP32 es la fuente de verdad de las redes: el panel las consulta y
  modifica contra el dispositivo, no contra una copia local.

### 2.3 Módulos del firmware

| Módulo | Responsabilidad |
| --- | --- |
| `ConfigStore` | Monta LittleFS, valida y guarda `/config.json`; operaciones WiFi |
| `NetManager` | Escaneo, conexión por prioridad manual, reintentos y estado |
| `Crypto` | SHA-256 y HMAC-SHA256 con mbedTLS |
| `DispComm` | WebSocket, handshake, comandos, telemetría y keepalive |
| `PowerManager` | Deep sleep, temporizador y despertar por botón |
| `Relay` | Relé activo en LOW y fail-safe local |
| `I2C` / `HC_SR04` | Pantalla y sensor |

### 2.4 Arranque y fail-safe

1. El relé se configura como salida y se fuerza OFF.
2. Se monta LittleFS y se valida `/config.json`.
3. Se configura el wake (temporizador + `ext0` en GPIO33).
4. Se conecta WiFi por prioridad y se abre el WebSocket.
5. `hello → challenge → auth`. Si no hay `key_hash`, queda `PENDING_CLAIM`.
6. Se muestrea el sensor y se envía telemetría.
7. `Relay::guard()` apaga el relé si supera el tiempo máximo encendido o si el
   backend lleva demasiado tiempo sin autenticar.

---

## 3. Backend

### 3.1 Módulos

| Archivo | Responsabilidad |
| --- | --- |
| `backend/main.py` | Router WebSocket, arranque, cierre, origen del panel |
| `handlers/device_handler.py` | Hello, challenge, auth, claim, telemetría, comandos |
| `handlers/panel_handler.py` | Login/resume, sync, configuración, acciones, auditoría |
| `handlers/state.py` | Sockets, nonces, claims, peticiones pendientes |
| `handlers/access.py` | Autorización por rol y propiedad |
| `handlers/device_command.py` | Envío de comandos y espera de `ack` |
| `handlers/wifi_handler.py` | Validación y comandos WiFi |
| `handlers/device_action.py` | Reboot, sleep y factory reset |
| `handlers/system_handler.py` | systemd vía `dispwatter-ctl` |
| `security/auth.py` | Argon2id, JWT, HMAC, rate limit y auditoría |
| `database/models.py` | `User`, `Device`, `TankConfig`, `DeviceNetwork`, `Telemetry`, `AuditLog` |
| `database/migrations.py` | Migraciones idempotentes y bootstrap del admin |

### 3.2 Estados del dispositivo

| Estado | Significado |
| --- | --- |
| `PENDING_CLAIM` | Conectado, sin `key_hash`; solo telemetría |
| `CLAIMED` | Vinculado y autenticado; acepta comandos |
| `BLOCKED` | Rechazado siempre |

### 3.3 Base de datos

- SQLite asíncrono (`aiosqlite` + SQLAlchemy 2).
- `devices.key_hash` es nullable para permitir `PENDING_CLAIM`.
- `device_networks` es una caché de SSID/prioridad/RSSI; **no guarda
  contraseñas**.
- La telemetría se purga cada 100 escrituras con retención configurable
  (24 h por defecto).
- Las migraciones añaden columnas nuevas y, una sola vez, invalidan el esquema
  de autenticación antiguo (`auth_v2_migrated`).

### 3.4 Lógica del tanque

El backend recibe la distancia bruta y calcula:

```
H_útil   = D_fondo - D_espejo
H_actual = D_fondo - D_medida
%        = clamp(H_actual / H_útil × 100, 0, 100)
litros   = V_total × % / 100
```

Llenado automático:

- `% ≤ min_level` y relé apagado → `set_relay(true)` + LCD «Llenando...».
- `% ≥ max_level` y relé encendido → `set_relay(false)` + LCD «Tanque lleno».
- Solo se aplica a dispositivos `CLAIMED`.

### 3.5 Acciones de sistema

`system_action` usa `dispwatter-ctl` con una lista blanca de sudoers:

- Reiniciar backend (responde antes de reiniciar).
- Arrancar/parar/reiniciar panel.
- Estado de ambos servicios.
- «Apagar todo»: duerme dispositivos y para el panel; el backend sigue vivo.
- «Encender todo»: arranca el panel; los dispositivos dormidos despiertan por
  temporizador o botón.
- «Reiniciar todo»: reinicia el panel y hace reboot de los dispositivos online.

El backend rechaza `backend/stop`. Para detenerlo: `systemctl stop`.

---

## 4. Panel web

Sin framework ni build step: módulos ES nativos.

| Vista | Contenido |
| --- | --- |
| Dashboard | Nivel, litros, distancia, relé, telemetría, vincular dispositivo |
| Redes WiFi | Lista priorizada, RSSI, añadir/borrar/reordenar, escanear |
| Dispositivo | Geometría del tanque, reboot, sleep, reset, eliminar |
| Sistema | Estado y control de servicios, apagar/encender/reiniciar todo |
| Auditoría | Últimos 250 eventos con filtros |

Características:

- Tema oscuro con acentos neón (cian, verde, magenta, ámbar).
- Login con JWT y reconexión automática.
- Los datos dinámicos se insertan con `textContent`.
- No hay simulación: la telemetría es real. Para desarrollo se puede apuntar a
  un backend de pruebas con `?backend=host:8765`.
- El endpoint por defecto es `${location.hostname}:8765`.

---

## 5. Seguridad (resumen)

- Usuarios: Argon2id + JWT HS256; roles `admin`/`user`.
- Dispositivos: challenge-response HMAC-SHA256 con nonce de un solo uso.
- El ESP32 guarda solo `key_hash`; el panel nunca lo recibe.
- Las contraseñas WiFi nunca salen del dispositivo/host.
- Origen del WebSocket del panel validado.
- Acciones de sistema con sudoers mínimo y sin autoapagado del backend.
- Auditoría en archivo y BD.

Detalle completo: [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 6. Protocolo (resumen)

- `/ws/device`: `hello → challenge → auth → auth_status`; luego telemetría,
  estado, ping y `ack`/`wifi_list`.
- `/ws/panel`: `login`/`resume` en 10 s; luego `sync_all` y mensajes de acción.
- Comandos al dispositivo: `set_relay`, `display`, `wifi_*`, `reboot`, `sleep`,
  `factory_reset`.

Detalle completo: [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

---

## 7. Despliegue

- `deploy/dispwatter-backend.service` — backend con `Restart=always`.
- `deploy/dispwatter-panel.service` — panel estático en el puerto 3000.
- `deploy/dispwatter-ctl` — helper cerrado para systemd.
- `deploy/sudoers.d/dispwatter` — lista blanca de comandos.
- `deploy/install.sh` — instalación asistida.
- `deploy/README.md` — guía completa.

Arranque manual para desarrollo: `./start.sh`; parada: `./stop.sh`.

---

## 8. Estructura del repositorio

```
DispWatter/
├── backend/
│   ├── database/          # modelos, conexión y migraciones
│   ├── handlers/          # dispositivo, panel, WiFi, acciones
│   ├── security/          # auth.py
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   └── .env.example
├── hardware/esp32/main/
│   ├── src/               # main.cpp, config.h
│   ├── ConfigStore/
│   ├── NetManager/
│   ├── DispComm/
│   ├── Crypto/
│   ├── PowerManager/
│   ├── Relay/
│   ├── I2C/
│   ├── HC_SR04/
│   ├── data/              # config.example.json
│   └── device_config.example.json
├── panel/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
├── deploy/
├── docs/
├── scripts/device_config.py
├── flash.sh
├── start.sh
└── stop.sh
```
