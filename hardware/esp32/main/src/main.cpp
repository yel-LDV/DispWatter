#include <Arduino.h>
#include <esp_system.h>

#include <Crypto.h>
#include <DispComm.h>
#include <I2C.h>

#include "HC_SR04.h"
#include "config.h"
#include "ConfigStore.h"
#include "NetManager.h"
#include "PowerManager.h"
#include "Relay.h"

I2C lcd(LCD_I2C_ADDR);
HC_SR04 sensor(PIN_TRIG, PIN_ECHO, 5);
ConfigStore configStore;
NetManager net(configStore);
Crypto crypto;
DispComm comm(crypto, configStore, net);
Relay relay;
PowerManager power;

unsigned long lastSample = 0;
unsigned long lastLcdRefresh = 0;
unsigned long lastStatus = 0;
unsigned long displayOverrideUntil = 0;
float lastDistanceMm = -1.0f;
bool backendAuthenticated = false;
bool configReady = false;

String padLine(const String& text) {
    String out = text;
    if (out.length() > LCD_COLS) out = out.substring(0, LCD_COLS);
    while (out.length() < LCD_COLS) out += ' ';
    return out;
}

void showLines(const String& line0, const String& line1) {
    lcd.print(0, 0, padLine(line0));
    lcd.print(0, 1, padLine(line1));
}

void refreshLcd() {
    if (millis() < displayOverrideUntil) return;
    const DeviceConfig& cfg = configStore.get();

    if (!configReady) {
        showLines("Config invalida", "Revisa /config");
    } else if (comm.isPendingClaim()) {
        showLines("Pendiente vinc.", cfg.deviceId);
    } else if (!net.isConnected()) {
        showLines("Buscando WiFi", cfg.deviceId);
    } else if (!backendAuthenticated) {
        if (comm.backendFailureVisible()) {
            showLines("Servicio no disp.", "Reintentando...");
        } else {
            showLines("Buscando servicio", cfg.deviceId);
        }
    } else {
        String line1 = lastDistanceMm > 0.0f
            ? String(lastDistanceMm / 10.0f, 1) + " cm "
            : String("---- cm ");
        line1 += relay.state() ? "RELE ON" : "RELE OFF";
        showLines("Servidor OK", line1);
    }
}

void onRelayCommand(bool state) {
    relay.set(state);
    Serial.printf("[RELE] Estado: %s\n", state ? "ENCENDIDO" : "APAGADO");
}

void onDisplayCommand(const String& line0, const String& line1, bool clear) {
    if (clear) lcd.clean();
    if (line0.length() > 0) lcd.print(0, 0, padLine(line0));
    if (line1.length() > 0) lcd.print(0, 1, padLine(line1));
    displayOverrideUntil = millis() + 10000;
}

void onConnectionStatus(bool isConnected) {
    backendAuthenticated = isConnected;
    lastLcdRefresh = 0;
    if (!isConnected && relay.state()) {
        relay.forceOff();
        Serial.println("[SAFE] Backend desconectado: relé apagado");
    }
    Serial.printf("[WS] %s\n", isConnected ? "Autenticado" : "Sin autenticar");
}

void onReboot() {
    relay.forceOff();
    Serial.println("[SYS] Reinicio solicitado desde el panel");
    Serial.flush();
    delay(100);
    ESP.restart();
}

void onSleep(uint16_t minutes) {
    relay.forceOff();
    power.sleepForMinutes(minutes);
}

void onFactoryReset() {
    relay.forceOff();
    configStore.factoryReset();
    Serial.println("[SYS] Reset de fabrica solicitado desde el panel");
    Serial.flush();
    delay(100);
    ESP.restart();
}

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.printf("[BOOT] reset_reason=%d\n", static_cast<int>(esp_reset_reason()));
    relay.begin(PIN_RELE, RELE_ON == LOW);
    lcd.init();
    lcd.onn();
    lcd.clean();
    showLines("DispWatter", "Iniciando...");

    configReady = configStore.begin();
    power.begin(configStore.get().wakePin, configStore.get().wakeActiveLow);
    if (!configReady) {
        Serial.printf("[CONFIG] %s\n", configStore.lastError().c_str());
        showLines("Config invalida", "Revisa /config");
        return;
    }

    crypto.setKeyHash(configStore.get().keyHash);
    comm.setWakeReason(power.wakeReasonString());
    Serial.printf("[CONFIG] Dispositivo %s (%s)\n",
                  configStore.get().deviceId.c_str(), configStore.get().deviceName.c_str());
    Serial.printf("[POWER] Motivo de arranque: %s\n", power.wakeReasonString().c_str());

    sensor.init();
    net.begin();
    comm.onRelayCommand(onRelayCommand);
    comm.onDisplayCommand(onDisplayCommand);
    comm.onConnectionStatus(onConnectionStatus);
    comm.onReboot(onReboot);
    comm.onSleep(onSleep);
    comm.onFactoryReset(onFactoryReset);
    comm.begin();
    showLines("Buscando WiFi", configStore.get().deviceId);
}

void loop() {
    if (!configReady) {
        delay(2000);
        return;
    }

    net.update();
    comm.update();
    const unsigned long now = millis();
    const DeviceConfig& cfg = configStore.get();

    // Fail-safe inmediato: el relé no debe quedar activo sin Wi-Fi/backend.
    if ((!net.isConnected() || !backendAuthenticated) && relay.state()) {
        relay.forceOff();
        Serial.println("[SAFE] Sin WiFi o backend: relé apagado");
    }
    relay.guard(now, comm.lastAuthenticatedMs(),
                static_cast<unsigned long>(cfg.maxRelayOnMin) * 60000UL,
                static_cast<unsigned long>(cfg.maxOfflineMin) * 60000UL);

    if (now - lastSample >= cfg.sampleIntervalMs) {
        lastSample = now;
        const float distance = sensor.getMm();
        if (distance > 0.0f) {
            lastDistanceMm = distance;
            if (!comm.sendTelemetry(distance, relay.state())) {
                Serial.println("[WS] Telemetría no enviada: dispositivo no autenticado");
            }
        } else {
            lastDistanceMm = -1.0f;
            if (relay.state()) {
                Serial.println("[SAFE] Lectura del sensor inválida: relé apagado");
                relay.forceOff();
            }
        }
    }

    if (now - lastStatus >= 60000UL) {
        lastStatus = now;
        comm.sendDeviceStatus();
    }
    if (now - lastLcdRefresh >= 250UL) {
        lastLcdRefresh = now;
        refreshLcd();
    }
    static unsigned long lastStackLog = 0;
    if (now - lastStackLog >= 30000UL) {
        lastStackLog = now;
        Serial.printf("[SYS] stack libre loopTask: %u bytes, heap libre: %u\n",
                      static_cast<unsigned>(uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t)),
                      static_cast<unsigned>(ESP.getFreeHeap()));
    }
    delay(5);
}
