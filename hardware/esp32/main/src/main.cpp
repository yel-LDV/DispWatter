#include <Arduino.h>

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
String displayOverrideLine0;
String displayOverrideLine1;

String sanitizeLcd(const String& input) {
    String out = input;
    // Transliterate common Spanish/European accented letters and replace
    // Unicode punctuation/icons that HD44780 character ROMs cannot render.
    out.replace("á", "a"); out.replace("é", "e"); out.replace("í", "i");
    out.replace("ó", "o"); out.replace("ú", "u"); out.replace("ü", "u"); out.replace("ñ", "n");
    out.replace("Á", "A"); out.replace("É", "E"); out.replace("Í", "I");
    out.replace("Ó", "O"); out.replace("Ú", "U"); out.replace("Ü", "U"); out.replace("Ñ", "N");
    out.replace("¿", ""); out.replace("¡", ""); out.replace("…", "...");
    out.replace("–", "-"); out.replace("—", "-"); out.replace("°", " deg");
    for (size_t i = 0; i < out.length(); ++i) {
        const uint8_t c = static_cast<uint8_t>(out[i]);
        if (c < 0x20 || c > 0x7e) out.setCharAt(i, ' ');
    }
    return out;
}

String lcdWindow(const String& raw, uint8_t row) {
    const String text = sanitizeLcd(raw);
    if (text.length() <= LCD_COLS) {
        String out = text;
        while (out.length() < LCD_COLS) out += ' ';
        return out;
    }

    // Bounce-scroll: displays the whole string, then scrolls back to its start.
    const unsigned maxOffset = text.length() - LCD_COLS;
    const unsigned period = maxOffset * 2;
    const unsigned tick = millis() / 300UL + row * 5U;
    const unsigned phase = period ? tick % period : 0;
    const unsigned offset = phase <= maxOffset ? phase : period - phase;
    return text.substring(offset, offset + LCD_COLS);
}

void showLines(const String& line0, const String& line1) {
    lcd.print(0, 0, lcdWindow(line0, 0));
    lcd.print(0, 1, lcdWindow(line1, 1));
}

void refreshLcd() {
    const unsigned long now = millis();
    if (now < displayOverrideUntil) {
        showLines(displayOverrideLine0, displayOverrideLine1);
        return;
    }
    const DeviceConfig& cfg = configStore.get();
    if (!configReady) {
        showLines("Config invalida", "Revisa /config");
    } else if (comm.isPendingClaim()) {
        showLines("Pendiente vinc.", cfg.deviceId);
    } else if (!net.isConnected()) {
        showLines(net.statusLine0(), net.statusLine1());
    } else if (!backendAuthenticated) {
        if (comm.backendFailureVisible()) showLines("Servicio no disp.", "Reintentando...");
        else showLines("Buscando servicio", cfg.deviceId);
    } else {
        String line1 = lastDistanceMm > 0.0f
            ? String(lastDistanceMm / 10.0f, 1) + " cm "
            : String("---- cm ");
        line1 += relay.state() ? "RELE ON" : "RELE OFF";
        showLines("Servidor OK", line1);
    }
}

void onRelayCommand(bool state) {
    if (state && (!net.isConnected() || !backendAuthenticated)) {
        relay.forceOff();
        Serial.println("[SAFE] Encendido rechazado: falta WiFi o backend autenticado");
        return;
    }
    relay.set(state);
    Serial.printf("[RELE] Estado: %s\n", state ? "ENCENDIDO" : "APAGADO");
}

void onDisplayCommand(const String& line0, const String& line1, bool clear) {
    displayOverrideLine0 = clear ? "" : line0;
    displayOverrideLine1 = clear ? "" : line1;
    displayOverrideUntil = millis() + 10000UL;
    showLines(displayOverrideLine0, displayOverrideLine1);
}

void onConnectionStatus(bool isConnected) {
    backendAuthenticated = isConnected;
    lastLcdRefresh = 0;
    if (!isConnected && relay.state()) {
        relay.forceOff();
        Serial.println("[SAFE] Backend desconectado: rele OFF");
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
    // Fail-safe first, before LCD, LittleFS, WiFi or backend startup.
    relay.begin(PIN_RELE, RELE_ON == LOW);
    lcd.init();
    lcd.onn();
    lcd.clean();
    showLines("DispWatter", "Iniciando...");

    configReady = configStore.begin();
    power.begin(configStore.get().wakePin, configStore.get().wakeActiveLow);
    if (!configReady) {
        relay.forceOff();
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
    showLines("Iniciando WiFi", "Rele: OFF");
}

void loop() {
    if (!configReady) {
        relay.forceOff();
        delay(2000);
        return;
    }
    net.update();
    comm.update();
    const unsigned long now = millis();
    const DeviceConfig& cfg = configStore.get();

    // Relay remains de-energized until WiFi and backend authentication are both live.
    if (!net.isConnected() || !backendAuthenticated) {
        if (relay.state()) Serial.println("[SAFE] Sin red/backend: apagando rele");
        relay.forceOff();
    }
    relay.guard(now, comm.lastAuthenticatedMs(),
                static_cast<unsigned long>(cfg.maxRelayOnMin) * 60000UL,
                static_cast<unsigned long>(cfg.maxOfflineMin) * 60000UL);

    if (now - lastSample >= cfg.sampleIntervalMs) {
        lastSample = now;
        const float distance = sensor.getMm();
        if (distance > 0.0f) {
            lastDistanceMm = distance;
            if (!comm.sendTelemetry(distance, relay.state()))
                Serial.println("[WS] Telemetria no enviada: ESP32 sin autenticar");
        } else {
            lastDistanceMm = -1.0f;
            if (relay.state()) {
                Serial.println("[SAFE] Sensor sin lectura valida: rele OFF");
                relay.forceOff();
            }
        }
    }
    if (now - lastStatus >= 60000UL) {
        lastStatus = now;
        comm.sendDeviceStatus();
    }
    if (now - lastLcdRefresh >= 100UL) {
        lastLcdRefresh = now;
        refreshLcd();
    }
    delay(5);
}
