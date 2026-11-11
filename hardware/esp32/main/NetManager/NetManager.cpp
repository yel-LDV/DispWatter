#include "NetManager.h"

#include <ArduinoJson.h>

namespace {
constexpr unsigned long CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long SCAN_DELAY_MS = 500;
} // namespace

NetManager::NetManager(ConfigStore& store) : _store(store) {}

void NetManager::begin() {
    // La fuente de verdad es /config.json: no permitir que el NVS del ESP32
    // se reconecte por su cuenta y salte el orden manual de prioridad.
    WiFi.persistent(false);
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(true, true);
    WiFi.mode(WIFI_STA);
    _state = State::Idle;
    _stateSince = millis();
    _lastScan = 0;
    _candidate = 0;
    _wasConnected = false;

    Serial.printf("[WIFI] Inicializado en modo estación; hay %u red(es) guardada(s)\n",
                  static_cast<unsigned>(_store.get().wifi.size()));
    for (size_t i = 0; i < _store.get().wifi.size(); ++i) {
        Serial.printf("[WIFI] Red configurada %u: '%s'\n",
                      static_cast<unsigned>(i + 1),
                      _store.get().wifi[i].ssid.c_str());
    }
}

bool NetManager::isConnected() const {
    return WiFi.status() == WL_CONNECTED;
}

String NetManager::connectedSSID() const {
    return isConnected() ? WiFi.SSID() : String("");
}

int32_t NetManager::rssi() const {
    return isConnected() ? WiFi.RSSI() : 0;
}

IPAddress NetManager::ip() const {
    return isConnected() ? WiFi.localIP() : IPAddress(0, 0, 0, 0);
}

void NetManager::update() {
    const unsigned long now = millis();

    if (WiFi.status() == WL_CONNECTED) {
        if (_state != State::Connected) {
            _state = State::Connected;
            _wasConnected = true;
            Serial.printf("[WIFI] Conectado a '%s' (%d dBm) IP %s\n",
                          WiFi.SSID().c_str(), WiFi.RSSI(),
                          WiFi.localIP().toString().c_str());
        }
        return;
    }

    if (_wasConnected && _state == State::Connected) {
        _wasConnected = false;
        _state = State::Idle;
        _lastScan = 0;
        Serial.println("[WIFI] Conexión perdida; reiniciando búsqueda");
    }

    switch (_state) {
        case State::Idle:
            if (now - _lastScan >= SCAN_DELAY_MS) {
                _startScan();
            }
            break;

        case State::Backoff:
            if (now - _lastScan >= _store.get().retryMs) {
                _startScan();
            }
            break;

        case State::Scanning:
            _pollScan();
            break;

        case State::Connecting: {
            const wl_status_t status = WiFi.status();
            if (status == WL_CONNECT_FAILED || status == WL_NO_SSID_AVAIL) {
                Serial.printf("[WIFI] Falló '%s' (status=%d); intentando otra red\n",
                              _candidates[_candidate - 1].c_str(), static_cast<int>(status));
                WiFi.disconnect();
                _tryNext();
            } else if (now - _stateSince >= CONNECT_TIMEOUT_MS) {
                Serial.printf("[WIFI] Timeout conectando a '%s' (status=%d); intentando otra red\n",
                              _candidates[_candidate - 1].c_str(), static_cast<int>(status));
                WiFi.disconnect();
                _tryNext();
            }
            break;
        }

        case State::Connected:
        default:
            break;
    }
}

void NetManager::_startScan() {
    _state = State::Scanning;
    _stateSince = millis();
    WiFi.scanDelete();
    Serial.println("[WIFI] Escaneando redes WiFi...");
    const int16_t result = WiFi.scanNetworks(true);
    if (result == WIFI_SCAN_FAILED) {
        _lastError = "Escaneo WiFi fallido";
        Serial.printf("[WIFI] %s (status=%d); reintento en %lu ms\n",
                      _lastError.c_str(), static_cast<int>(result),
                      _store.get().retryMs);
        _state = State::Backoff;
        _lastScan = millis();
    }
}

void NetManager::_pollScan() {
    const int16_t count = WiFi.scanComplete();
    if (count == WIFI_SCAN_RUNNING) {
        return;
    }
    if (count < 0) {
        _lastError = "Escaneo WiFi fallido";
        Serial.printf("[WIFI] %s (status=%d); reintento en %lu ms\n",
                      _lastError.c_str(), static_cast<int>(count),
                      _store.get().retryMs);
        _state = State::Backoff;
        _lastScan = millis();
        return;
    }

    _scan.clear();
    Serial.printf("[WIFI] Escaneo terminado: %d red(es) detectada(s)\n", count);
    for (int i = 0; i < count; ++i) {
        const String ssid = WiFi.SSID(i);
        if (ssid.length() == 0) {
            continue;
        }
        WifiStatus status;
        status.ssid = ssid;
        status.rssi = WiFi.RSSI(i);
        status.stored = _store.hasWifi(ssid);
        status.hasPassword = _store.hasPassword(ssid);
        status.visible = true;
        status.connected = false;
        _scan.push_back(status);
        Serial.printf("[WIFI] Detectada '%s' (%d dBm)%s\n", ssid.c_str(),
                      status.rssi, status.stored ? " [guardada]" : "");
    }

    WiFi.scanDelete();
    _buildCandidates();
    _candidate = 0;
    Serial.printf("[WIFI] Intentaré %u red(es) guardada(s) en prioridad\n",
                  static_cast<unsigned>(_candidates.size()));
    _tryNext();
}

