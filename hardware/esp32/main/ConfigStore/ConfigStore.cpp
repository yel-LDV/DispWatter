#include "ConfigStore.h"

#include <LittleFS.h>
#include <ArduinoJson.h>

namespace {
constexpr const char* CONFIG_PATH = "/config.json";
constexpr const char* CONFIG_TMP = "/config.json.tmp";
constexpr size_t MAX_WIFI = 8;

bool isHex64(const String& value) {
    if (value.length() != 64) {
        return false;
    }
    for (size_t i = 0; i < value.length(); ++i) {
        const char c = value[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
              (c >= 'A' && c <= 'F'))) {
            return false;
        }
    }
    return true;
}
} // namespace

bool ConfigStore::begin() {
    if (!LittleFS.begin(true)) {
        _lastError = "LittleFS no disponible";
        _valid = false;
        return false;
    }
    _applyDefaults();
    load();
    return _valid;
}

void ConfigStore::_applyDefaults() {
    _cfg = DeviceConfig();
}

bool ConfigStore::load() {
    File file = LittleFS.open(CONFIG_PATH, "r");
    if (!file) {
        _lastError = "Sin /config.json";
        _valid = false;
        return false;
    }

    DynamicJsonDocument doc(8192);
    const DeserializationError error = deserializeJson(doc, file);
    file.close();

    if (error) {
        _lastError = String("JSON invalido: ") + error.c_str();
        _valid = false;
        return false;
    }

    DeviceConfig cfg;
    if (!_applyJson(doc.as<JsonVariantConst>(), cfg)) {
        _lastError = "Estructura de configuracion invalida";
        _valid = false;
        return false;
    }

    if (!_validate(cfg)) {
        _lastError = "Configuracion invalida";
        _valid = false;
        return false;
    }

    _cfg = cfg;
    _valid = true;
    _lastError = "";
    return true;
}

bool ConfigStore::save() {
    DynamicJsonDocument doc(8192);
    doc["schema"] = _cfg.schema;

    JsonObject dev = doc.createNestedObject("device");
    dev["id"] = _cfg.deviceId;
    dev["name"] = _cfg.deviceName;
    dev["location"] = _cfg.location;
    dev["firmware"] = _cfg.firmware;
    dev["key_hash"] = _cfg.keyHash;

    JsonObject backend = doc.createNestedObject("backend");
    backend["host"] = _cfg.backendHost;
    backend["port"] = _cfg.backendPort;
    backend["path"] = _cfg.backendPath;
    backend["tls"] = _cfg.backendTls;

    JsonArray wifi = doc.createNestedArray("wifi");
    for (const auto& entry : _cfg.wifi) {
        JsonObject item = wifi.createNestedObject();
        item["ssid"] = entry.ssid;
        item["password"] = entry.password;
    }

    JsonObject sampling = doc.createNestedObject("sampling");
    sampling["interval_ms"] = _cfg.sampleIntervalMs;
    sampling["retry_ms"] = _cfg.retryMs;

    JsonObject power = doc.createNestedObject("power");
    power["wake_pin"] = _cfg.wakePin;
    power["wake_active_low"] = _cfg.wakeActiveLow;
    power["sleep_timer_min"] = _cfg.sleepTimerMin;

    JsonObject safety = doc.createNestedObject("safety");
    safety["max_relay_on_min"] = _cfg.maxRelayOnMin;
    safety["max_offline_min"] = _cfg.maxOfflineMin;
    safety["min_relay_off_min"] = _cfg.minRelayOffMin;
    safety["overflow_protection"] = _cfg.overflowProtection;

    if (_cfg.relayActiveLow >= 0) {
        JsonObject relayCfg = doc.createNestedObject("relay");
        relayCfg["active_low"] = (_cfg.relayActiveLow == 1);
    }

    File file = LittleFS.open(CONFIG_TMP, "w");
    if (!file) {
        _lastError = "No se pudo abrir config temporal";
        return false;
    }
    const size_t written = serializeJson(doc, file);
    file.close();
    if (written == 0) {
        LittleFS.remove(CONFIG_TMP);
        _lastError = "No se pudo escribir config";
        return false;
    }

    LittleFS.remove(CONFIG_PATH);
    if (!LittleFS.rename(CONFIG_TMP, CONFIG_PATH)) {
        _lastError = "No se pudo reemplazar config";
        return false;
    }
    _lastError = "";
    return true;
}

bool ConfigStore::factoryReset() {
    LittleFS.remove(CONFIG_PATH);
    LittleFS.remove(CONFIG_TMP);
    _applyDefaults();
    _valid = false;
    _lastError = "Reset de fabrica";
    return true;
}

bool ConfigStore::_applyJson(JsonVariantConst root, DeviceConfig& out) {
    if (!root.is<JsonObjectConst>()) {
        return false;
    }

    out.schema = root["schema"] | 1;

    JsonObjectConst dev = root["device"];
    if (dev.isNull()) {
        return false;
    }
    out.deviceId = dev["id"] | "";
    out.deviceName = dev["name"] | "";
    out.location = dev["location"] | "";
    out.firmware = dev["firmware"] | "1.0.0";
    out.keyHash = dev["key_hash"] | "";

    JsonObjectConst backend = root["backend"];
    out.backendHost = backend["host"] | "";
    out.backendPort = backend["port"] | 8765;
    out.backendPath = backend["path"] | "/ws/device";
    out.backendTls = backend["tls"] | false;

    out.wifi.clear();
    JsonArrayConst wifi = root["wifi"].as<JsonArrayConst>();
    for (JsonVariantConst item : wifi) {
        WifiEntry entry;
        entry.ssid = item["ssid"] | "";
        entry.password = item["password"] | "";
        if (entry.ssid.length() > 0) {
            out.wifi.push_back(entry);
        }
    }

    JsonObjectConst sampling = root["sampling"];
    out.sampleIntervalMs = sampling["interval_ms"] | 2000;
    out.retryMs = sampling["retry_ms"] | 5000;

    JsonObjectConst power = root["power"];
    out.wakePin = power["wake_pin"] | 33;
    out.wakeActiveLow = power["wake_active_low"] | true;
    out.sleepTimerMin = power["sleep_timer_min"] | 60;

    JsonObjectConst safety = root["safety"];
    out.maxRelayOnMin = safety["max_relay_on_min"] | 10;
    out.maxOfflineMin = safety["max_offline_min"] | 5;
    out.minRelayOffMin = safety["min_relay_off_min"] | 3;
    out.overflowProtection = safety["overflow_protection"] | true;

    JsonObjectConst relayCfg = root["relay"];
    if (!relayCfg.isNull() && relayCfg.containsKey("active_low")) {
        out.relayActiveLow = (relayCfg["active_low"] | true) ? 1 : 0;
    } else {
        out.relayActiveLow = -1;
    }

    return true;
}

