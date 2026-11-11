# Protocolo WebSocket

DispWatter usa dos endpoints WebSocket con mensajes JSON:

| Endpoint | Cliente | Autenticación |
| --- | --- | --- |
| `ws://<host>:8765/ws/device` | ESP32 | Challenge-response HMAC-SHA256 |
| `ws://<host>:8765/ws/panel` | Panel web | `login` o `resume` con JWT |

El tamaño máximo de mensaje es `MAX_MESSAGE_SIZE × 20` (40 960 bytes con el
valor por defecto `2048`).

---

## 1. Autenticación del dispositivo

### 1.1 Secreto y `key_hash`

En el host se define un `claim_secret` de al menos 16 caracteres. A partir de
él se calcula:

```
key_hash = SHA256("<device_id>:<claim_secret>")   # 64 caracteres hex
```

- `device_config.json` (host) contiene el secreto y las contraseñas WiFi.
- `data/config.json` (LittleFS del ESP32) contiene **solo** `key_hash`.
- El backend guarda `key_hash` en la tabla `devices`.
- El `claim_secret` no se envía nunca al panel ni se guarda en la base de datos.

### 1.2 Handshake

```
ESP32                                  Backend
  │  hello {device_id, firmware}          │
  ├──────────────────────────────────────►│
  │                                       │ crea/actualiza dispositivo
  │  challenge {nonce, purpose:"auth"}    │ PENDING_CLAIM si no existe
  │◄──────────────────────────────────────┤
  │  auth {device_id, nonce, proof, ...}  │
  ├──────────────────────────────────────►│
  │                                       │ verifica HMAC
  │  auth_status {status}                 │
  │◄──────────────────────────────────────┤
```

`proof` se calcula en el ESP32:

```
proof = HMAC-SHA256(key = key_hash_ascii, message = nonce)   # hex
```

El nonce es de un solo uso, caduca a los 30 s y se guarda en memoria del
backend. Un nonce repetido o caducado devuelve `invalid_nonce`.

### 1.3 Mensajes

#### `hello` (ESP32 → backend)

```json
{
  "event": "hello",
  "device_id": "WATTER-001",
  "firmware": "1.0.0"
}
```

#### `challenge` (backend → ESP32)

```json
{
  "event": "challenge",
  "nonce": "64 caracteres hex",
  "expires_in": 30,
  "purpose": "auth"
}
```

`purpose` puede ser `auth` o `claim`.

#### `auth` (ESP32 → backend)

```json
{
  "event": "auth",
  "device_id": "WATTER-001",
  "nonce": "el nonce recibido",
  "proof": "64 caracteres hex",
  "name": "Bebedero Huerto",
  "location": "Patio Principal",
  "firmware": "1.0.0",
  "wake_reason": "timer"
}
```

`wake_reason`: `power_on`, `timer`, `button` o `unknown`.

#### `auth_status` (backend → ESP32)

```json
{ "event": "auth_status", "status": "ok", "device_id": "WATTER-001" }
```

| `status` | Significado |
| --- | --- |
| `ok` | HMAC verificado y dispositivo `CLAIMED` |
| `pending_claim` | HMAC correcto pero el dispositivo aún no tiene `key_hash`; solo telemetría |
| `error` | Rechazado; `error` indica el motivo |

Errores posibles: `invalid_device_id`, `invalid_params`, `invalid_nonce`,
`invalid_proof`, `blocked`.

### 1.4 Vinculación (`claim`)

El dispositivo debe estar online. El panel (solo `admin`) envía
`claim_device` con el `device_id` y el `claim_secret`.

```
Panel                Backend                      ESP32
  │ claim_device        │                            │
  ├────────────────────►│                            │
  │                     │ challenge {purpose:claim}  │
  │                     ├───────────────────────────►│
  │                     │ auth {nonce, proof}        │
  │                     │◄───────────────────────────┤
  │                     │ verifica SHA256(id:secreto)│
  │                     │ = key_hash esperado        │
  │ claim_result        │                            │
  │◄────────────────────┤ auth_status {ok}           │
  │                     ├───────────────────────────►│
```

Si el `proof` no coincide, el backend responde `claim_result` con error
`invalid_credentials` y registra `DEVICE_CLAIM_FAILED` en auditoría.

---

## 2. Mensajes del dispositivo

### 2.1 Telemetría (ESP32 → backend)

```json
{
  "event": "telemetry",
  "device_id": "WATTER-001",
  "distance_mm": 640.0,
  "relay_state": false,
  "timestamp": 12345,
  "rssi": -52
}
```

- `distance_mm` debe estar entre 0 y 12 000. Fuera de rango se descarta.
- El backend calcula porcentaje y litros con la geometría del tanque.
- Cada lectura se guarda en `telemetry` y se reenvía a los paneles como evento
  `telemetry`.

