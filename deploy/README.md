# Despliegue de DispWatter

Guía para instalar el backend WebSocket y el panel web como servicios de
systemd, con las credenciales y permisos correctos.

> El repositorio **no** incluye secretos. `backend/.env`, `device_config.json` y
> `data/config.json` están en `.gitignore` y deben crearse en cada instalación.

---

## 1. Requisitos

- Linux con systemd.
- Python 3.11 o superior (probado con 3.14).
- `sudo`, `systemctl` y, opcionalmente, `git`.
- Plataforma de firmware: PlatformIO (`pio`) para compilar y flashear el ESP32.

Rutas usadas en esta guía:

| Elemento | Ruta |
| --- | --- |
| Repositorio | `/home/angedl_/Proyectos/DispWatter` |
| Backend | `backend/` |
| Panel | `panel/` |
| Base de datos | `backend/data.db` |
| Logs | `logs/` |
| Unidades systemd | `/etc/systemd/system/` |
| Helper privilegiado | `/usr/local/bin/dispwatter-ctl` |

Si usas otra ruta u otro usuario, ajusta `deploy/*.service`,
`deploy/sudoers.d/dispwatter` y `deploy/install.sh` antes de instalar.

---

## 2. Preparar el entorno Python

```bash
cd /home/angedl_/Proyectos/DispWatter
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
```

Crea `backend/.env` a partir del ejemplo:

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
```

Genera un `JWT_SECRET` real y edítalo:

```bash
openssl rand -hex 48
```

Valores importantes de `backend/.env`:

```dotenv
HOST=0.0.0.0
PORT=8765
PANEL_PORT=3000
PANEL_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
JWT_SECRET=<cadena aleatoria larga>
JWT_EXPIRE_HOURS=12
ADMIN_USER=admin
ADMIN_PASSWORD=<contraseña inicial fuerte>
DB_NAME=data.db
```

- `ADMIN_USER` / `ADMIN_PASSWORD` solo se usan para crear el **primer**
  administrador cuando la tabla `users` está vacía.
- Puedes añadir más orígenes separados por comas si abres el panel desde otra
  IP o nombre. Los orígenes loopback y de red privada en `PANEL_PORT` también se
  aceptan automáticamente.
- `SYSTEM_ACTIONS_ENABLED=false` desactiva los botones de systemd del panel.
- `DISPWATTER_CTL` permite cambiar la ruta del helper (por defecto
  `/usr/local/bin/dispwatter-ctl`).

Inicia el backend manualmente una vez para crear la base de datos y el
administrador:

```bash
backend/.venv/bin/python -m backend.main
```

Comprueba que `backend/data.db` existe y que en el log aparece
`Administrador inicial creado: <usuario>`. Después detén el proceso con
`Ctrl+C`.

---

## 3. Instalar los servicios systemd

```bash
sudo cp deploy/dispwatter-backend.service /etc/systemd/system/
sudo cp deploy/dispwatter-panel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dispwatter-backend.service dispwatter-panel.service
```

Verifica:

```bash
systemctl status dispwatter-backend.service --no-pager
systemctl status dispwatter-panel.service --no-pager
```

Panel: `http://<ip-del-servidor>:3000`
WebSocket del panel: `ws://<ip-del-servidor>:8765/ws/panel`
WebSocket del hardware: `ws://<ip-del-servidor>:8765/ws/device`

Si el panel está en otro host, ábrelo con el parámetro `?backend=host:8765`
para indicar la dirección del backend.

---

## 4. Helper privilegiado y sudoers

El backend necesita reiniciar o detener el **panel**, pero nunca debe poder
detener el backend desde el panel. Para ello se usa un helper con comandos
cerrados:

```bash
sudo install -o root -g root -m 0755 deploy/dispwatter-ctl /usr/local/bin/dispwatter-ctl
sudo install -o root -g root -m 0440 deploy/sudoers.d/dispwatter /etc/sudoers.d/dispwatter
sudo visudo -c
```

El archivo de sudoers permite únicamente:

- `backend-restart`
- `panel-start`
- `panel-stop`
- `panel-restart`
- `status`

`backend-stop` existe en el helper para administración manual por root, pero
**no** está autorizado para el usuario del backend y el handler del panel lo
rechaza explícitamente.

Prueba el helper sin contraseña desde el usuario del servicio:

```bash
sudo -n /usr/local/bin/dispwatter-ctl status
```

Si falla, revisa el nombre de usuario en `/etc/sudoers.d/dispwatter` y que la
unidad del backend no tenga `NoNewPrivileges=true`.

---

## 5. Instalación automática (opcional)

`deploy/install.sh` copia unidades, helper y sudoers sustituyendo usuario y
ruta del repositorio:

```bash
sudo ./deploy/install.sh
# o para otro usuario/ruta:
sudo ./deploy/install.sh --user mi_usuario --dir /opt/DispWatter
```

El script no crea `backend/.env` ni el entorno virtual: sigue siendo necesario
el paso 2.

