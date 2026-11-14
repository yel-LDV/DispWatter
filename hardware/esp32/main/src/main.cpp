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
#include "OtaReceiver.h"
#include "Button.h"
#include <SettingsMenu.h>
#include <menu_definitions.h>

I2C lcd(LCD_I2C_ADDR);
HC_SR04 sensor(PIN_TRIG, PIN_ECHO, 5);
ConfigStore configStore;
NetManager net(configStore);
Crypto crypto;
DispComm comm(crypto, configStore, net);
Relay relay;
PowerManager power;
OtaReceiver ota;

// Botones de navegación (IDs según config.h)
Button btnUp(1, BTN_UP_PIN);
Button btnDown(2, BTN_DOWN_PIN);
Button btnLeft(3, BTN_LEFT_PIN);
Button btnRight(4, BTN_RIGHT_PIN);
Button btnOk(5, BTN_OK_PIN);
Button btnBack(6, BTN_BACK_PIN);

// Menú de ajustes
SettingsMenu settingsMenu;

unsigned long lastSample = 0;
unsigned long lastLcdRefresh = 0;
unsigned long lastStatus = 0;
unsigned long displayOverrideUntil = 0;
float lastDistanceMm = -1.0f;
float lastPercent = -1.0f;          // recibido del backend
float lastLiters = -1.0f;
unsigned long lastLevelMs = 0;      // instante de la última recepción
const unsigned long LEVEL_STALE_MS = 15000UL;
bool backendAuthenticated = false;
bool configReady = false;
unsigned long pumpTestOffAt = 0;  // Timer para prueba de bomba 10s

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

// Claim code display state
bool showingClaimCode = false;
String currentClaimCode;
unsigned long claimCodeExpiry = 0;
unsigned long claimFailUntil = 0;  // block new claims after expiry

void onClaimCode(const String& code, int expiresIn) {
    showingClaimCode = true;
    currentClaimCode = code;
    claimCodeExpiry = millis() + (unsigned long)expiresIn * 1000UL;
    claimFailUntil = 0;
    lcd.clean();
    lcd.print(0, 0, padLine("CODIGO CLAIM:"));
    String line = "  " + code + " ";
    line += String(expiresIn);
    line += "s     ";
    lcd.print(0, 1, padLine(line));
    Serial.printf("[CLAIM] Código %s por %ds\n", code.c_str(), expiresIn);
}

void onClaimVerified() {
    showingClaimCode = false;
    currentClaimCode = "";
    claimCodeExpiry = 0;
    claimFailUntil = 0;
    lcd.clean();
    lcd.print(0, 0, padLine("VINCULADO"));
    lcd.print(0, 1, padLine("Dispositivo activo"));
    Serial.println("[CLAIM] Dispositivo vinculado exitosamente");
}

void updateClaimCountdown() {
    if (!showingClaimCode) return;
    
    unsigned long now = millis();
    if (now >= claimCodeExpiry) {
        // Code expired - show failure message
        showingClaimCode = false;
        currentClaimCode = "";
        claimCodeExpiry = 0;
        claimFailUntil = now + 5000UL;  // wait 5 seconds
        lcd.clean();
        lcd.print(0, 0, padLine("CODIGO EXPIRADO"));
        lcd.print(0, 1, padLine("Espera 5s..."));
        Serial.println("[CLAIM] Código expirado");
        return;
    }
    
    int seconds = (int)((claimCodeExpiry - now) / 1000);
    String line = "  " + currentClaimCode + " ";
    line += String(seconds);
    line += "s     ";
    lcd.print(0, 1, padLine(line));
}

