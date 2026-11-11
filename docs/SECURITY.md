# Seguridad

Modelo de seguridad, credenciales, permisos y procedimientos de rotación de
DispWatter.

---

## 1. Principios

1. **Sin credenciales por defecto.** El administrador inicial se crea desde
   `backend/.env`; si faltan `ADMIN_USER`/`ADMIN_PASSWORD` no se crea ninguno.
2. **El panel nunca ve secretos de dispositivo ni contraseñas WiFi.**
   - `key_hash` no se incluye en `to_dict()` ni en `sync_all`.
   - Las contraseñas WiFi se guardan solo en el ESP32 y en el fichero de
     configuración del host; el panel recibe únicamente SSID, RSSI,
     `has_password` y prioridad.
3. **El backend no puede apagarse desde el panel.** Solo se reinicia; para
   detenerlo hace falta systemd/CLI con privilegios.
4. **Mínimo privilegio.** El backend ejecuta un helper cerrado mediante
   `sudo -n` con una lista blanca de comandos.
5. **Todo lo relevante se audita.** Login, cambios de configuración, comandos,
   acciones de sistema y vinculaciones.

---

## 2. Contraseñas de usuario

- Algoritmo: **Argon2id** (`argon2-cffi`), con los parámetros por defecto de la
  librería.
- El hash se guarda en `users.password_hash`; nunca se devuelve al cliente.
- Sesión: **JWT HS256** firmado con `JWT_SECRET`, con `sub`, `role`, `iat` y
  `exp` (12 h por defecto).
- El token se guarda en `localStorage` del navegador. Es aceptable para un panel
  de LAN, pero implica que un XSS podría robarlo: no se debe inyectar HTML de
  usuario sin escapar. El panel usa `textContent` para los datos dinámicos.
- Límite de login: 5 intentos por IP y ventana de 300 s (en memoria del
  backend). Al superarlo se responde `rate_limited`.
- `PANEL_AUTH_TIMEOUT=10`: un WebSocket de panel que no se autentica en 10 s se
  cierra con código 1008.

### Roles

| Rol | Permisos |
| --- | --- |
| `admin` | Todo: vincular/eliminar dispositivos, reset de fábrica, systemd, WiFi, relé, configuración |
| `user` | Solo sus dispositivos: relé, pantalla, WiFi, configuración del tanque |

La propiedad se comprueba con `devices.owner_id`. Un `user` no puede actuar
sobre dispositivos de otro usuario. `admin` puede actuar sobre cualquiera.

---

## 3. Autenticación del dispositivo

- El ESP32 guarda **solo** `key_hash = SHA256(id:secreto)`.
- El secreto en claro (`claim_secret`) vive únicamente en
  `hardware/esp32/main/device_config.json` (host, `chmod 600`, ignorado por
  git).
- Handshake: el backend envía un nonce de un solo uso (32 bytes aleatorios,
  caduca en 30 s); el ESP32 responde
  `HMAC-SHA256(key=key_hash, message=nonce)`.
- El backend compara con `hmac.compare_digest` (tiempo constante).
- Un nonce caducado, repetido o desconocido se rechaza.
- Un dispositivo `PENDING_CLAIM` puede conectarse y enviar telemetría, pero no
  recibe comandos hasta que se vincula.
- Un dispositivo `BLOCKED` se rechaza siempre.
- La vinculación exige que el dispositivo esté **online**: el backend le envía
  el challenge de claim y verifica el HMAC. Así el panel no puede vincular un
  dispositivo ajeno solo conociendo su ID.

### Por qué no se usa un token con timestamp

La versión anterior usaba `SHA256(key_hash:timestamp)`. Un timestamp es
predecible y permite replay dentro de la ventana de tolerancia. El nonce
aleatorio de un solo uso elimina ese problema.

---

## 4. Superficie de red

### Orígenes del panel

`is_origin_allowed()` comprueba el header `Origin` del WebSocket:

- Sin `Origin` (clientes CLI) se permite.
- Se permite cualquier origen si `PANEL_ORIGINS` contiene `*`.
- Se permiten los orígenes listados en `PANEL_ORIGINS`.
- Se permiten orígenes `http(s)` en `PANEL_PORT` cuyo host sea loopback o una
  IP privada (para abrir el panel desde otro equipo de la LAN).

Ajusta `PANEL_ORIGINS` si usas un dominio o un proxy inverso. No uses `*` en
producción.

### TLS

El backend escucha WebSocket sin TLS por defecto. Para exposición fuera de la
LAN, coloca un proxy inverso (Caddy, nginx, Traefik) con TLS y usa `wss://`.
El panel detecta `https:` y genera la URL `wss://` automáticamente.

### Red

- Segmenta los dispositivos IoT en una VLAN o red separada.
- No expongas los puertos 8765/3000 a Internet sin TLS y autenticación.
- El firmware admite `backend.tls = true` si compilas con soporte TLS y usas
  `wss://`.

---

## 5. Acciones de sistema y sudoers

El backend necesita gestionar el panel, pero no debe poder apagarse a sí mismo
ni ejecutar comandos arbitrarios. Para ello:

- `deploy/dispwatter-ctl` implementa una lista cerrada de comandos.
- `deploy/sudoers.d/dispwatter` autoriza **solo**:
  `backend-restart`, `panel-start`, `panel-stop`, `panel-restart`, `status`.
- `backend-stop` existe en el helper para administración manual por root, pero
  no está en sudoers y el handler responde `forbidden`.
- La unidad del backend **no** usa `NoNewPrivileges=true` porque necesita
  `sudo -n`. La unidad del panel sí lo usa.
