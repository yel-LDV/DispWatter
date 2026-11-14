#ifndef CONFIG_STORE_H
#define CONFIG_STORE_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>

struct WifiEntry {
    String ssid;
    String password;
};

struct DeviceConfig {
    uint8_t schema = 1;
    String deviceId;
    String deviceName;
    String location;
    String firmware;
    String keyHash;

    String backendHost;
    uint16_t backendPort = 8765;
    String backendPath = "/ws/device";
    bool backendTls = false;

    std::vector<WifiEntry> wifi;

    uint32_t sampleIntervalMs = 2000;
    uint32_t retryMs = 5000;

    uint8_t wakePin = 33;
    bool wakeActiveLow = true;
    uint16_t sleepTimerMin = 60;

    uint16_t maxRelayOnMin = 10;
    uint16_t maxOfflineMin = 5;
    
    // Protección de bomba: tiempo mínimo de apagado entre arranques (minutos)
    uint16_t minRelayOffMin = 3;
    // Protección contra desborde
    bool overflowProtection = true;
    
    // Polaridad del módulo de relé ("relay.active_low" en config.json).
    //   -1 = no definida en el JSON -> se usa RELE_ACTIVE_LOW_DEFAULT (config.h)
    //    1 = activo en LOW, 0 = activo en HIGH
    int8_t relayActiveLow = -1;

    // Actualización automática de firmware
    bool autoUpdate = false;
};

/**
 * Carga y persiste /config.json en LittleFS.
 * El dispositivo es la fuente de verdad de las redes WiFi.
 */
class ConfigStore {
public:
    bool begin();
    bool load();
    bool save();
    bool factoryReset();

    bool isValid() const { return _valid; }
    const DeviceConfig& get() const { return _cfg; }
    const String& lastError() const { return _lastError; }

    bool addWifi(const String& ssid, const String& password);
    bool removeWifi(const String& ssid);
    bool moveWifi(const String& ssid, size_t newIndex);
    bool hasWifi(const String& ssid) const;
    bool hasPassword(const String& ssid) const;

    String networksJson() const;

    // Modificadores de configuración con guardado automático
    void setOverflowProtection(bool value);
    void setAutoUpdate(bool value);

private:
    DeviceConfig _cfg;
    bool _valid = false;
    String _lastError;

    bool _applyJson(JsonVariantConst root, DeviceConfig& out);
    bool _validate(const DeviceConfig& cfg);
    void _applyDefaults();
};

#endif // CONFIG_STORE_H