void refreshLcd() {
    if (showingClaimCode) {
        updateClaimCountdown();
        return;
    }

    // Show failure countdown after claim expiry
    if (claimFailUntil > 0) {
        unsigned long now = millis();
        if (now < claimFailUntil) {
            int remaining = (int)((claimFailUntil - now) / 1000);
            lcd.clean();
            lcd.print(0, 0, padLine("CODIGO EXPIRADO"));
            String failLine = "Espera ";
            failLine += String(remaining);
            failLine += "s para nuevo";
            lcd.print(0, 1, padLine(failLine));
            return;
        }
        claimFailUntil = 0;
    }

    if (millis() < displayOverrideUntil) return;
    const DeviceConfig& cfg = configStore.get();

    if (!configReady) {
        showLines("Config invalida", "Revisa /config");
    } else if (comm.isPendingClaim()) {
        showLines("Pendiente vinc.", cfg.deviceId);
    } else if (!net.isConnected()) {
        showLines(net.statusLine0(), net.statusLine1());
    } else if (!backendAuthenticated) {
        if (comm.backendFailureVisible()) {
            showLines("Servicio no disp.", "Reintentando...");
        } else {
            showLines("Buscando servicio", cfg.deviceId);
        }
    } else {
        const bool levelFresh = lastLevelMs != 0 && (millis() - lastLevelMs) < LEVEL_STALE_MS;
        String line0 = levelFresh ? String(lastPercent, 0) + "%" : String("--%");
        line0 += " ";
        if (!levelFresh) {
            line0 += "--- L";
        } else if (lastLiters >= 1000.0f) {
            line0 += String(lastLiters, 0) + " L";
        } else {
            line0 += String(lastLiters, 1) + " L";
        }
        String line1 = relay.state() ? "ON  " : "OFF ";
        line1 += lastDistanceMm > 0.0f ? String(lastDistanceMm / 10.0f, 1) + " cm" : String("--- cm");
        showLines(line0, line1);
    }
}

bool onRelayCommand(bool state) {
    relay.set(state);
    Serial.printf("[RELE] Estado: %s (nivel pin=%s, activo en %s)\n",
                  relay.state() ? "ENCENDIDO" : "APAGADO",
                  digitalRead(PIN_RELE) ? "HIGH" : "LOW",
                  relay.activeLow() ? "LOW" : "HIGH");
    lastLcdRefresh = 0;  // refresca la pantalla ya, sin esperar 250 ms
    return relay.state();
}

void onLevel(float percent, float liters) {
    lastPercent = percent;
    lastLiters = liters;
    lastLevelMs = millis();
}

void onDisplayCommand(const String& line0, const String& line1, bool clear) {
    if (clear) lcd.clean();
    if (line0.length() > 0) lcd.print(0, 0, padLine(line0));
    if (line1.length() > 0) lcd.print(0, 1, padLine(line1));
    displayOverrideUntil = millis() + 10000;
}

