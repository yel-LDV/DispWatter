#include "NetManager.h"

#include <ArduinoJson.h>

namespace {
constexpr unsigned long CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long SCAN_DELAY_MS = 500;
constexpr unsigned long STATUS_MESSAGE_MS = 3000;
constexpr unsigned long RETRY_INTERVAL_MS = 250;

String wifiFailureReason(wl_status_t status) {
    if (status == WL_NO_SSID_AVAIL) return "SSID no encontrada";
    if (status == WL_CONNECT_FAILED) return "Clave/AP rechazado";
    if (status == WL_DISCONNECTED) return "Sin respuesta del AP";
    return String("Estado WiFi ") + String(static_cast<int>(status));
}
} // namespace

NetManager::NetManager(ConfigStore& store) : _store(store) {}

void NetManager::begin() {
    WiFi.persistent(false);
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(true, true);
    WiFi.mode(WIFI_STA);
    _state = State::Idle;
    _stateSince = millis();
    _lastScan = 0;
    _lastRetryTick = 0;
    _candidate = 0;
    _wasConnected = false;
    _messageUntil = 0;

    Serial.printf("[WIFI] Modo estación; %u red(es) guardada(s)\n",
                  static_cast<unsigned>(_store.get().wifi.size()));
    for (size_t i = 0; i < _store.get().wifi.size(); ++i) {
        Serial.printf("[WIFI] Configurada %u: '%s'\n",
                      static_cast<unsigned>(i + 1), _store.get().wifi[i].ssid.c_str());
    }
}

bool NetManager::isConnected() const { return WiFi.status() == WL_CONNECTED; }
String NetManager::connectedSSID() const { return isConnected() ? WiFi.SSID() : String(""); }
int32_t NetManager::rssi() const { return isConnected() ? WiFi.RSSI() : 0; }
IPAddress NetManager::ip() const { return isConnected() ? WiFi.localIP() : IPAddress(0, 0, 0, 0); }

String NetManager::statusLine0() const {
    if (millis() < _messageUntil && _messageLine0.length()) return _messageLine0;
    switch (_state) {
        case State::Idle: return "WiFi iniciando";
        case State::Scanning: return "Escaneando WiFi";
        case State::Connecting: return String("Probando: ") + _currentSsid;
        case State::Connected: return String("WiFi OK: ") + connectedSSID();
        case State::Backoff: return "Sin conexion WiFi";
        default: return "Buscando WiFi";
    }
}

String NetManager::statusLine1() const {
    if (millis() < _messageUntil && _messageLine1.length()) return _messageLine1;
    switch (_state) {
        case State::Idle: return "Preparando";
        case State::Scanning: return "Buscando redes";
        case State::Connecting:
            return String("Red ") + String(static_cast<unsigned>(_candidate)) + "/" +
                   String(static_cast<unsigned>(_candidates.size()));
        case State::Connected: return connectedSSID();
        case State::Backoff: {
            const unsigned long retryMs = _store.get().retryMs;
            const unsigned long elapsed = millis() - _lastScan;
            const unsigned long remaining = elapsed >= retryMs ? 0 : retryMs - elapsed;
            const unsigned seconds = static_cast<unsigned>((remaining + 999UL) / 1000UL);
            return String("Reintento en ") + String(seconds) + "s";
        }
        default: return "";
    }
}

void NetManager::_showTransientMessage(const String& line0, const String& line1) {
    _messageLine0 = line0;
    _messageLine1 = line1;
    _messageUntil = millis() + STATUS_MESSAGE_MS;
}

String NetManager::_nextSsid() const {
    return _candidate < _candidates.size() ? _candidates[_candidate] : "Reintento en 5s";
}

