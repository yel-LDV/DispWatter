#include <Arduino.h>
#include <I2C.h>
#include "HC_SR04.h"
#include <Crypto.h>
#include <DispComm.h>
#include "config.h"

// ==========================================
// MÓDULOS DEL DISPOSITIVO
// ==========================================
I2C lcd(LCD_I2C_ADDR);
HC_SR04 sensor(PIN_TRIG, PIN_ECHO, 5);
Crypto crypto(DEVICE_ID, DEVICE_PASS);
DispComm comm(crypto);

// Variables de Control y Temporización
bool servidorConectado = false;
unsigned long ultimoIntento = 0;
unsigned long ultimoMuestreo = 0;

// ==========================================
// SETUP
// ==========================================
void setup() {
    Serial.begin(115200);
    delay(200);

    // 1. Inicializar Relé en estado apagado
    pinMode(PIN_RELE, OUTPUT);
    digitalWrite(PIN_RELE, RELE_OFF);

    // 2. Inicializar Pantalla LCD y Sensor
    lcd.init();
    lcd.onn();
    lcd.clean();
    lcd.print(0, 0, DEVICE_NAME);
    lcd.print(0, 1, String("v") + FIRMWARE_VERSION + " Init");
    sensor.init();
    delay(1200);

    // 3. Asignar metadatos del dispositivo para el handshake
    comm.setDeviceInfo(DEVICE_NAME, DEVICE_LOCATION, FIRMWARE_VERSION);

    // 4. Mostrar estado inicial de búsqueda de WiFi
    lcd.clean();
    lcd.print(0, 0, "Buscando WiFi...");
    lcd.print(0, 1, String(NUM_WIFI_NETWORKS) + " redes config.");

    // 5. Registrar Callbacks de Comunicación
    // Callback: Orden de Relé enviada por el Backend
    comm.onRelayCommand([](bool state) {
        digitalWrite(PIN_RELE, state ? RELE_ON : RELE_OFF);
        Serial.printf("[RELE] Estado: %s\n", state ? "ENCENDIDO" : "APAGADO");
    });

    // Callback: Texto remoto para LCD enviado por el Backend
    comm.onDisplayCommand([](const String &line0, const String &line1, bool clear) {
        if (servidorConectado) {
            if (clear) lcd.clean();
            if (line0.length() > 0) {
                lcd.clean(0);
                lcd.print(0, 0, line0);
            }
            if (line1.length() > 0) {
                lcd.clean(1);
                lcd.print(0, 1, line1);
            }
        }
    });

    // Callback: Cambio de estado de conexión con el Servidor Backend
    comm.onConnectionStatus([](bool isConnected) {
        servidorConectado = isConnected;
        lcd.clean();

        if (isConnected) {
            Serial.println("[WS] ¡Conectado y Autenticado con éxito en Backend!");
            lcd.print(0, 0, "Servidor Conect.");
            lcd.print(0, 1, String("ID: ") + DEVICE_ID);
        } else {
            Serial.println("[WS] Servidor no conectado. Esperando vinculación...");
            lcd.print(0, 0, "Servidor no conn");
            lcd.print(0, 1, String("ID: ") + DEVICE_ID);
        }
    });

    // 6. Iniciar la conexión con la lista de redes WiFi
    comm.begin(WIFI_NETWORKS, NUM_WIFI_NETWORKS, BACKEND_HOST, BACKEND_PORT, BACKEND_PATH);
}

// ==========================================
// LOOP PRINCIPAL
// ==========================================
void loop() {
    // Atender tareas de red y WebSocket
    comm.update();

    unsigned long ahora = millis();

    // Gestión periódica de estados de conexión (cada INTERVALO_REINTENTO_MS)
    if (ahora - ultimoIntento >= INTERVALO_REINTENTO_MS) {
        ultimoIntento = ahora;

        if (!comm.isWiFiConnected()) {
            Serial.println("[WIFI] Buscando redes disponibles...");
            lcd.clean(0);
            lcd.print(0, 0, "Buscando WiFi...");
            lcd.clean(1);
            lcd.print(0, 1, "Sin conexion");
        } else if (!servidorConectado) {
            String connectedSSID = comm.getConnectedSSID();
            Serial.printf("[WIFI] Conectado a '%s'. Reintentando ws://%s:%d%s | Dispositivo ID: %s\n",
                          connectedSSID.c_str(), BACKEND_HOST, BACKEND_PORT, BACKEND_PATH, DEVICE_ID);
            lcd.clean(0);
            lcd.print(0, 0, "Servidor no conn");
            lcd.clean(1);
            lcd.print(0, 1, String("ID: ") + DEVICE_ID);
        }
    }

    // Muestreo ultrasónico y telemetría hacia el Backend (cada INTERVALO_MUESTREO_MS)
    if (servidorConectado && (ahora - ultimoMuestreo >= INTERVALO_MUESTREO_MS)) {
        ultimoMuestreo = ahora;

        float distanciaMm = sensor.getMm();
        bool releActivo = (digitalRead(PIN_RELE) == RELE_ON);

        if (distanciaMm > 0) {
            comm.sendTelemetry(distanciaMm, releActivo);
            Serial.printf("[TELEMETRIA] Distancia: %.1f mm | Rele: %d\n", distanciaMm, releActivo);
        }
    }
}
