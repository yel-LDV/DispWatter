#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

// ==========================================
// CONFIGURACIÓN GENERADA AUTOMÁTICAMENTE
// ==========================================
#define WIFI_SSID          "MiWiFi"
#define WIFI_PASS          "12345678"

#define BACKEND_HOST       "192.168.1.100"
#define BACKEND_PORT       8765
#define BACKEND_PATH       "/ws/device"

#define DEVICE_ID          "WATTER-001"
#define DEVICE_PASS        "clave_secreta_99"

#define PIN_TRIG           5
#define PIN_ECHO           18
#define PIN_RELE           4
#define LCD_I2C_ADDR       0x27

#define RELE_ON            LOW
#define RELE_OFF           HIGH

#define INTERVALO_MUESTREO_MS  2000
#define INTERVALO_REINTENTO_MS 5000

#endif // DEVICE_CONFIG_H
