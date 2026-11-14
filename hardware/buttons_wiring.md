# Conexión de Botones — Matriz 3×2 + Power

## Resumen

Los 6 botones de navegación se conectan como **individual a GND** con pull-up interno
(`INPUT_PULLUP`). No se necesita una matriz electrónica real; el término "matriz 3×2"
se refiere al **disposición física** de los botones en el panel frontal.

Cada botón tiene un **ID único** que se usa en los callbacks del firmware, similar a
los listeners de plugins de Minecraft.

---

## Disposición Física (vista frontal del panel)

```
┌──────────────────────────────────────┐
│          DispWatter Panel            │
├────────────┬────────────┬────────────┤
│   ▲ UP     │   ► RIGHT  │   ● OK     │   ← Fila 0
│  (ID=1)    │  (ID=4)    │  (ID=5)    │
├────────────┼────────────┼────────────┤
│   ◄ LEFT   │   ▼ DOWN   │   ↩ BACK   │   ← Fila 1
│  (ID=3)    │  (ID=2)    │  (ID=6)    │
└────────────┴────────────┴────────────┘

        [POWER]  ← Botón independiente (GPIO 32) para despertar del deep sleep
```

---

## Tabla de Conexiones

| Botón | ID | GPIO ESP32 | Conexión | Descripción |
|---|---|---|---|---|
| **UP (▲)** | 1 | GPIO 15 | Botón → GND | Navegar arriba / aumentar valor |
| **DOWN (▼)** | 2 | GPIO 14 | Botón → GND | Navegar abajo / disminuir valor |
| **LEFT (◄)** | 3 | GPIO 19 | Botón → GND | Ir atrás / página anterior |
| **RIGHT (►)** | 4 | GPIO 13 | Botón → GND | Ir adelante / página siguiente |
| **OK (●)** | 5 | GPIO 27 | Botón → GND | Seleccionar / confirmar |
| **BACK (↩)** | 6 | GPIO 17 | Botón → GND | Volver al menú central |
| **POWER** | — | GPIO 32 | Botón → GND | Despertar del deep sleep |

> **GPIO 4 está dañado** y no se usa en ninguna conexión.

---

## Diagrama de Cableado por Botón

Cada botón se conecta igual:

```
     3.3V (interno, pull-up)
        │
        └───[INPUT_PULLUP]─── GPIO XX
                              │
                         ┌────┴────┐
                         │  BOTÓN  │
                         │ (tactil)│
                         └────┬────┘
                              │
                             GND
```

### Conexión detallada

```
ESP32 Dev Board
├── GPIO 15  ──► Botón UP     ──► GND
├── GPIO 14  ──► Botón DOWN   ──► GND
├── GPIO 19  ──► Botón LEFT   ──► GND
├── GPIO 13  ──► Botón RIGHT  ──► GND
├── GPIO 27  ──► Botón OK     ──► GND
├── GPIO 17  ──► Botón BACK   ──► GND
├── GPIO 32  ──► Botón POWER  ──► GND
└── GND      ──► Tierra común de todos los botones
```

---

## Mapa Completo de Pines GPIO del ESP32

### En uso por hardware existente

| GPIO | Uso | Módulo |
|---|---|---|
| 5 | HC-SR04 Trig | Sensor ultrasónico |
| 18 | HC-SR04 Echo | Sensor ultrasónico |
| 21 | I2C SDA | LCD 16×2 |
| 22 | I2C SCL | LCD 16×2 |
| 23 | Relé (bomba) | Control de bomba |
| 33 | Wake pin | Deep sleep (RTC GPIO) |

### En uso por botones

| GPIO | Uso |
|---|---|
| 13 | Botón RIGHT (ID=4) |
| 19 | Botón LEFT (ID=3) |
| 14 | Botón DOWN (ID=2) |
| 15 | Botón UP (ID=1) |
| 27 | Botón OK (ID=5) |
| 17 | Botón BACK (ID=6) |
| 32 | Botón POWER |

### No disponibles

| GPIO | Razón |
|---|---|
| 0, 2, 3 | UART / Bootstrap (flash) |
| 4 | **Dañado** |
| 6–11 | SPI Flash interna |
| 34–39 | Solo entrada analógica (sin OUTPUT) |

---

## Componentes Necesarios

- **7 botones táctiles** (6 de navegación + 1 de power)
  - Tipo recomendado: tactil 12mm, normalmente abierto (NO)
- **Cables jumper** macho-hembra o macho-macho según la placa
- **Placa base** para montar los botones en disposición 3×2

---

## Comportamiento Eléctrico

- **Modo del pin:** `INPUT_PULLUP` (resistencia pull-up interna de ~40kΩ)
- **Estado en reposo:** `HIGH` (3.3V lógico por el pull-up)
- **Estado al presionar:** `LOW` (conectado a GND)
- **Debounce:** 50 ms por botón (manejado en software por la librería `Button`)
- **No se necesitan resistencias externas** — el pull-up interno es suficiente

---

## Bloqueo Remoto desde el Panel

Cada botón se puede **bloquear/desbloquear** individualmente desde el panel web
vía WebSocket. Cuando un botón está bloqueado:

- El firmware ignora completamente las presiones físicas
- Los callbacks `onPress` y `onRelease` no se ejecutan
- El estado `isLocked()` retorna `true`

Esto permite deshabilitar botones específicos sin modificar el firmware ni desconectar
cables, útil para:

- Evitar que un usuario modifique configuraciones críticas
- Deshabilitar navegación durante OTA
- Bloqueo parental o de mantenimiento

---

## Integración con el Firmware

### Librería `Button/`

Cada botón se instancia con su ID y pin:

```cpp
#include "Button.h"

Button btnUp    (BTN_ID_UP,    BTN_UP_PIN);
Button btnDown  (BTN_ID_DOWN,  BTN_DOWN_PIN);
Button btnLeft  (BTN_ID_LEFT,  BTN_LEFT_PIN);
Button btnRight (BTN_ID_RIGHT, BTN_RIGHT_PIN);
Button btnOk    (BTN_ID_OK,    BTN_OK_PIN);
Button btnBack  (BTN_ID_BACK,  BTN_BACK_PIN);
```

### Callbacks (estilo listeners de Minecraft)

```cpp
// Se ejecuta cuando cualquier botón se presiona
void onAnyButtonPress(uint8_t buttonId, unsigned long pressedMs) {
    Serial.printf("[BTN] Presionado ID=%u en %lums\n", buttonId, pressedMs);
}

// Se ejecuta cuando cualquier botón se suelta
void onAnyButtonRelease(uint8_t buttonId, unsigned long pressedMs,
                        unsigned long releasedMs, unsigned long durationMs) {
    Serial.printf("[BTN] Soltado ID=%u duracion=%lums\n", buttonId, durationMs);
}

// En setup():
btnUp.onPress(onAnyButtonPress);
btnUp.onRelease(onAnyButtonRelease);
// ... repetir para cada botón
```

### Loop principal

```cpp
void loop() {
    btnUp.update();
    btnDown.update();
    btnLeft.update();
    btnRight.update();
    btnOk.update();
    btnBack.update();
    // ...
}
```

### Bloqueo desde el panel

```cpp
// El backend envía un comando WebSocket para bloquear/desbloquear
// {"cmd": "button_lock", "buttonId": 5, "locked": true}
void onButtonLockCommand(uint8_t buttonId, bool locked) {
    Button* btn = getButtonById(buttonId);
    if (btn) {
        btn->setLocked(locked);
        Serial.printf("[BTN] ID=%u %s\n", buttonId, locked ? "bloqueado" : "desbloqueado");
    }
}
```