- `SYSTEM_ACTIONS_ENABLED=false` desactiva por completo los botones de sistema.

«Apagar todo» detiene el panel y pone los dispositivos online en deep sleep,
pero mantiene el backend vivo. Es una decisión de disponibilidad: permite
recuperar el sistema y volver a arrancar el panel.

---

## 6. Fail-safes del hardware

- El relé se fuerza a OFF en `setup()`, antes de inicializar nada más.
- Se apaga antes de reiniciar, dormir o hacer reset de fábrica.
- `safety.max_relay_on_min`: apaga el relé si está encendido demasiado tiempo.
- `safety.max_offline_min`: apaga el relé si el backend lleva demasiado tiempo
  sin autenticar.
- Pull-up externo en la entrada del relé para evitar activaciones durante el
  arranque y el deep sleep (ver `docs/WIRING.md`).
- El deep sleep solo despierta por temporizador o botón físico; no hay
  despertar remoto por red.

---

## 7. Almacenamiento de secretos

| Secreto | Ubicación | Permisos | Git |
| --- | --- | --- | --- |
| `JWT_SECRET` | `backend/.env` | `600` | Ignorado |
| `ADMIN_PASSWORD` | `backend/.env` | `600` | Ignorado |
| `claim_secret` | `hardware/esp32/main/device_config.json` | `600` | Ignorado |
| Contraseñas WiFi | `device_config.json` y `/config.json` del ESP32 | `600` / LittleFS | Ignorado |
| `key_hash` | `data/config.json` del ESP32 y BD | — | Ignorado |

Archivos de ejemplo sin secretos: `backend/.env.example` y
`hardware/esp32/main/device_config.example.json`.

Comprueba antes de publicar:

```bash
git status --short
git ls-files | grep -E '\.env$|device_config\.json$|data/config\.json$' && echo "REVISAR"
git grep -n -i -E 'password|secret|token' -- ':!*.md' ':!*.example.*'
```

---

## 8. Rotación de secretos

### 8.1 Contraseña WiFi filtrada

Si una contraseña WiFi ha estado en git, en un log o en una captura, considérala
**comprometida** aunque borres el archivo:

1. Cambia la contraseña en el router/AP.
2. Actualiza la entrada correspondiente en
   `hardware/esp32/main/device_config.json` (o vuelve a ejecutar
   `./flash.sh --fresh`).
3. Reflashea con `./flash.sh --reset-config` para subir el nuevo
   `data/config.json`.
4. Verifica que el dispositivo se conecta y que el panel muestra la red.
5. Si el repositorio es público, valora reescribir el historial con
   `git filter-repo` y forzar el push. La rotación es obligatoria; reescribir el
   historial es opcional y no sustituye a la rotación.

No se debe imprimir la contraseña en la salida de `flash.sh` ni en los logs.

### 8.2 Secreto del dispositivo

Si cambias `claim_secret`, el `key_hash` cambia y el dispositivo deja de
autenticar contra la BD:

1. Como `admin`, elimina el dispositivo desde el panel (borra también su
   configuración y telemetría).
2. Actualiza `device_config.json` y ejecuta `./flash.sh --reset-config`.
3. Espera a que aparezca como `PENDING_CLAIM`.
4. Vincúlalo de nuevo con el nuevo secreto.

### 8.3 `JWT_SECRET`

1. Genera uno nuevo: `openssl rand -hex 48`.
2. Actualiza `backend/.env` y reinicia el backend.
3. Todas las sesiones existentes quedan invalidadas; los usuarios deben volver
   a iniciar sesión.

### 8.4 Contraseña de administrador

No hay pantalla de cambio de contraseña. Cámbiala con un script de Python
(Argon2id) o crea otro usuario `admin` y desactiva el anterior. Consulta
`deploy/README.md`.

---

## 9. Auditoría

Se escribe en dos sitios:

- `logs/audit.log` (texto, una línea por evento).
- Tabla `audit_logs` de SQLite (consultable desde el panel, últimos 250).

Eventos destacados: `LOGIN_SUCCESS`, `LOGIN_FAILED`, `PANEL_CONNECTED`,
`DEVICE_AUTH_SUCCESS`, `DEVICE_AUTH_FAILED`, `DEVICE_CLAIMED`,
`DEVICE_CLAIM_FAILED`, `WIFI_ADDED`, `WIFI_REMOVED`, `WIFI_REORDERED`,
`CONFIG_UPDATED`, `MANUAL_RELAY`, `MANUAL_DISPLAY`, `DEVICE_REBOOT`,
`DEVICE_SLEEP`, `DEVICE_FACTORY_RESET`, `SYSTEM_*`, `DEVICE_DELETED`.

Protege `logs/` y limita su acceso. La retención de telemetría es de 24 h por
defecto (`TELEMETRY_RETENTION_HOURS`); la auditoría no se borra
automáticamente.

---

## 10. Limitaciones conocidas

- El panel se sirve como estático; no hay CSP ni cabeceras de seguridad por
  defecto. Si lo expones fuera de la LAN, añádelas en el proxy inverso.
- El token JWT en `localStorage` es vulnerable a XSS. No hay contenido de
  usuario sin escapar, pero conviene mantenerlo así.
- No hay gestión de usuarios desde la interfaz; se hace por script.
- El rate limit de login es por proceso y en memoria: se reinicia con el
  backend.
- SQLite no está cifrado en reposo. Protege el disco y los backups.
- El firmware no verifica el certificado del backend si se usa TLS; para
  producción, fija la CA o usa un backend en red privada.
