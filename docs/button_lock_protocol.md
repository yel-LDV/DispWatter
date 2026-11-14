# Protocolo de Bloqueo Remoto de Botones

## Resumen

El panel web puede bloquear o desbloquear cada botón físico individualmente enviando
un comando WebSocket al ESP32. El firmware ignora las presiones de los botones
bloqueados sin necesidad de recompilar ni desconectar cables.

---

## Comando WebSocket: `button_lock`

### Del panel → ESP32

```json
{
    "command": "button_lock",
    "request_id": "abc-123",
    "button_id": 5,
    "locked": true
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `command` | string | `"button_lock"` |
| `request_id` | string | ID único para correlacionar la respuesta |
| `button_id` | int | ID del botón (1–6, ver tabla abajo) |
| `locked` | bool | `true` = bloquear, `false` = desbloquear |

### ESP32 → Panel (respuesta ACK)

Éxito:
```json
{
    "event": "ack",
    "request_id": "abc-123",
    "ok": true
}
```

Error (callback no registrado):
```json
{
    "event": "ack",
    "request_id": "abc-123",
    "ok": false,
    "error": "button_lock_unavailable"
}
```

Error (no autenticado):
```json
{
    "event": "ack",
    "request_id": "abc-123",
    "ok": false,
    "error": "unauthorized"
}
```

---

## IDs de Botones

| ID | Botón | GPIO | Función |
|---|---|---|---|
| 1 | UP (▲) | GPIO 15 | Navegar arriba / aumentar |
| 2 | DOWN (▼) | GPIO 14 | Navegar abajo / disminuir |
| 3 | LEFT (◄) | GPIO 19 | Página anterior |
| 4 | RIGHT (►) | GPIO 13 | Página siguiente |
| 5 | OK (●) | GPIO 27 | Seleccionar / confirmar |
| 6 | BACK (↩) | GPIO 17 | Volver al menú central |

> El botón POWER (GPIO 32) no tiene ID y no se puede bloquear — solo despierta del deep sleep.

---

## Integración en `main.cpp`

### 1. Instanciar los botones

```cpp
#include "Button.h"
#include "config.h"

Button btnUp    (BTN_ID_UP,    BTN_UP_PIN);
Button btnDown  (BTN_ID_DOWN,  BTN_DOWN_PIN);
Button btnLeft  (BTN_ID_LEFT,  BTN_LEFT_PIN);
Button btnRight (BTN_ID_RIGHT, BTN_RIGHT_PIN);
Button btnOk    (BTN_ID_OK,    BTN_OK_PIN);
Button btnBack  (BTN_ID_BACK,  BTN_BACK_PIN);

Button* allButtons[] = {&btnUp, &btnDown, &btnLeft, &btnRight, &btnOk, &btnBack};
const int BUTTON_COUNT = 6;
```

### 2. Buscar botón por ID

```cpp
Button* getButtonById(uint8_t id) {
    for (int i = 0; i < BUTTON_COUNT; i++) {
        if (allButtons[i]->getId() == id) {
            return allButtons[i];
        }
    }
    return nullptr;
}
```

### 3. Registrar callbacks (estilo listeners de Minecraft)

```cpp
// Callback genérico para press de cualquier botón
void onButtonPress(uint8_t buttonId, unsigned long pressedMs) {
    Serial.printf("[BTN] Presionado ID=%u en %lums\n", buttonId, pressedMs);

    switch (buttonId) {
        case BTN_ID_UP:
            // Navegar arriba en el menú actual
            break;
        case BTN_ID_DOWN:
            // Navegar abajo en el menú actual
            break;
        case BTN_ID_LEFT:
            // Ir a la página anterior
            break;
        case BTN_ID_RIGHT:
            // Ir a la página siguiente
            break;
        case BTN_ID_OK:
            // Confirmar selección
            break;
        case BTN_ID_BACK:
            // Volver al menú central
            break;
    }
}

// Callback genérico para release de cualquier botón
void onButtonRelease(uint8_t buttonId, unsigned long pressedMs,
                     unsigned long releasedMs, unsigned long durationMs) {
    Serial.printf("[BTN] Soltado ID=%u duracion=%lums\n", buttonId, durationMs);

    // Ejemplo: detectar long press en OK (>1500ms)
    if (buttonId == BTN_ID_OK && durationMs > 1500) {
        Serial.println("[BTN] Long press en OK — cambiar modo");
    }
}

