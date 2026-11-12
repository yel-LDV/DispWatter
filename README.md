# DispWatter - Monitoreo de Agua con ESP32

Sistema de monitoreo de nivel de agua con ESP32, panel web y actualizaciones OTA.

## Caracteristicas

- Monitoreo de nivel de agua en tiempo real con sensor ultrasonico HC-SR04
- Control remoto de bomba via panel web
- Actualizaciones de firmware OTA (Over-The-Air)
- Sistema de usuarios con registro y verificacion por email
- Permisos granulares por dispositivo
- Historial de telemetria con graficas
- Configuracion del LCD desde el panel
- Temas claro y oscuro

## Instalacion

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con credenciales
python main.py
```

### Panel Web

```bash
python -m http.server 3000 --directory panel
```

### Firmware ESP32

```bash
cd hardware/esp32/main
pio run -e esp32dev
pio run -e esp32dev --upload
```

## Actualizaciones OTA

Las actualizaciones se compilan automaticamente con GitHub Actions. Desde el panel:

1. Navega a la seccion OTA
2. Selecciona una version disponible
3. Presiona "Actualizar"
4. En el ESP32, presiona el boton OK para confirmar

## Botones Fisicos

- **OK + Arriba (2s)**: Modo OTA
- **OK + Abajo (2s)**: Modo downgrade
- **OK + Izquierda**: Volver al modo normal
- **OK (corto)**: Confirmar accion
- **OK (largo)**: Cambiar modo

## Pruebas

```bash
./test.sh --all --save results
```

## Documentacion

- [Circuito](docs/circuit.md) - Diagrama de conexiones
- [Montaje](docs/assembly.md) - Guia de ensamblaje
- [OTA](docs/ota.md) - Guia de actualizaciones
- [Botones](docs/buttons.md) - Guia de navegacion
