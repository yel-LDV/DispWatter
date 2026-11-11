#include "DispComm.h"

DispComm::DispComm(Crypto& crypto, ConfigStore& config, NetManager& net)
    : _crypto(crypto), _config(config), _net(net) {}

void DispComm::begin() {
    const DeviceConfig& cfg = _config.get();

    if (cfg.backendTls) {
        _ws.beginSSL(cfg.backendHost.c_str(), cfg.backendPort,
                     cfg.backendPath.c_str());
    } else {
        _ws.begin(cfg.backendHost.c_str(), cfg.backendPort,
                  cfg.backendPath.c_str());
    }

    _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        this->_handleEvent(type, payload, length);
    });
    _ws.setReconnectInterval(5000);

    Serial.printf("[WS] Backend %s:%u%s\n", cfg.backendHost.c_str(),
                  cfg.backendPort, cfg.backendPath.c_str());
}

void DispComm::update() {
    if (!_net.isConnected()) {
        if (_wsConnected) {
            _ws.disconnect();
        }
        return;
    }

    _ws.loop();

    if (_wsConnected && _state != AuthState::Disconnected &&
        _state != AuthState::Authenticated && _state != AuthState::PendingClaim) {
        if (millis() - _connectedAt > 12000) {
            Serial.println("[WS] Timeout esperando challenge/auth_status");
            _ws.disconnect();
        }
    }

    if (isAuthenticated() && millis() - _lastPing > 30000) {
        sendPing();
        _lastPing = millis();
    }
}

void DispComm::_handleEvent(WStype_t type, uint8_t* payload, size_t length) {
    (void)length;

    switch (type) {
        case WStype_DISCONNECTED:
            _wsConnected = false;
            _setState(AuthState::Disconnected);
            Serial.println("[WS] Desconectado del backend");
            break;

        case WStype_CONNECTED: {
            _wsConnected = true;
            _connectedAt = millis();
            _setState(AuthState::AwaitChallenge);

            StaticJsonDocument<320> hello;
            hello["event"] = "hello";
            hello["device_id"] = _config.get().deviceId;
            hello["firmware"] = _config.get().firmware;
            _sendJson(hello);

            Serial.println("[WS] Conectado; esperando challenge");
            break;
        }

        case WStype_TEXT:
            _handleJson(reinterpret_cast<const char*>(payload));
            break;

        case WStype_ERROR:
            Serial.println("[WS] Error de WebSocket");
            break;

        default:
            break;
    }
}

void DispComm::_setState(AuthState state) {
    if (_state == state) {
        return;
    }
    _state = state;

    if (state == AuthState::Authenticated) {
        _lastAuthMs = millis();
        Serial.println("[WS] Autenticado con el backend");
    }

    _notifyConnection();
}

void DispComm::_notifyConnection() {
    if (_connCb) {
        _connCb(_state == AuthState::Authenticated);
    }
}

void DispComm::_sendAuth(const String& nonce) {
    const String proof = _crypto.createAuthProof(nonce);
    if (proof.length() != 64) {
        Serial.println("[WS] No se pudo calcular el proof HMAC");
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

    if (event == "challenge") {
        const String nonce = doc["nonce"] | "";
        if (nonce.length() == 0) {
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
            Serial.printf("[WS] Autenticacion rechazada: %s\n", status.c_str());
            _ws.disconnect();
        }
        return;
    }

    if (doc.containsKey("command")) {
        _handleCommand(doc);
        return;
    }

    if (event == "pong") {
        return;
    }
}

void DispComm::_handleCommand(JsonDocument& doc) {
    const String command = doc["command"] | "";
    const String requestId = doc["request_id"] | "";

    if (!isAuthenticated()) {
        if (requestId.length() > 0) {
            ack(requestId, false, "unauthorized");
        }
        return;
    }

    if (command == "set_relay") {
        const bool state = doc["state"] | false;
        if (_relayCb) {
            _relayCb(state);
        }
        ack(requestId, true);
        return;
    }

    if (command == "display") {
        const String line0 = doc["line0"] | "";
        const String line1 = doc["line1"] | "";
        const bool clear = doc["clear"] | false;
        if (_displayCb) {
            _displayCb(line0, line1, clear);
        }
        ack(requestId, true);
        return;
    }

    if (command == "wifi_list") {
        const String networks = _net.networksJson();
        DynamicJsonDocument response(4600);
        response["event"] = "wifi_list";
        response["request_id"] = requestId;

        DynamicJsonDocument array(4096);
        if (!deserializeJson(array, networks)) {
            response["networks"] = array.as<JsonArray>();
        } else {
            response["networks"] = serialized("[]");
        }
        _sendJson(response);
        return;
    }

    if (command == "wifi_add") {
        const String ssid = doc["ssid"] | "";
        const String password = doc["password"] | "";
        const bool ok = _net.addAndSave(ssid, password);
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }

    if (command == "wifi_remove") {
        const String ssid = doc["ssid"] | "";
        const bool ok = _net.removeAndSave(ssid);
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }

    if (command == "wifi_reorder") {
        const String ssid = doc["ssid"] | "";
        const size_t index = doc["index"] | 0;
        const bool ok = _net.reorderAndSave(ssid, index);
        ack(requestId, ok, ok ? "" : _net.lastError());
        return;
    }

    if (command == "reboot") {
        ack(requestId, true);
        delay(300);
        if (_rebootCb) {
            _rebootCb();
        }
        return;
    }

    if (command == "sleep") {
        const uint16_t minutes = doc["minutes"] | 60;
        ack(requestId, true);
        delay(300);
        if (_sleepCb) {
            _sleepCb(minutes);
        }
        return;
    }

    if (command == "factory_reset") {
        ack(requestId, true);
        delay(300);
        if (_factoryResetCb) {
            _factoryResetCb();
        }
        return;
    }

    ack(requestId, false, "unknown_command");
}

bool DispComm::sendTelemetry(float distanceMm, bool relayState) {
    if (!isAuthenticated()) {
        return false;
    }

    StaticJsonDocument<384> doc;
    doc["event"] = "telemetry";
    doc["device_id"] = _config.get().deviceId;
    doc["distance_mm"] = distanceMm;
    doc["relay_state"] = relayState;
    doc["timestamp"] = millis() / 1000;
    doc["rssi"] = _net.rssi();

    _sendJson(doc);
    return true;
}

void DispComm::sendPing() {
    if (!_wsConnected) {
        return;
    }
    StaticJsonDocument<192> doc;
    doc["event"] = "ping";
    doc["device_id"] = _config.get().deviceId;
    _sendJson(doc);
}

void DispComm::sendDeviceStatus() {
    if (!_wsConnected) {
        return;
    }

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
    if (!ok && error.length() > 0) {
        doc["error"] = error;
    }
    _sendJson(doc);
}

void DispComm::_sendJson(JsonDocument& doc) {
    String output;
    serializeJson(doc, output);
    _ws.sendTXT(output);
}
