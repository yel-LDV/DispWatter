#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

// ==========================================
// CONFIGURACIÓN ESTÁTICA DE HARDWARE
// ==========================================
// Este archivo NO contiene credenciales ni datos de usuario.
// La configuración real (WiFi, backend, identidad) vive en
// /config.json dentro de LittleFS y se genera desde
// hardware/esp32/main/device_config.json.

// ==========================================
// Pines de hardware fijo
// ==========================================
// GPIO 4 está dañado y NO se puede usar.
//
// Mapa completo de pines ESP32:
//   En uso:  5 (Trig), 18 (Echo), 21 (SDA), 22 (SCL), 23 (Relé), 32 (Power), 33 (Wake)
//   Dañado:  4
//   UART/Flash: 0, 2, 3  (evitar)
//   SPI Flash:  6, 7, 8, 9, 10, 11  (evitar)
//   Analog-only input: 34, 35, 36, 39  (solo lectura, no OUTPUT)
//   Disponibles para botones: 13, 14, 15, 17, 19, 27

#define PIN_TRIG           5
#define PIN_ECHO           18
#define PIN_RELE           23
#define LCD_I2C_ADDR       0x27
#define WAKE_PIN           33

// ==========================================
// Botones de navegación (matriz 3x2)
// ==========================================
// Cada botón tiene un ID único para los callbacks.
// Se conectan a GND al presionarse (INPUT_PULLUP, activo en LOW).
//
// Matriz física 3 columnas x 2 filas:
//
//   [Fila 0]  [BTN_UP    ]  [BTN_RIGHT  ]  [BTN_OK     ]
//   [Fila 1]  [BTN_LEFT  ]  [BTN_DOWN   ]  [BTN_BACK   ]
//
// El botón de power (GPIO 32) es independiente, solo despierta del deep sleep.

// IDs únicos por botón (para callbacks)
#define BTN_ID_UP          1
#define BTN_ID_DOWN        2
#define BTN_ID_LEFT        3
#define BTN_ID_RIGHT       4
#define BTN_ID_OK          5
#define BTN_ID_BACK        6

// Pines GPIO asignados a cada botón
#define BTN_UP_PIN         15
#define BTN_DOWN_PIN       14
#define BTN_LEFT_PIN       19
#define BTN_RIGHT_PIN      13
#define BTN_OK_PIN         27
#define BTN_BACK_PIN       17

// Botón de power (despertar del deep sleep)
#define BTN_POWER_PIN      32

// Relé: polaridad por defecto de la lógica del módulo.
//   1 = módulo activo en LOW  (IN a GND  -> bobina activada)
//   0 = módulo activo en HIGH (IN a 3,3V -> bobina activada)
// Se puede sobrescribir sin recompilar con "relay.active_low" en config.json.
// Si el panel muestra la bomba ENCENDIDA cuando está apagada (o al revés),
// cambia este valor (o el JSON) y revisa docs/WIRING.md (pull-up / pull-down).
#define RELE_ACTIVE_LOW_DEFAULT  0

// Límites
#define MAX_WIFI_NETWORKS  8

// Valores por defecto si el JSON no los define
#define DEFAULT_SAMPLE_INTERVAL_MS  2000
#define DEFAULT_RETRY_MS            5000
#define DEFAULT_MAX_RELAY_ON_MIN    10
#define DEFAULT_MAX_OFFLINE_MIN     5
#define DEFAULT_SLEEP_TIMER_MIN     60

#endif // DEVICE_CONFIG_H