void NetManager::_buildCandidates() {
    _candidates.clear();

    // Primero, redes guardadas y visibles respetando su prioridad.
    for (const auto& entry : _store.get().wifi) {
        for (const auto& status : _scan) {
            if (status.ssid == entry.ssid) {
                _candidates.push_back(entry.ssid);
                break;
            }
        }
    }

    // No excluir el resto de redes guardadas: pueden estar ocultas, tener
    // escaneo incompleto o estar disponibles aunque otra red visible falle.
    for (const auto& entry : _store.get().wifi) {
        bool alreadyAdded = false;
        for (const auto& ssid : _candidates) {
            if (ssid == entry.ssid) {
                alreadyAdded = true;
                break;
            }
        }
        if (!alreadyAdded) {
            _candidates.push_back(entry.ssid);
        }
    }
}

void NetManager::_tryNext() {
    while (_candidate < _candidates.size()) {
        const String ssid = _candidates[_candidate++];
        const WifiEntry* entry = nullptr;
        for (const auto& candidate : _store.get().wifi) {
            if (candidate.ssid == ssid) {
                entry = &candidate;
                break;
            }
        }
        if (entry == nullptr) {
            continue;
        }

        Serial.printf("[WIFI] Intentando conectar a '%s' (%u/%u)...\n",
                      ssid.c_str(), static_cast<unsigned>(_candidate),
                      static_cast<unsigned>(_candidates.size()));
        WiFi.begin(ssid.c_str(),
                   entry->password.length() > 0 ? entry->password.c_str() : nullptr);
        _state = State::Connecting;
        _stateSince = millis();
        return;
    }

    _state = State::Backoff;
    _lastScan = millis();
    Serial.printf("[WIFI] No se pudo conectar a ninguna red; nueva búsqueda en %lu ms\n",
                  _store.get().retryMs);
}

bool NetManager::addAndSave(const String& ssid, const String& password) {
    if (!_store.addWifi(ssid, password)) {
        _lastError = _store.lastError();
        return false;
    }

    if (!isConnected()) {
        Serial.printf("[WIFI] Nueva red '%s', intentando conectar...\n", ssid.c_str());
        WiFi.begin(ssid.c_str(),
                   password.length() > 0 ? password.c_str() : nullptr);
        _state = State::Connecting;
        _stateSince = millis();
    }
    return true;
}

bool NetManager::removeAndSave(const String& ssid) {
    const bool wasConnected = isConnected() && WiFi.SSID() == ssid;
    if (!_store.removeWifi(ssid)) {
        _lastError = _store.lastError();
        return false;
    }

    if (wasConnected) {
        WiFi.disconnect();
        _state = State::Idle;
        _lastScan = 0;
        _wasConnected = false;
    }
    return true;
}

bool NetManager::reorderAndSave(const String& ssid, size_t newIndex) {
    if (!_store.moveWifi(ssid, newIndex)) {
        _lastError = _store.lastError();
        return false;
    }
    if (!isConnected()) {
        _lastScan = 0;
        _state = State::Idle;
    }
    return true;
}

void NetManager::requestScan() {
    _lastScan = 0;
    _state = State::Idle;
}

String NetManager::networksJson() const {
    DynamicJsonDocument doc(4096);
    JsonArray array = doc.to<JsonArray>();

    const String connectedSsid = connectedSSID();

    for (size_t i = 0; i < _store.get().wifi.size(); ++i) {
        const WifiEntry& entry = _store.get().wifi[i];
        int32_t rssi = 0;
        bool visible = false;
        for (const auto& status : _scan) {
            if (status.ssid == entry.ssid) {
                rssi = status.rssi;
                visible = true;
                break;
            }
        }

        JsonObject item = array.createNestedObject();
        item["ssid"] = entry.ssid;
        item["rssi"] = rssi;
        item["visible"] = visible;
        item["stored"] = true;
        item["connected"] = (entry.ssid == connectedSsid);
        item["has_password"] = entry.password.length() > 0;
        item["priority"] = static_cast<int>(i);
    }

    for (const auto& status : _scan) {
        if (status.stored) {
            continue;
        }
        JsonObject item = array.createNestedObject();
        item["ssid"] = status.ssid;
        item["rssi"] = status.rssi;
        item["visible"] = true;
        item["stored"] = false;
        item["connected"] = false;
        item["has_password"] = status.hasPassword;
        item["priority"] = -1;
    }

    String output;
    serializeJson(array, output);
    return output;
}
