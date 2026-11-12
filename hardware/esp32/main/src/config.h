#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

// ==========================================
// CONFIGURACIÓN ESTÁTICA DE HARDWARE
// ==========================================
// Este archivo NO contiene credenciales ni datos de usuario.
// La configuración real (WiFi, backend, identidad) vive en
// /config.json dentro de LittleFS y se genera desde
// hardware/esp32/main/device_config.json.

// Pines
#define PIN_TRIG           5
#define PIN_ECHO           18
#define PIN_RELE           23
#define LCD_I2C_ADDR       0x27
#define WAKE_PIN           33
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
