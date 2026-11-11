#include "DispComm.h"

namespace {
constexpr unsigned long RECONNECT_INTERVAL_MS = 5000;
constexpr unsigned long CONNECT_TIMEOUT_MS = 15000;
constexpr unsigned long AUTH_TIMEOUT_MS = 15000;
constexpr size_t MAX_ERROR_LENGTH = 72;
}

DispComm::DispComm(Crypto& crypto, ConfigStore& config, NetManager& net)
    : _crypto(crypto), _config(config), _net(net) {}

void DispComm::begin() {
    const DeviceConfig& cfg = _config.get();
    if (cfg.backendTls) {
        _ws.beginSSL(cfg.backendHost.c_str(), cfg.backendPort, cfg.backendPath.c_str());
    } else {
        _ws.begin(cfg.backendHost.c_str(), cfg.backendPort, cfg.backendPath.c_str());
    }
    _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        this->_handleEvent(type, payload, length);
    });
    _ws.setReconnectInterval(RECONNECT_INTERVAL_MS);
    _lastConnectionProgressMs = millis();
    Serial.printf("[WS] Backend configurado: %s://%s:%u%s; timeout %lus; reintento cada %lus\n",
                  cfg.backendTls ? "wss" : "ws", cfg.backendHost.c_str(), cfg.backendPort,
                  cfg.backendPath.c_str(), CONNECT_TIMEOUT_MS / 1000,
                  RECONNECT_INTERVAL_MS / 1000);
}

String DispComm::_endpoint() const {
    const DeviceConfig& cfg = _config.get();
    return String(cfg.backendTls ? "wss://" : "ws://") + cfg.backendHost + ":" +
           String(cfg.backendPort) + cfg.backendPath;
}

String DispComm::statusLine0() const {
    if (_state == AuthState::Authenticated) return "Backend autent.";
    if (_state == AuthState::PendingClaim) return "Pendiente claim";
    if (_hasConnectionFailure) {
        const unsigned long elapsed = millis() - _lastFailureMs;
        const unsigned long remaining = elapsed >= RECONNECT_INTERVAL_MS
            ? 0 : RECONNECT_INTERVAL_MS - elapsed;
        const unsigned seconds = static_cast<unsigned>((remaining + 999UL) / 1000UL);
        return String("WS error: ") + _lastError + " " + String(seconds) + "s";
    }
    switch (_state) {
        case AuthState::Disconnected: return "Conectando WS";
        case AuthState::AwaitChallenge: return "WS OK, espera auth";
        case AuthState::Authenticating: return "Autenticando WS";
        case AuthState::PendingClaim: return "Pendiente claim";
        case AuthState::Authenticated: return "Backend autent.";
        default: return "Conectando WS";
    }
}

String DispComm::statusLine1() const {
    return _endpoint();
}

void DispComm::update() {
    if (!_net.isConnected()) {
        if (_wsConnected) _ws.disconnect();
        return;
    }

    _ws.loop();
    const unsigned long now = millis();

    if (!_wsConnected && now - _lastConnectionProgressMs >= CONNECT_TIMEOUT_MS) {
        _recordConnectionFailure("sin respuesta");
        // Avoid repeating the timeout every loop; next diagnostic window begins now.
        _lastConnectionProgressMs = now;
    }

    if (_wsConnected && _state != AuthState::Disconnected &&
        _state != AuthState::Authenticated && _state != AuthState::PendingClaim &&
        now - _connectedAt > AUTH_TIMEOUT_MS) {
        _recordConnectionFailure("timeout auth");
        _ws.disconnect();
    }
    if (isAuthenticated() && now - _lastPing > 30000UL) {
        sendPing();
        _lastPing = now;
    }
}

void DispComm::_recordConnectionFailure(const String& reason) {
    _hasConnectionFailure = true;
    _lastFailureMs = millis();
    _lastError = reason;
    Serial.printf("[WS] Error conectando a %s: %s. Reintento en %lus\n",
                  _endpoint().c_str(), _lastError.c_str(), RECONNECT_INTERVAL_MS / 1000);
}