bool ConfigStore::_validate(const DeviceConfig& cfg) {
    if (cfg.schema != 1) {
        return false;
    }
    if (cfg.deviceId.length() == 0 || cfg.deviceId.length() > 64) {
        return false;
    }
    if (!isHex64(cfg.keyHash)) {
        return false;
    }
    if (cfg.backendHost.length() == 0 || cfg.backendPort == 0) {
        return false;
    }
    if (!cfg.backendPath.startsWith("/")) {
        return false;
    }
    if (cfg.wifi.size() < 1 || cfg.wifi.size() > MAX_WIFI) {
        return false;
    }
    for (size_t i = 0; i < cfg.wifi.size(); ++i) {
        const WifiEntry& entry = cfg.wifi[i];
        if (entry.ssid.length() == 0 || entry.ssid.length() > 31) {
            return false;
        }
        if (entry.password.length() > 0 &&
            (entry.password.length() < 8 || entry.password.length() > 63)) {
            return false;
        }
        for (size_t j = i + 1; j < cfg.wifi.size(); ++j) {
            if (cfg.wifi[j].ssid == entry.ssid) {
                return false;
            }
        }
    }
    if (cfg.sampleIntervalMs < 500 || cfg.retryMs < 1000) {
        return false;
    }
    if (cfg.wakePin > 39 || cfg.sleepTimerMin < 1) {
        return false;
    }
    if (cfg.maxRelayOnMin < 1 || cfg.maxOfflineMin < 1) {
        return false;
    }
    return true;
}

bool ConfigStore::addWifi(const String& ssid, const String& password) {
    if (ssid.length() == 0 || ssid.length() > 31) {
        _lastError = "SSID invalido";
        return false;
    }
    if (password.length() > 0 &&
        (password.length() < 8 || password.length() > 63)) {
        _lastError = "Password invalida";
        return false;
    }
    if (_cfg.wifi.size() >= MAX_WIFI) {
        _lastError = "Limite de redes alcanzado";
        return false;
    }
    for (const auto& entry : _cfg.wifi) {
        if (entry.ssid == ssid) {
            _lastError = "La red ya existe";
            return false;
        }
    }
    _cfg.wifi.push_back({ssid, password});
    if (!save()) {
        _cfg.wifi.pop_back();
        return false;
    }
    return true;
}

bool ConfigStore::removeWifi(const String& ssid) {
    if (_cfg.wifi.size() <= 1) {
        _lastError = "Debe quedar al menos una red";
        return false;
    }
    for (auto it = _cfg.wifi.begin(); it != _cfg.wifi.end(); ++it) {
        if (it->ssid == ssid) {
            WifiEntry removed = *it;
            _cfg.wifi.erase(it);
            if (!save()) {
                _cfg.wifi.push_back(removed);
                return false;
            }
            return true;
        }
    }
    _lastError = "Red no encontrada";
    return false;
}

bool ConfigStore::moveWifi(const String& ssid, size_t newIndex) {
    size_t current = _cfg.wifi.size();
    for (size_t i = 0; i < _cfg.wifi.size(); ++i) {
        if (_cfg.wifi[i].ssid == ssid) {
            current = i;
            break;
        }
    }
    if (current >= _cfg.wifi.size()) {
        _lastError = "Red no encontrada";
        return false;
    }
    if (newIndex >= _cfg.wifi.size()) {
        newIndex = _cfg.wifi.size() - 1;
    }
    WifiEntry entry = _cfg.wifi[current];
    _cfg.wifi.erase(_cfg.wifi.begin() + current);
    _cfg.wifi.insert(_cfg.wifi.begin() + newIndex, entry);
    if (!save()) {
        _lastError = "No se pudo guardar el orden";
        return false;
    }
    return true;
}

bool ConfigStore::hasWifi(const String& ssid) const {
    for (const auto& entry : _cfg.wifi) {
        if (entry.ssid == ssid) {
            return true;
        }
    }
    return false;
}

bool ConfigStore::hasPassword(const String& ssid) const {
    for (const auto& entry : _cfg.wifi) {
        if (entry.ssid == ssid) {
            return entry.password.length() > 0;
        }
    }
    return false;
}

String ConfigStore::networksJson() const {
    DynamicJsonDocument doc(2048);
    JsonArray array = doc.to<JsonArray>();
    for (size_t i = 0; i < _cfg.wifi.size(); ++i) {
        JsonObject item = array.createNestedObject();
        item["ssid"] = _cfg.wifi[i].ssid;
        item["has_password"] = _cfg.wifi[i].password.length() > 0;
        item["priority"] = i;
    }
    String output;
    serializeJson(array, output);
    return output;
}