### 2.2 Estado del dispositivo (ESP32 → backend)

```json
{
  "event": "device_status",
  "device_id": "WATTER-001",
  "uptime_s": 5230,
  "rssi": -52,
  "ip": "192.168.1.77",
  "free_heap": 210000,
  "wake_reason": "timer",
  "firmware": "1.0.0",
  "pending_claim": false
}
```

### 2.3 Keepalive

```json
{ "event": "ping", "device_id": "WATTER-001" }
```

El backend responde `{"event":"pong","device_id":"..."}`. El ESP32 envía un
`ping` cada 30 s.

### 2.4 Resultados de comandos

El firmware responde a cada comando con `ack`:

```json
{ "event": "ack", "request_id": "abc123", "ok": true }
```

En caso de error:

```json
{ "event": "ack", "request_id": "abc123", "ok": false, "error": "unauthorized" }
```

`wifi_list` devuelve la lista de redes (nunca contraseñas):

```json
{
  "event": "wifi_list",
  "request_id": "abc123",
  "networks": [
    {
      "ssid": "Casa",
      "rssi": -45,
      "visible": true,
      "stored": true,
      "connected": true,
      "has_password": true,
      "priority": 0
    },
    {
      "ssid": "Invitados",
      "rssi": -80,
      "visible": true,
      "stored": false,
      "connected": false,
      "has_password": false,
      "priority": -1
    }
  ]
}
```

`ack` y `wifi_list` **no incluyen `device_id`**: el backend lo deriva del
socket autenticado. Si el firmware lo incluye, debe coincidir.

---

## 3. Comandos del backend al dispositivo

Todos llevan `request_id` y se responden con `ack` (o `wifi_list`).

### `set_relay`

```json
{ "command": "set_relay", "state": true, "request_id": "r1" }
```

### `display`

```json
{
  "command": "display",
  "line0": "Nivel 78%",
  "line1": "Bomba ACTIVA",
  "clear": false,
  "request_id": "r2"
}
```

Cada línea se recorta a 16 caracteres. La pantalla normal vuelve a los 10 s.

### `wifi_list`

```json
{ "command": "wifi_list", "request_id": "r3" }
```

### `wifi_add`

```json
{
  "command": "wifi_add",
  "ssid": "Taller",
  "password": "contrasena-de-8-a-63",
  "request_id": "r4"
}
```

`password` vacía = red abierta. SSID de 1 a 31 bytes; contraseña de 8 a 63
caracteres o vacía.

### `wifi_remove`

```json
{ "command": "wifi_remove", "ssid": "Taller", "request_id": "r5" }
```

No se puede borrar la última red guardada.

### `wifi_reorder`

```json
{ "command": "wifi_reorder", "ssid": "Taller", "index": 0, "request_id": "r6" }
```

Mueve la red a la posición indicada (0 = primera). El orden es la prioridad
manual de conexión.

### `reboot`

```json
{ "command": "reboot", "request_id": "r7" }
```

Apaga el relé, responde `ack` y reinicia el ESP32.

### `sleep`

```json
{ "command": "sleep", "minutes": 60, "request_id": "r8" }
```

Apaga el relé y entra en deep sleep. Despierta por temporizador o por el botón
físico del GPIO de wake.

### `factory_reset`

```json
{ "command": "factory_reset", "request_id": "r9" }
```

Borra `/config.json` de LittleFS y reinicia. El dispositivo deja de estar
vinculado hasta que se vuelva a configurar y reclamar.

---

## 4. Protocolo del panel

### 4.1 Autenticación

Al conectar, el backend espera `login` o `resume` durante 10 s. Si no llega,
cierra con código 1008.

#### `login`

```json
{ "event": "login", "username": "admin", "password": "..." }
```

Respuesta:

```json
{
  "event": "login_result",
  "ok": true,
  "token": "<JWT>",
  "user": { "id": "USR-...", "username": "admin", "role": "admin" }
}
```

Si falla: `ok:false`, `error:"unauthorized"` o `error:"rate_limited"`.

#### `resume`

```json
{ "event": "resume", "token": "<JWT>" }
```

Respuesta: `resume_result` con `ok`, `user` o `error:"unauthorized"`.

Tras autenticar, el backend envía `sync_all`.

### 4.2 `sync_all` (backend → panel)