void DispComm::_handleEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            if (_wsConnected || _state != AuthState::Disconnected) {
                _recordConnectionFailure("socket cerrado");
            }
            _wsConnected = false;
            _state = AuthState::Disconnected;
            _lastConnectionProgressMs = millis();
            _notifyConnection();
            Serial.println("[WS] Desconectado del backend");
            break;
        case WStype_CONNECTED: {
            _wsConnected = true;
            _hasConnectionFailure = false;
            _lastError = "";
            _lastConnectionProgressMs = millis();
            _connectedAt = millis();
            _setState(AuthState::AwaitChallenge);
            StaticJsonDocument<320> hello;
            hello["event"] = "hello";
            hello["device_id"] = _config.get().deviceId;
            hello["firmware"] = _config.get().firmware;
            Serial.printf("[WS] Conectado a %s; enviando hello para %s\n",
                          _endpoint().c_str(), _config.get().deviceId.c_str());
            _sendJson(hello);
            break;
        }
        case WStype_TEXT:
            _handleJson(reinterpret_cast<const char*>(payload));
            break;
        case WStype_ERROR: {
            char detail[MAX_ERROR_LENGTH + 1] = {0};
            const size_t copyLength = (payload && length < MAX_ERROR_LENGTH) ? length
                                      : (payload ? MAX_ERROR_LENGTH : 0);
            if (copyLength) memcpy(detail, payload, copyLength);
            _recordConnectionFailure(copyLength ? String(detail) : String("error socket"));
            _lastConnectionProgressMs = millis();
            break;
        }
        default:
            break;
    }
}

void DispComm::_setState(AuthState state) {
    if (_state == state) return;
    _state = state;
    if (state == AuthState::Authenticated) {
        _lastAuthMs = millis();
        _hasConnectionFailure = false;
        _lastError = "";
        Serial.println("[WS] Autenticado con el backend");
    }
    _notifyConnection();
}

void DispComm::_notifyConnection() {
    if (_connCb) _connCb(_state == AuthState::Authenticated);
}

void DispComm::_sendAuth(const String& nonce) {
    const String proof = _crypto.createAuthProof(nonce);
    if (proof.length() != 64) {
        _recordConnectionFailure("proof HMAC invalido");
        _ws.disconnect();
        return;
    }
    const DeviceConfig& cfg = _config.get();
    StaticJsonDocument<768> doc;
    doc["event"] = "auth";
    doc["device_id"] = cfg.deviceId;
    doc["nonce"] = nonce;
    doc["proof"] = proof;
    doc["name"] = cfg.deviceName;
    doc["location"] = cfg.location;
    doc["firmware"] = cfg.firmware;
    doc["wake_reason"] = _wakeReason;
    Serial.printf("[WS] Enviando autenticacion para %s\n", cfg.deviceId.c_str());
    _setState(AuthState::Authenticating);
    _sendJson(doc);
}

void DispComm::_handleJson(const char* json) {
    DynamicJsonDocument doc(2048);
    const DeserializationError error = deserializeJson(doc, json);
    if (error) {
        Serial.printf("[WS] JSON invalido: %s\n", error.c_str());
        return;
    }
    const String event = doc["event"] | "";
    Serial.printf("[WS] Recibido evento: %s\n", event.c_str());
    if (event == "challenge") {
        const String nonce = doc["nonce"] | "";
        if (nonce.length() == 0) {
            _recordConnectionFailure("challenge sin nonce");
            _ws.disconnect();
            return;
        }
        _sendAuth(nonce);
        return;
    }
    if (event == "auth_status") {
        const String status = doc["status"] | "";
        if (status == "ok") {
            _setState(AuthState::Authenticated);
            sendDeviceStatus();
        } else if (status == "pending_claim") {
            _setState(AuthState::PendingClaim);
            sendDeviceStatus();
        } else {
            const String errorText = doc["error"] | status;
            _recordConnectionFailure(errorText);
            _ws.disconnect();
        }
        return;
    }
    if (doc.containsKey("command")) {
        _handleCommand(doc);
        return;
    }
    if (event == "pong") return;
}