void NetManager::update() {
    const unsigned long now = millis();
    if (WiFi.status() == WL_CONNECTED) {
        if (_state != State::Connected) {
            _state = State::Connected;
            _wasConnected = true;
            _messageUntil = 0;
            _currentSsid = WiFi.SSID();
            Serial.printf("[WIFI] Conectado a '%s' (%d dBm) IP %s\n", WiFi.SSID().c_str(),
                          WiFi.RSSI(), WiFi.localIP().toString().c_str());
        }
        return;
    }

    if (_wasConnected && _state == State::Connected) {
        _wasConnected = false;
        _state = State::Idle;
        _lastScan = 0;
        Serial.println("[WIFI] Conexion perdida; iniciando busqueda de nuevo");
    }

    switch (_state) {
        case State::Idle:
            if (now - _lastScan >= SCAN_DELAY_MS) _startScan();
            break;
        case State::Backoff:
            if (now - _lastRetryTick >= RETRY_INTERVAL_MS) {
                _lastRetryTick = now;
                const unsigned long retryMs = _store.get().retryMs;
                const unsigned long elapsed = now - _lastScan;
                const unsigned long remaining = elapsed >= retryMs ? 0 : retryMs - elapsed;
                const unsigned seconds = static_cast<unsigned>((remaining + 999UL) / 1000UL);
                Serial.printf("[WIFI] Reintento de escaneo en %u s\n", seconds);
            }
            if (now - _lastScan >= _store.get().retryMs) _startScan();
            break;
        case State::Scanning:
            _pollScan();
            break;
        case State::Connecting: {
            const wl_status_t status = WiFi.status();
            if (status == WL_CONNECT_FAILED || status == WL_NO_SSID_AVAIL) {
                const String failed = _currentSsid;
                const String reason = wifiFailureReason(status);
                Serial.printf("[WIFI] Fallo '%s': %s (status=%d)\n", failed.c_str(),
                              reason.c_str(), static_cast<int>(status));
                WiFi.disconnect();
                _tryNext(failed, reason);
            } else if (now - _stateSince >= CONNECT_TIMEOUT_MS) {
                const String failed = _currentSsid;
                const String reason = String("Timeout; status=") + String(static_cast<int>(status));
                Serial.printf("[WIFI] Timeout en '%s' (status=%d)\n", failed.c_str(), static_cast<int>(status));
                WiFi.disconnect();
                _tryNext(failed, reason);
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
    Serial.println("[WIFI] Escaneando redes...");
    const int16_t result = WiFi.scanNetworks(true);
    if (result == WIFI_SCAN_FAILED) {
        _lastError = "Escaneo WiFi fallido";
        Serial.printf("[WIFI] %s (codigo %d)\n", _lastError.c_str(), static_cast<int>(result));
        _state = State::Backoff;
        _lastScan = millis();
        _lastRetryTick = 0;
        _showTransientMessage("Error escaneo", "Reintento en 5s");
    }
}

void NetManager::_pollScan() {
    const int16_t count = WiFi.scanComplete();
    if (count == WIFI_SCAN_RUNNING) return;
    if (count < 0) {
        _lastError = "Escaneo WiFi fallido";
        Serial.printf("[WIFI] %s (codigo %d)\n", _lastError.c_str(), static_cast<int>(count));
        _state = State::Backoff;
        _lastScan = millis();
        _lastRetryTick = 0;
        _showTransientMessage("Error escaneo", "Reintento en 5s");
        return;
    }

    _scan.clear();
    Serial.printf("[WIFI] Detectadas %d red(es)\n", count);
    for (int i = 0; i < count; ++i) {
        const String ssid = WiFi.SSID(i);
        if (!ssid.length()) continue;
        WifiStatus status;
        status.ssid = ssid;
        status.rssi = WiFi.RSSI(i);
        status.stored = _store.hasWifi(ssid);
        status.hasPassword = _store.hasPassword(ssid);
        status.visible = true;
        status.connected = false;
        _scan.push_back(status);
        Serial.printf("[WIFI] Detectada '%s' (%ld dBm)%s\n", ssid.c_str(),
                      static_cast<long>(status.rssi), status.stored ? " [guardada]" : "");
    }

    WiFi.scanDelete();
    _buildCandidates();
    _candidate = 0;
    Serial.printf("[WIFI] Redes para intentar: %u\n", static_cast<unsigned>(_candidates.size()));
    if (count == 0) {
        Serial.println("[WIFI] Sin redes visibles; probar configuradas como ocultas (2.4 GHz)");
        _showTransientMessage("No hay redes", "Pruebo guardadas");
    }
    _tryNext();
}

void NetManager::_buildCandidates() {
    _candidates.clear();
    for (const auto& entry : _store.get().wifi) {
        for (const auto& status : _scan) {
            if (status.ssid == entry.ssid) {
                _candidates.push_back(entry.ssid);
                break;
            }
        }
    }
    for (const auto& entry : _store.get().wifi) {
        bool alreadyAdded = false;
        for (const auto& ssid : _candidates) {
            if (ssid == entry.ssid) { alreadyAdded = true; break; }
        }
        if (!alreadyAdded) _candidates.push_back(entry.ssid);
    }
}

void NetManager::_tryNext(const String& failedSsid, const String& reason) {
    if (failedSsid.length()) {
        const String next = _nextSsid();
        Serial.printf("[WIFI] Siguiente paso: %s\n", next.c_str());
        _showTransientMessage(String("Fallo: ") + failedSsid, reason + "; sigue " + next);
    }

    while (_candidate < _candidates.size()) {
        const String ssid = _candidates[_candidate++];
        const WifiEntry* entry = nullptr;
        for (const auto& candidate : _store.get().wifi) {
            if (candidate.ssid == ssid) { entry = &candidate; break; }
        }
        if (!entry) continue;

        _currentSsid = ssid;
        Serial.printf("[WIFI] Intentando '%s' (%u/%u)\n", ssid.c_str(),
                      static_cast<unsigned>(_candidate), static_cast<unsigned>(_candidates.size()));
        WiFi.begin(ssid.c_str(), entry->password.length() ? entry->password.c_str() : nullptr);
        _state = State::Connecting;
        _stateSince = millis();
        return;
    }

    _state = State::Backoff;
    _lastScan = millis();
    _lastRetryTick = 0;
    Serial.printf("[WIFI] Ninguna red conectó. Siguiente paso: reintentar en %lu ms\n",
                  _store.get().retryMs);
    _showTransientMessage("Sin conexion WiFi", "Reintento en 5s");
}

bool NetManager::addAndSave(const String& ssid, const String& password) {
    if (!_store.addWifi(ssid, password)) { _lastError = _store.lastError(); return false; }
    if (!isConnected()) {
        Serial.printf("[WIFI] Red agregada '%s', iniciando conexion\n", ssid.c_str());
        WiFi.begin(ssid.c_str(), password.length() ? password.c_str() : nullptr);
        _currentSsid = ssid;
        _state = State::Connecting;
        _stateSince = millis();
    }
    return true;
}

bool NetManager::removeAndSave(const String& ssid) {
    const bool wasConnected = isConnected() && WiFi.SSID() == ssid;
    if (!_store.removeWifi(ssid)) { _lastError = _store.lastError(); return false; }
    if (wasConnected) {
        WiFi.disconnect(); _state = State::Idle; _lastScan = 0; _wasConnected = false;
    }
    return true;
}

bool NetManager::reorderAndSave(const String& ssid, size_t newIndex) {
    if (!_store.moveWifi(ssid, newIndex)) { _lastError = _store.lastError(); return false; }
    if (!isConnected()) { _lastScan = 0; _state = State::Idle; }
    return true;
}

void NetManager::requestScan() { _lastScan = 0; _state = State::Idle; }

String NetManager::networksJson() const {
    DynamicJsonDocument doc(4096);
    JsonArray array = doc.to<JsonArray>();
    const String connectedSsid = connectedSSID();
    for (size_t i = 0; i < _store.get().wifi.size(); ++i) {
        const WifiEntry& entry = _store.get().wifi[i];
        int32_t rssi = 0; bool visible = false;
        for (const auto& status : _scan) if (status.ssid == entry.ssid) { rssi = status.rssi; visible = true; break; }
        JsonObject item = array.createNestedObject();
        item["ssid"] = entry.ssid; item["rssi"] = rssi; item["visible"] = visible;
        item["stored"] = true; item["connected"] = (entry.ssid == connectedSsid);
        item["has_password"] = entry.password.length() > 0; item["priority"] = static_cast<int>(i);
    }
    for (const auto& status : _scan) {
        if (status.stored) continue;
        JsonObject item = array.createNestedObject();
        item["ssid"] = status.ssid; item["rssi"] = status.rssi; item["visible"] = true;
        item["stored"] = false; item["connected"] = false;
        item["has_password"] = status.hasPassword; item["priority"] = -1;
    }
    String output; serializeJson(array, output); return output;
}