```json
{
  "event": "sync_all",
  "devices": [
    {
      "id": "WATTER-001",
      "name": "Bebedero Huerto",
      "location": "Patio Principal",
      "firmware_version": "1.0.0",
      "claimed": true,
      "status": "CLAIMED",
      "owner_id": "USR-...",
      "online": true,
      "last_seen": "2026-11-10T20:00:00",
      "rssi": -52,
      "ip": "192.168.1.77",
      "wake_reason": "timer",
      "capacity": 50.0,
      "bottomDist": 900.0,
      "mirrorDist": 100.0,
      "minLevel": 25.0,
      "maxLevel": 90.0,
      "autoRefill": true,
      "currentDist": 640.0,
      "waterPercent": 30.0,
      "waterLiters": 15.0,
      "relayState": false,
      "networks": [
        {
          "ssid": "Casa",
          "priority": 0,
          "has_password": true,
          "rssi": -45,
          "visible": true,
          "connected": true
        }
      ]
    }
  ]
}
```

Nunca incluye `key_hash` ni contraseñas WiFi.

### 4.3 Mensajes del panel → backend

| `event` | Campos principales | Respuesta |
| --- | --- | --- |
| `claim_device` | `device_id`, `password`, `name?`, `request_id` | `claim_result` |
| `update_config` | `device_id`, `config`, `request_id` | `ack` + `sync_all` |
| `wifi_list` | `device_id`, `request_id` | `wifi_list_result` |
| `wifi_add` | `device_id`, `ssid`, `password`, `request_id` | `ack` |
| `wifi_remove` | `device_id`, `ssid`, `request_id` | `ack` |
| `wifi_reorder` | `device_id`, `ssid`, `index`, `request_id` | `ack` |
| `device_action` | `device_id`, `action`, `minutes?`, `request_id` | `ack` |
| `system_action` | `target`, `action`, `request_id` | `system_result` |
| `delete_device` | `device_id`, `request_id` | `ack` + `sync_all` |
| `get_audit` | `action?`, `device_id?`, `request_id` | `audit_result` |
| `set_relay` | `device_id`, `state`, `request_id` | `ack` |
| `display` | `device_id`, `line0`, `line1`, `clear`, `request_id` | `ack` |
| `sync` | — | `sync_all` |
| `ping` | — | `pong` |

`update_config.config`:

```json
{
  "capacity": 50.0,
  "bottom_dist_mm": 900.0,
  "mirror_dist_mm": 100.0,
  "min_level": 25.0,
  "max_level": 90.0,
  "auto_refill": true
}
```

`device_action.action`: `reboot`, `sleep` (`minutes` 1..1440) o
`factory_reset` (solo `admin`).

`system_action.target`: `backend`, `panel` o `all`.
`system_action.action`: `start`, `stop`, `restart` o `status`.

Restricciones:

- `backend/stop` → `forbidden`. El backend no puede apagarse desde el panel.
- `backend/start` → `forbidden` (ya está en ejecución).
- `backend/restart` responde de inmediato y reinicia el servicio tras 1 s.
- `all/stop` duerme los dispositivos y detiene el panel; el backend sigue vivo.

### 4.4 Eventos del backend al panel

- `telemetry`: distancia, porcentaje, litros y estado del relé.
- `device_status`: online/offline, RSSI, IP, firmware, motivo de despertar.
- `pong`.
- `error`: `{event, request_id, code, message}`.

---

## 5. Códigos de error

| Código | Significado |
| --- | --- |
| `unauthorized` | Sin sesión o token inválido |
| `forbidden` | Rol/permisos insuficientes o acción prohibida |
| `invalid_params` | Datos inválidos o fuera de rango |
| `not_found` | Dispositivo inexistente |
| `device_not_claimed` | El dispositivo no está vinculado |
| `device_offline` | El dispositivo no tiene socket activo |
| `timeout` | El dispositivo no respondió a tiempo |
| `hardware_error` | Error interno del backend |
| `systemd_unavailable` | Falta `dispwatter-ctl` o los permisos sudo |
| `invalid_json` | Mensaje no es JSON válido |
| `rate_limited` | Demasiados intentos de login |

---

## 6. Límites y validaciones

| Campo | Regla |
| --- | --- |
| `device_id` | `^[A-Za-z0-9._-]{1,64}$` |
| `claim_secret` | ≥ 16 caracteres |
| `key_hash` | 64 hex |
| SSID | 1..31 bytes, sin duplicados |
| Contraseña WiFi | 0 u 8..63 caracteres |
| Redes guardadas | 1..8; la primera es obligatoria |
| `distance_mm` | 0..12 000 |
| Capacidad | 0,1..100 000 L |
| Distancia al fondo | 10..12 000 mm |
| Distancia al espejo | 0 ≤ espejo < fondo |
| Niveles | 0..100 %, mínimo < máximo |
| `minutes` de sleep | 1..1440 |
| Timeout de comando | 10 s (20 s en claim) |