void DispComm::_handleCommand(JsonDocument& doc) {
    const String command = doc["command"] | "";
    const String requestId = doc["request_id"] | "";
    if (!isAuthenticated()) {
        if (requestId.length() > 0) ack(requestId, false, "unauthorized");
        return;
    }
    if (command == "set_relay") {
        const bool state = doc["state"] | false;
        if (_relayCb) _relayCb(state);
        ack(requestId, true);
        return;
    }
    if (command == "display") {
        const String line0 = doc["line0"] | "";
        const String line1 = doc["line1"] | "";
        const bool clear = doc["clear"] | false;
        if (_displayCb) _displayCb(line0, line1, clear);
        ack(requestId, true);
        return;
    }
    if (command == "wifi_list") {
        const String networks = _net.networksJson();
        DynamicJsonDocument response(4600);
        response["event"] = "wifi_list";
        response["request_id"] = requestId;
        DynamicJsonDocument array(4096);
        if (!deserializeJson(array, networks)) response["networks"] = array.as<JsonArray>();
        else response["networks"] = serialized("[]");
        _sendJson(response);
        return;
    }
    if (command == "wifi_add") {
        const bool ok = _net.addAndSave(doc["ssid"] | "", doc["password"] | "");
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }
    if (command == "wifi_remove") {
        const bool ok = _net.removeAndSave(doc["ssid"] | "");
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }
    if (command == "wifi_reorder") {
        const bool ok = _net.reorderAndSave(doc["ssid"] | "", doc["index"] | 0);
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }
    if (command == "reboot") {
        ack(requestId, true); delay(300); if (_rebootCb) _rebootCb(); return;
    }
    if (command == "sleep") {
        const uint16_t minutes = doc["minutes"] | 60;
        ack(requestId, true); delay(300); if (_sleepCb) _sleepCb(minutes); return;
    }
    if (command == "factory_reset") {
        ack(requestId, true); delay(300); if (_factoryResetCb) _factoryResetCb(); return;
    }
    ack(requestId, false, "unknown_command");
}

bool DispComm::sendTelemetry(float distanceMm, bool relayState) {
    if (!isAuthenticated()) return false;
    StaticJsonDocument<384> doc;
    doc["event"] = "telemetry";
    doc["device_id"] = _config.get().deviceId;
    doc["distance_mm"] = distanceMm;
    doc["relay_state"] = relayState;
    doc["timestamp"] = millis() / 1000;
    doc["rssi"] = _net.rssi();
    Serial.printf("[WS] Enviando telemetry distance=%.1f relay=%s\n", distanceMm,
                  relayState ? "ON" : "OFF");
    return _sendJson(doc);
}

void DispComm::sendPing() {
    if (!_wsConnected) return;
    StaticJsonDocument<192> doc;
    doc["event"] = "ping";
    doc["device_id"] = _config.get().deviceId;
    _sendJson(doc);
}

void DispComm::sendDeviceStatus() {
    if (!_wsConnected) return;
    const DeviceConfig& cfg = _config.get();
    StaticJsonDocument<512> doc;
    doc["event"] = "device_status";
    doc["device_id"] = cfg.deviceId;
    doc["uptime_s"] = millis() / 1000;
    doc["rssi"] = _net.rssi();
    doc["ip"] = _net.ip().toString();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["wake_reason"] = _wakeReason;
    doc["firmware"] = cfg.firmware;
    doc["pending_claim"] = isPendingClaim();
    _sendJson(doc);
}

void DispComm::ack(const String& requestId, bool ok, const String& error) {
    StaticJsonDocument<256> doc;
    doc["event"] = "ack";
    doc["request_id"] = requestId;
    doc["ok"] = ok;
    if (!ok && error.length() > 0) doc["error"] = error;
    _sendJson(doc);
}

bool DispComm::_sendJson(JsonDocument& doc) {
    String output;
    serializeJson(doc, output);
    String event = doc["event"] | doc["command"] | "msg";
    if (!_wsConnected) {
        Serial.printf("[WS] No se envio %s: socket desconectado\n", event.c_str());
        return false;
    }
    const bool ok = _ws.sendTXT(output);
    Serial.printf("[WS] Envio %s: %s\n", event.c_str(), ok ? "aceptado por socket" : "fallo");
    if (!ok) {
        _recordConnectionFailure("fallo sendTXT");
        _ws.disconnect();
        return false;
    }
    return true;
}
