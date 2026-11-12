# Cambios sobre la rama fixBugs

Copia estos archivos sobre el repo respetando las rutas (no incluye `hardware/esp32/src`, que es un enlace a `main/src`).

## 1. Bomba invertida
- `Relay.h/.cpp`: la polaridad ya no está fija. `setPolarity()`, `activeLow()`, y el pin se deja en nivel de apagado **antes** de pasar a salida (sin pulso al arrancar).
- `config.h`: `RELE_ACTIVE_LOW_DEFAULT` (ahora 0 = módulo activo en HIGH, que es lo que describe tu síntoma). Se puede sobrescribir con `"relay": {"active_low": ...}` en `config.json` (`ConfigStore`, `device_config.py`, ejemplos JSON).
- `main.cpp` + `DispComm`: el `ack` de `set_relay` devuelve el estado REAL del relé; el backend lo difunde (`relay_state`) y lo guarda en caché. Al desconectarse el ESP32 el panel pasa a "apagada".
- Bug extra: `_lastAuthMs` solo se fijaba al autenticar, por lo que el fail-safe `max_offline_min` apagaba la bomba ~5 min después aunque el WebSocket siguiera vivo. Ahora se refresca mientras hay sesión.
- `docs/WIRING.md`: pull-up/pull-down según polaridad y advertencia NO/NC.

## 2. Interruptor
- `panel`: los botones "Encender/Apagar" se sustituyen por un interruptor único, sin confirmación, que refleja el estado real. Se bloquea si el dispositivo está offline/sin vincular.
- Interruptor de "Llenado automático" junto al de la bomba.
- Apagar a mano pausa el automático (30 min, `MANUAL_HOLD_MINUTES`) para que no se reencienda a los 2 s.

## 3. Calibración
- Campos: altura del sensor sobre el fondo, altura máxima del agua sobre el fondo, distancia sensor→espejo (calculada), capacidad.
- Botones "Medir fondo" / "Medir máximo": mediana de las últimas lecturas (mín. 3, dispersión ≤ 15 mm), con validaciones. Nuevo evento `calibrate`.
- Se muestra altura del agua (mm), % y litros (el cálculo de litros se mantiene).

## 4. Niveles y rellenado automático
- Mínimo, máximo y activar/desactivar ya existían; ahora con validación (separación ≥ 5 puntos, altura útil ≥ 20 mm) y avisos al cambiar solo.