---

## 6. Primer acceso al panel

1. Abre `http://<servidor>:3000`.
2. Inicia sesión con `ADMIN_USER` / `ADMIN_PASSWORD`.
3. El dispositivo aparece como **Pendiente de vincular** en cuanto se conecta
   y completa el handshake `hello → challenge → auth`.
4. Pulsa **Vincular dispositivo**, introduce el `device.id` y el
   `claim_secret` configurado en `hardware/esp32/main/device_config.json`.
5. El backend envía un challenge al ESP32 y verifica el HMAC-SHA256. Si
   coincide, el dispositivo queda `CLAIMED` y asociado al administrador.

El `claim_secret` solo se usa durante la vinculación y no se guarda en el panel
ni en la base de datos. El ESP32 guarda únicamente `key_hash = SHA256(id:secreto)`.

### Crear más usuarios

De momento no hay pantalla de gestión de usuarios. Se pueden crear desde
Python con el mismo entorno:

```bash
backend/.venv/bin/python - <<'PY'
import asyncio, secrets
from backend.database.connect import get_db
from backend.database.models import User
from backend.security.auth import hash_password

async def main():
    async with get_db() as session:
        session.add(User(
            id=f"USR-{secrets.token_hex(6)}",
            username="operador",
            password_hash=hash_password("cambia-esta-contrasena"),
            role="user",
            is_active=True,
        ))
        await session.commit()

asyncio.run(main())
PY
```

Roles:

- `admin`: todo, incluido vincular/eliminar dispositivos, reset de fábrica y
  acciones de systemd.
- `user`: sus dispositivos, relé, pantalla, WiFi y configuración del tanque.

---

## 7. Seguridad operativa

- **El backend no se apaga desde el panel.** Los botones solo permiten
  reiniciarlo; para detenerlo usa `sudo systemctl stop dispwatter-backend`.
- **«Apagar todo»** detiene el panel y envía deep sleep a los dispositivos
  online. El backend permanece vivo para permitir la recuperación.
- Los dispositivos en deep sleep **no despiertan por red**: usan el
  temporizador configurado o el botón físico del pin de wake.
- Las contraseñas WiFi nunca se envían al navegador. El panel muestra SSID,
  RSSI, si tienen clave y la prioridad.
- El firmware guarda la configuración en `/config.json` dentro de LittleFS.
  `flash.sh` pregunta antes de sobrescribirla.
- Protege `backend/.env` (`chmod 600`) y no lo subas nunca a git.
- Rota cualquier contraseña WiFi o secreto que haya podido quedar en el
  historial de git. El historial no se reescribe automáticamente.

Consulta `docs/SECURITY.md` para el modelo de amenazas y la rotación de
secretos.

---

## 8. Operación diaria

```bash
# Estado
sudo systemctl status dispwatter-backend.service dispwatter-panel.service
sudo /usr/local/bin/dispwatter-ctl status

# Logs
journalctl -u dispwatter-backend.service -f
journalctl -u dispwatter-panel.service -f
tail -f logs/backend.log
tail -f logs/audit.log

# Reiniciar tras actualizar código
sudo systemctl restart dispwatter-backend.service dispwatter-panel.service
```

La base de datos SQLite está en `backend/data.db`. Haz copias de seguridad
periódicas con el backend detenido o usando `sqlite3 .backup`:

```bash
sqlite3 backend/data.db ".backup 'backend/data-$(date +%F).db'"
```

---

## 9. Actualizar el firmware

```bash
cd /home/angedl_/Proyectos/DispWatter
./flash.sh
```

- La primera vez crea `hardware/esp32/main/device_config.json` a partir del
  ejemplo y pide los datos.
- En flasheos posteriores pregunta si se conserva la configuración del ESP32.
  La opción por defecto es conservarla.
- `--reset-config` fuerza la subida de `data/config.json`.
- `--fresh` recrea la configuración del host.
- `--build-only` solo compila.

El firmware usa la partición `min_spiffs.csv` (dos slots OTA de 1,875 MB y
128 KB para LittleFS).

---

## 10. Problemas frecuentes

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `Falta JWT_SECRET en backend/.env` | `.env` incompleto | Genera y añade `JWT_SECRET` |
| Panel muestra «Sin backend» | Puerto/origen incorrecto | Usa `?backend=host:8765` y revisa `PANEL_ORIGINS` |
| `systemd_unavailable` en el panel | Helper o sudoers mal instalados | Repite el paso 4 y prueba `sudo -n … status` |
| Dispositivo en `PENDING_CLAIM` | Secreto incorrecto u offline | Verifica `claim_secret` y que esté online |
| El ESP32 no guarda WiFi | LittleFS no subido | Ejecuta `./flash.sh` y acepta subir `data/` |
| El relé se activa al reiniciar | Falta pull-down externo | Instala la resistencia según `docs/WIRING.md` |
| Puerto 8765 ocupado | Otro backend en marcha | `pkill -f "python -m backend.main"` |
