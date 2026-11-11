# Backend DispWatter

Servidor WebSocket que atiende a los ESP32 (`/ws/device`) y al panel web
(`/ws/panel`).

## Arranque rápido

```bash
cd ..
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# edita backend/.env: JWT_SECRET, ADMIN_USER y ADMIN_PASSWORD
backend/.venv/bin/python -m backend.main
```

El backend crea `backend/data.db`, aplica migraciones y, si no existe ningún
usuario, crea el administrador inicial con `ADMIN_USER`/`ADMIN_PASSWORD`.

## Documentación

- Arquitectura general: [`../ARQUITECTURA.md`](../ARQUITECTURA.md)
- Protocolo WebSocket: [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md)
- Seguridad y rotación de secretos: [`../docs/SECURITY.md`](../docs/SECURITY.md)
- Despliegue con systemd: [`../deploy/README.md`](../deploy/README.md)

## Estructura

| Ruta | Contenido |
| --- | --- |
| `main.py` | Router WebSocket y arranque |
| `config.py` | Variables de entorno y rutas |
| `handlers/` | Lógica de dispositivo, panel, WiFi y systemd |
| `security/auth.py` | Argon2id, JWT, HMAC, rate limit, auditoría |
| `database/` | Modelos, conexión y migraciones |
| `requirements.txt` | Dependencias |
| `.env.example` | Plantilla sin secretos |

No subas `backend/.env`, `backend/data.db` ni `backend/backups/` al
repositorio.