void onConnectionStatus(bool isConnected) {
    backendAuthenticated = isConnected;
    if (!isConnected) lastLevelMs = 0;
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

void onOtaStart(const String& version, size_t size) {
    Serial.printf("[OTA] Inicio version=%s size=%u\n", version.c_str(), size);
    ota.start(nullptr, 0, size);
    showLines("OTA: " + version, "Espera...");
}

void onOtaChunk(uint8_t* data, size_t len) {
    ota.receiveChunk(data, len);
    static unsigned long lastProgress = 0;
    unsigned long now = millis();
    if (now - lastProgress >= 1000UL) {
        lastProgress = now;
        float prog = ota.progress();
        String line = String("OTA ") + String(prog, 0) + "%";
        lcd.print(0, 1, padLine(line));
    }
}

void onOtaComplete() {
    Serial.println("[OTA] Descarga completa, reiniciando...");
    showLines("OTA lista", "Reiniciando...");
    delay(500);
    ota.setConfirm();
}

// ==========================================================================
// Callbacks del menú de ajustes
// ==========================================================================

void onMenuExecute(int menuId, int itemId) {
    Serial.printf("[MENU] Ejecutar menu=%d item=%d\n", menuId, itemId);

    switch (menuId) {
        // -- Dispositivo --
        case MENU_DEVICE:
            switch (itemId) {
                case DEVICE_REBOOT:
                    relay.forceOff();
                    Serial.println("[MENU] Reinicio desde menu");
                    Serial.flush();
                    delay(100);
                    ESP.restart();
                    break;
                case DEVICE_SLEEP:
                    relay.forceOff();
                    Serial.println("[MENU] Deep sleep desde menu");
                    power.sleepForMinutes(60);
                    break;
            }
            break;

        // -- Bomba --
        case MENU_PUMP:
            switch (itemId) {
                case PUMP_TURN_ON:
                    relay.set(true);
                    Serial.println("[MENU] Bomba encendida manualmente");
                    break;
                case PUMP_TURN_OFF:
                    relay.set(false);
                    Serial.println("[MENU] Bomba apagada manualmente");
                    break;
                case PUMP_TEST_10S:
                    relay.set(true);
                    pumpTestOffAt = millis() + 10000;
                    Serial.println("[MENU] Prueba bomba 10s");
                    break;
            }
            break;

        // -- Seguridad --
        case MENU_SECURITY:
            switch (itemId) {
                case SEC_FACTORY_RESET:
                    relay.forceOff();
                    configStore.factoryReset();
                    Serial.println("[MENU] Factory reset desde menu");
                    Serial.flush();
                    delay(100);
                    ESP.restart();
                    break;
                case SEC_UNLINK:
                    Serial.println("[MENU] Desvincular desde menu");
                    // Lógica de desvinculación pendiente
                    break;
            }
            break;

        // -- WiFi --
        case MENU_WIFI:
            switch (itemId) {
                case WIFI_SCAN:
                    Serial.println("[MENU] Escaneando redes WiFi...");
                    net.requestScan();
                    break;
            }
            break;

        default:
            Serial.printf("[MENU] Accion no implementada menu=%d item=%d\n", menuId, itemId);
            break;
    }
}

String onMenuValue(int menuId, int itemId) {
    switch (menuId) {
        // -- Dispositivo --
        case MENU_DEVICE:
            switch (itemId) {
                case DEVICE_NAME:
                    return configStore.get().deviceName;
                case DEVICE_LOCATION:
                    return configStore.get().location;
                case DEVICE_ID:
                    return configStore.get().deviceId;
                case DEVICE_SERIAL:
                    return WiFi.macAddress();
                case DEVICE_UPTIME: {
                    unsigned long secs = millis() / 1000;
                    unsigned long mins = secs / 60;
                    unsigned long hours = mins / 60;
                    unsigned long days = hours / 24;
                    String s = String(days) + "d ";
                    s += String(hours % 24) + "h ";
                    s += String(mins % 60) + "m";
                    return s;
                }
                case DEVICE_HEAP:
                    return String(ESP.getFreeHeap()) + " bytes";
            }
            break;

        // -- Bomba --
        case MENU_PUMP:
            switch (itemId) {
                case PUMP_STATUS:
                    return relay.state() ? "ON" : "OFF";
                case PUMP_LEVEL:
                    return String(lastPercent, 0) + "%";
                case PUMP_LITERS:
                    return String(lastLiters, 1) + " L";
            }
            break;

        // -- Sensores --
        case MENU_SENSORS:
            switch (itemId) {
                case SENSOR_DISTANCE:
                    if (lastDistanceMm > 0) {
                        return String(lastDistanceMm / 10.0f, 1) + " cm";
                    }
                    return "Error";
                case SENSOR_STATUS:
                    return (lastDistanceMm > 0) ? "OK" : "Error lectura";
            }
            break;

        // -- Firmware --
        case MENU_FIRMWARE:
            switch (itemId) {
                case FIRMWARE_CURRENT:
                    return configStore.get().firmware;
            }
            break;

        // -- Red --
        case MENU_NETWORK:
            switch (itemId) {
                case NET_WIFI_STATUS:
                    return net.isConnected() ? "Conectado" : "Desconectado";
                case NET_SSID:
                    return WiFi.SSID();
                case NET_SIGNAL:
                    return String(WiFi.RSSI()) + " dBm";
                case NET_IP:
                    return WiFi.localIP().toString();
                case NET_BACKEND:
                    return comm.isAuthenticated() ? "Conectado" : "No conectado";
                case NET_HOST:
                    return configStore.get().backendHost;
                case NET_PORT:
                    return String(configStore.get().backendPort);
                case NET_TLS:
                    return configStore.get().backendTls ? "Si" : "No";
            }
            break;

        // -- Seguridad --
        case MENU_SECURITY:
            switch (itemId) {
                case SEC_CLAIM_STATUS:
                    if (comm.isAuthenticated()) return "Vinculado";
                    if (comm.isPendingClaim()) return "Pendiente";
                    return "No vinculado";
                case SEC_LOCKED_LIST: {
                    String s = "";
                    bool first = true;
                    for (uint8_t i = 1; i <= 6; i++) {
                        // Check each button's lock state
                        Button* btn = nullptr;
                        if (i == 1) btn = &btnUp;
                        else if (i == 2) btn = &btnDown;
                        else if (i == 3) btn = &btnLeft;
                        else if (i == 4) btn = &btnRight;
                        else if (i == 5) btn = &btnOk;
                        else if (i == 6) btn = &btnBack;
                        if (btn && btn->isLocked()) {
                            if (!first) s += ", ";
                            s += String(i);
                            first = false;
                        }
                    }
                    return first ? "Ninguno" : s;
                }
            }
            break;

        // -- WiFi --
        case MENU_WIFI:
            switch (itemId) {
                case WIFI_CURRENT:
                    String s = WiFi.SSID();
                    s += " ";
                    s += String(WiFi.RSSI());
                    s += " dBm";
                    return s;
            }
            break;
    }
    return "--";
}

bool onMenuToggleGet(int menuId, int itemId) {
    switch (menuId) {
        case MENU_PUMP:
            if (itemId == PUMP_OVERFLOW_PROTECT) {
                return configStore.get().overflowProtection;
            }
            break;
        case MENU_WIFI:
            if (itemId == WIFI_AIRPLANE) {
                // WiFi desactivado = no conectado y sin reintentos
                return !net.isConnected();
            }
            break;
        case MENU_FIRMWARE:
            if (itemId == FIRMWARE_AUTO_UPDATE) {
                return configStore.get().autoUpdate;
            }
            break;
        case MENU_SECURITY:
            if (itemId == SEC_LOCK_BUTTONS) {
                // Returns true if any button is locked
                return btnUp.isLocked() || btnDown.isLocked() || btnLeft.isLocked() ||
                       btnRight.isLocked() || btnOk.isLocked() || btnBack.isLocked();
            }
            break;
    }
    return false;
}

void onMenuToggleSet(int menuId, int itemId, bool value) {
    Serial.printf("[MENU] Toggle menu=%d item=%d value=%d\n", menuId, itemId, value);
    switch (menuId) {
        case MENU_PUMP:
            if (itemId == PUMP_OVERFLOW_PROTECT) {
                configStore.setOverflowProtection(value);
            }
            break;
        case MENU_FIRMWARE:
            if (itemId == FIRMWARE_AUTO_UPDATE) {
                configStore.setAutoUpdate(value);
            }
            break;
        case MENU_SECURITY:
            if (itemId == SEC_LOCK_BUTTONS) {
                btnUp.setLocked(value);
                btnDown.setLocked(value);
                btnLeft.setLocked(value);
                btnRight.setLocked(value);
                btnOk.setLocked(value);
                btnBack.setLocked(value);
            }
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.printf("[BOOT] reset_reason=%d\n", static_cast<int>(esp_reset_reason()));
    // Apagado inmediato con la polaridad por defecto; si config.json define
    // "relay.active_low" se reaplica más abajo (siempre dejando el relé OFF).
    relay.begin(PIN_RELE, RELE_ACTIVE_LOW_DEFAULT != 0);
    lcd.init();
    lcd.light(true);
    lcd.clean();
    showLines("DispWatter", "Iniciando...");

    configReady = configStore.begin();
    power.begin(configStore.get().wakePin, configStore.get().wakeActiveLow);
    if (!configReady) {
        Serial.printf("[CONFIG] %s\n", configStore.lastError().c_str());
        showLines("Config invalida", "Revisa /config");
        return;
    }

    if (configStore.get().relayActiveLow >= 0) {
        relay.setPolarity(configStore.get().relayActiveLow == 1);
    }
    Serial.printf("[RELE] Polaridad: activo en %s\n", relay.activeLow() ? "LOW" : "HIGH");

    crypto.setKeyHash(configStore.get().keyHash);
    comm.setWakeReason(power.wakeReasonString());
    Serial.printf("[CONFIG] Dispositivo %s (%s)\n",
                  configStore.get().deviceId.c_str(), configStore.get().deviceName.c_str());
    Serial.printf("[POWER] Motivo de arranque: %s\n", power.wakeReasonString().c_str());

    sensor.init();
    net.begin();
    comm.onRelayCommand(onRelayCommand);
    comm.onDisplayCommand(onDisplayCommand);
    comm.onLevel(onLevel);
    comm.onConnectionStatus(onConnectionStatus);
    comm.onReboot(onReboot);
    comm.onSleep(onSleep);
    comm.onFactoryReset(onFactoryReset);
    comm.onOtaStart(onOtaStart);
    comm.onOtaChunk(onOtaChunk);
    comm.onOtaComplete(onOtaComplete);
    comm.onClaimCode(onClaimCode);
    comm.onClaimVerified(onClaimVerified);
    comm.onMenuClose([]() {
        settingsMenu.deactivate();
        Serial.println("[MENU] Cerrado remotamente desde el panel");
    });
    comm.onConfigUpdate([](const String& jsonConfig) {
        // Parse config update from backend and apply to ConfigStore
        DynamicJsonDocument doc(512);
        DeserializationError err = deserializeJson(doc, jsonConfig);
        if (err) {
            Serial.printf("[CONFIG] Error parseando config: %s\n", err.c_str());
            return;
        }
        if (doc.containsKey("menu_lock")) {
            configStore.setMenuLock(doc["menu_lock"] | false);
            Serial.printf("[CONFIG] menu_lock=%d\n", configStore.get().menuLock);
        }
        if (doc.containsKey("overflow_protection")) {
            configStore.setOverflowProtection(doc["overflow_protection"] | true);
        }
        if (doc.containsKey("auto_update")) {
            configStore.setAutoUpdate(doc["auto_update"] | false);
        }
        if (doc.containsKey("min_relay_off_min")) {
            configStore.setMinRelayOffMin(doc["min_relay_off_min"] | 3);
        }
        // Tank parameters (capacity, bottom_dist_mm, mirror_dist_mm, min_level,
        // max_level, auto_refill) are stored in the backend TankConfig table and
        // used for telemetry calculations. The ESP32 does not persist them in
        // /config.json; they are applied at runtime via the backend sync.
        Serial.println("[CONFIG] Configuración actualizada desde el panel");
    });
    comm.begin();
    ota.begin();

    // Inicializar botones de navegación
    btnUp.begin();
    btnDown.begin();
    btnLeft.begin();
    btnRight.begin();
    btnOk.begin();
    btnBack.begin();

    // Botón Power (GPIO 32) — no usa librería Button, solo lectura directa
    pinMode(BTN_POWER_PIN, INPUT_PULLUP);

    // Inicializar menú de ajustes
    settingsMenu.begin();
    settingsMenu.setRootMenu(menu_root);
    settingsMenu.onExecute(onMenuExecute);
    settingsMenu.onValue(onMenuValue);
    settingsMenu.onToggle(onMenuToggleGet, onMenuToggleSet);

    showLines("Buscando WiFi", configStore.get().deviceId);
}

void loop() {
    if (!configReady) {
        delay(2000);
        return;
    }

    net.update();
    comm.update();

    // Actualizar botones
    btnUp.update();
    btnDown.update();
    btnLeft.update();
    btnRight.update();
    btnOk.update();
    btnBack.update();

    const unsigned long now = millis();
    const DeviceConfig& cfg = configStore.get();

    // ==========================================================================
    // Menú de ajustes
    // ==========================================================================

    // Detectar activación: Power (GPIO 32) + Back presionados simultáneamente
    // Solo si el menú no está bloqueado por el panel
    bool powerPressed = (digitalRead(BTN_POWER_PIN) == LOW);
    if (!configStore.get().menuLock) {
        settingsMenu.checkActivation(powerPressed, btnBack.isPressed());
    }

    if (settingsMenu.isAnimating() || settingsMenu.isActive()) {
        settingsMenu.update();
        settingsMenu.render(lcd);

        if (settingsMenu.isActive()) {
            if (btnLeft.wasPressed()) settingsMenu.navigateLeft();
            if (btnRight.wasPressed()) settingsMenu.navigateRight();
            if (btnOk.wasPressed()) settingsMenu.select();
            if (btnBack.wasPressed()) settingsMenu.back();
        }

        // Durante el menú, mantener net/comm actualizados pero no hacer nada más
        delay(5);
        return;
    }

    // Timer de prueba de bomba: apagar después de 10s
    if (pumpTestOffAt > 0 && millis() >= pumpTestOffAt) {
        relay.set(false);
        pumpTestOffAt = 0;
        Serial.println("[MENU] Prueba bomba finalizada (10s)");
    }

    // Fail-safe inmediato: el relé no debe quedar activo sin Wi-Fi/backend.
    if ((!net.isConnected() || !backendAuthenticated) && relay.state()) {
        relay.forceOff();
        Serial.println("[SAFE] Sin WiFi o backend: relé apagado");
    }
    relay.guard(now, comm.lastAuthenticatedMs(),
                static_cast<unsigned long>(cfg.maxRelayOnMin) * 60000UL,
                static_cast<unsigned long>(cfg.maxOfflineMin) * 60000UL,
                static_cast<unsigned long>(cfg.minRelayOffMin) * 60000UL,
                cfg.overflowProtection,
                lastPercent,
                90.0f);

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
