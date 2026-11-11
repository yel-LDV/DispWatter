#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

#include <DispComm.h>

// ==========================================
// CONFIGURACIÓN DE REDES WIFI (MÚLTIPLES)
// ==========================================
// El ESP32 escaneará y se conectará automáticamente a la red disponible con mejor señal
const WiFiCred WIFI_NETWORKS[] = {
    {"MiWiFi_Principal", "12345678"},
    {"MiWiFi_Secundaria", "87654321"},
    {"Red_Movil_Hotspot", "clavehotspot"}
};
const size_t NUM_WIFI_NETWORKS = sizeof(WIFI_NETWORKS) / sizeof(WIFI_NETWORKS[0]);

// ==========================================
// CONFIGURACIÓN DEL SERVIDOR BACKEND
// ==========================================
#define SERVER_MODE        "local"        // "local" o "remote"
#define BACKEND_HOST       "192.168.1.100"
#define BACKEND_PORT       8765
#define BACKEND_PATH       "/ws/device"

// ==========================================
// IDENTIDAD Y METADATOS DEL DISPOSITIVO
// ==========================================
#define DEVICE_ID          "WATTER-001"
#define DEVICE_PASS        "clave_secreta_disp_99"
#define DEVICE_NAME        "Bebedero Huerto"
#define DEVICE_LOCATION    "Patio Principal"
#define FIRMWARE_VERSION   "1.0.0"

// ==========================================
// PINES Y PARÁMETROS DE HARDWARE
// ==========================================
#define PIN_TRIG           5
#define PIN_ECHO           18
#define PIN_RELE           4
#define LCD_I2C_ADDR       0x27

#define RELE_ON            LOW
#define RELE_OFF           HIGH

#define INTERVALO_MUESTREO_MS  2000
#define INTERVALO_REINTENTO_MS 5000

#endif // DEVICE_CONFIG_H
