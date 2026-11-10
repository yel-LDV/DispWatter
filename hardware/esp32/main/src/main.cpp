#include <Arduino.h>
#include <I2C.h>
#include <HC_SR04.h>
#include <Crypto.h>
#include <DispComm.h>

// ==========================================
// CONFIGURACIÓN DE PINES Y PARÁMETROS
// ==========================================
const uint8_t PIN_TRIG = 5;
const uint8_t PIN_ECHO = 18;
const uint8_t PIN_RELE = 4;

const int RELE_ON = LOW;   // Relé activo en nivel bajo
const int RELE_OFF = HIGH;

// Credenciales de Red y Backend
const char *WIFI_SSID     = "TU_RED_WIFI";
const char *WIFI_PASS     = "TU_PASSWORD_WIFI";
const char *BACKEND_HOST  = "192.168.1.100";  // IP del servidor backend
const uint16_t BACKEND_PORT = 8765;
const char *BACKEND_PATH  = "/ws/device";

// Credenciales del Dispositivo para Criptografía y Claiming
const char *DEVICE_ID     = "WATTER-001";
const char *DEVICE_PASS   = "clave_secreta_disp_99";

// ==========================================
// MÓDULOS DEL SISTEMA
// ==========================================
I2C lcd(0x27);
HC_SR04 sensor(PIN_TRIG, PIN_ECHO, 5);
Crypto crypto(DEVICE_ID, DEVICE_PASS);
DispComm comm(crypto);

unsigned long ultimoMuestreo = 0;
const unsigned long INTERVALO_MUESTREO_MS = 2000;

// ==========================================
// SETUP
// ==========================================
void setup() {
    Serial.begin(115200);

    // Inicializar Relé (apagado por defecto)
    pinMode(PIN_RELE, OUTPUT);
    digitalWrite(PIN_RELE, RELE_OFF);

    // Inicializar Pantalla LCD y Sensor
    lcd.init();
    lcd.onn();
    lcd.clean();
    lcd.print(0, 0, "DispWatter Init");
    sensor.init();

    // Callbacks: Control de Relé remoto desde Backend
    comm.onRelayCommand([](bool state) {
        digitalWrite(PIN_RELE, state ? RELE_ON : RELE_OFF);
        Serial.printf("[RELE] Estado cambiado a: %s\n", state ? "ENCENDIDO" : "APAGADO");
    });

    // Callbacks: Control de Pantalla LCD remoto desde Backend
    comm.onDisplayCommand([](const String &line0, const String &line1, bool clear) {
        if (clear) lcd.clean();
        if (line0.length() > 0) {
            lcd.clean(0);
            lcd.print(0, 0, line0);
        }
        if (line1.length() > 0) {
            lcd.clean(1);
            lcd.print(0, 1, line1);
        }
    });

    // Callbacks: Estado de conexión con el Servidor
    comm.onConnectionStatus([](bool isConnected) {
        if (isConnected) {
            Serial.println("[WS] Autenticado con éxito en Backend");
            lcd.print(0, 1, "WS Conectado");
        } else {
            Serial.println("[WS] Desconectado o error de autenticación");
            lcd.print(0, 1, "WS Desconectado");
        }
    });

    // Iniciar conexión de red y WebSockets
    comm.begin(WIFI_SSID, WIFI_PASS, BACKEND_HOST, BACKEND_PORT, BACKEND_PATH);
}

// ==========================================
// LOOP
// ==========================================
void loop() {
    // Mantener la pila de red y WebSocket activa
    comm.update();

    // Muestreo y reporte periódico hacia el Backend
    unsigned long ahora = millis();
    if (ahora - ultimoMuestreo >= INTERVALO_MUESTREO_MS) {
        ultimoMuestreo = ahora;

        float distanciaMm = sensor.getMm();
        bool releActivo = (digitalRead(PIN_RELE) == RELE_ON);

        if (distanciaMm > 0) {
            comm.sendTelemetry(distanciaMm, releActivo);
            Serial.printf("[TELEMETRIA] Distancia: %.1f mm | Rele: %d\n", distanciaMm, releActivo);
        }
    }
}