// Callback para bloqueo remoto desde el panel
void onButtonLockCommand(uint8_t buttonId, bool locked) {
    Button* btn = getButtonById(buttonId);
    if (btn) {
        btn->setLocked(locked);
        Serial.printf("[BTN] ID=%u %s\n", buttonId, locked ? "bloqueado" : "desbloqueado");
    } else {
        Serial.printf("[BTN] ERROR: ID=%u no encontrado\n", buttonId);
    }
}
```

### 4. Configurar en `setup()`

```cpp
void setup() {
    // ... inicialización existente ...

    // Inicializar botones
    btnUp.begin();
    btnDown.begin();
    btnLeft.begin();
    btnRight.begin();
    btnOk.begin();
    btnBack.begin();

    // Registrar callbacks genéricos
    btnUp.onPress(onButtonPress);
    btnUp.onRelease(onButtonRelease);
    btnDown.onPress(onButtonPress);
    btnDown.onRelease(onButtonRelease);
    btnLeft.onPress(onButtonPress);
    btnLeft.onRelease(onButtonRelease);
    btnRight.onPress(onButtonPress);
    btnRight.onRelease(onButtonRelease);
    btnOk.onPress(onButtonPress);
    btnOk.onRelease(onButtonRelease);
    btnBack.onPress(onButtonPress);
    btnBack.onRelease(onButtonRelease);

    // Registrar callback de bloqueo remoto en DispComm
    comm.onButtonLock(onButtonLockCommand);

    // ... resto de setup ...
}
```

### 5. Actualizar en `loop()`

```cpp
void loop() {
    // ... código existente ...

    // Actualizar estado de todos los botones
    btnUp.update();
    btnDown.update();
    btnLeft.update();
    btnRight.update();
    btnOk.update();
    btnBack.update();

    // ... resto del loop ...
}
```

---

## Uso desde el Panel Web

### Bloquear un botón individual

```javascript
// Bloquear el botón OK (ID=5)
ws.send(JSON.stringify({
    command: "button_lock",
    request_id: generateId(),
    button_id: 5,
    locked: true
}));
```

### Desbloquear un botón individual

```javascript
// Desbloquear el botón OK (ID=5)
ws.send(JSON.stringify({
    command: "button_lock",
    request_id: generateId(),
    button_id: 5,
    locked: false
}));
```

### Bloquear todos los botones de navegación

```javascript
// Bloquear todos excepto BACK (para que el usuario pueda salir)
for (let id of [1, 2, 3, 4, 5]) {
    ws.send(JSON.stringify({
        command: "button_lock",
        request_id: generateId(),
        button_id: id,
        locked: true
    }));
}
```

### Desbloquear todos los botones

```javascript
// Desbloquear todos
for (let id = 1; id <= 6; id++) {
    ws.send(JSON.stringify({
        command: "button_lock",
        request_id: generateId(),
        button_id: id,
        locked: false
    }));
}
```

---

## Casos de Uso

### 1. Bloqueo durante OTA

Cuando el firmware está actualizando, bloquea todos los botones para evitar
interferencias:

```
Panel → ESP32:  button_lock(button_id=1..6, locked=true)
                 ota_start(...)
                 ota_chunk(...)
                 ota_complete()
Panel → ESP32:  button_lock(button_id=1..6, locked=false)
```

### 2. Restricción de usuario

Un administrador puede bloquear los botones de navegación para que solo el
botón OK funcione (modo kiosco):

```
Panel → ESP32:  button_lock(button_id=1, locked=true)  // UP
Panel → ESP32:  button_lock(button_id=2, locked=true)  // DOWN
Panel → ESP32:  button_lock(button_id=3, locked=true)  // LEFT
Panel → ESP32:  button_lock(button_id=4, locked=true)  // RIGHT
Panel → ESP32:  button_lock(button_id=6, locked=true)  // BACK
// OK (ID=5) queda desbloqueado
```

### 3. Mantenimiento

Bloquear todos los botones durante mantenimiento sin desconectar nada:

```
Panel → ESP32:  button_lock(button_id=1..6, locked=true)
                 ... mantenimiento ...
Panel → ESP32:  button_lock(button_id=1..6, locked=false)
```

---

## Notas Importantes

1. **El bloqueo es volátil:** si el ESP32 se reinicia, todos los botones quedan
   desbloqueados. El panel debe re-aplicar los bloqueos después de reconectar.

2. **El botón POWER no se bloquea:** GPIO 32 solo despierta del deep sleep y
   no pasa por la librería Button.

3. **Los callbacks no se ejecutan si el botón está bloqueado:** ni `onPress`
   ni `onRelease` se disparan, ahorrando ciclos de CPU.

4. **El GPIO 4 está dañado** y no se usa en ninguna conexión de botones.
