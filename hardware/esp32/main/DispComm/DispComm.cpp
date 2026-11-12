#include "DispComm.h"

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
    _ws.setReconnectInterval(5000);
    Serial.printf("[WS] Buscando servicio ws%s://%s:%u%s (reintento cada 5 s)\n",
                  cfg.backendTls ? "s" : "", cfg.backendHost.c_str(),
                  cfg.backendPort, cfg.backendPath.c_str());
}

void DispComm::update() {
    if (!_net.isConnected()) {
        if (_wsConnected) _ws.disconnect();
        return;
    }
    _ws.loop();
    // Mientras haya sesión autenticada el backend está "vivo": se refresca la
    // marca para que el fail-safe de max_offline_min mida tiempo SIN conexión
    // y no tiempo desde la última autenticación.
    if (isAuthenticated() && _wsConnected) {
        _lastAuthMs = millis();
    }
    if (_pendingDisconnect) {
        _pendingDisconnect = false;
        _ws.disconnect();
        return;
    }
    if (_wsConnected && _state != AuthState::Disconnected &&
        _state != AuthState::Authenticated && _state != AuthState::PendingClaim &&
        millis() - _connectedAt > 12000UL) {
        _recordConnectionFailure("timeout esperando challenge/auth_status");
        _requestDisconnect();
    }
    if (isAuthenticated() && millis() - _lastPing > 30000UL) {
        sendPing();
        _lastPing = millis();
    }
}

void DispComm::_requestDisconnect() {
    _pendingDisconnect = true;
}

void DispComm::_recordConnectionFailure(const char* reason) {
    _hasConnectionFailure = true;
    _lastFailureMs = millis();
    Serial.printf("[WS] Servicio no disponible: %s. Reintento en 5 s\n", reason);
}

void DispComm::_handleEvent(WStype_t type, uint8_t* payload, size_t length) {
    (void)length;
    switch (type) {
        case WStype_DISCONNECTED:
            if (_wsConnected || _state != AuthState::Disconnected)
                _recordConnectionFailure("conexión cerrada");
            _wsConnected = false;
            _setState(AuthState::Disconnected);
            Serial.println("[WS] Desconectado del backend");
            break;
        case WStype_CONNECTED: {
            _wsConnected = true;
            _connectedAt = millis();
            _setState(AuthState::AwaitChallenge);
            DynamicJsonDocument hello(320);
            hello["event"] = "hello";
            hello["device_id"] = _config.get().deviceId;
            hello["firmware"] = _config.get().firmware;
            Serial.printf("[WS] Conectado a %s:%u%s; enviando hello para %s\n",
                          _config.get().backendHost.c_str(), _config.get().backendPort,
                          _config.get().backendPath.c_str(), _config.get().deviceId.c_str());
            _sendJson(hello);
            break;
        }
        case WStype_TEXT:
            _handleJson(reinterpret_cast<const char*>(payload));
            break;
        case WStype_ERROR:
            _recordConnectionFailure("error de WebSocket");
            Serial.println("[WS] Error de WebSocket");
            break;
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
        _recordConnectionFailure("no se pudo calcular proof HMAC");
        _requestDisconnect();
        return;
    }
    const DeviceConfig& cfg = _config.get();
    DynamicJsonDocument doc(768);
    doc["event"] = "auth";
    doc["device_id"] = cfg.deviceId;
    doc["nonce"] = nonce;
    doc["proof"] = proof;
    doc["name"] = cfg.deviceName;
    doc["location"] = cfg.location;
    doc["firmware"] = cfg.firmware;
    doc["wake_reason"] = _wakeReason;
    Serial.printf("[WS] Enviando autenticación para %s\n", cfg.deviceId.c_str());
    _setState(AuthState::Authenticating);
    _sendJson(doc);
}

void DispComm::_handleJson(const char* json) {
    DynamicJsonDocument doc(2048);
    const DeserializationError error = deserializeJson(doc, json);
    if (error) {
        Serial.printf("[WS] JSON inválido: %s\n", error.c_str());
        return;
    }
    const String event = doc["event"] | "";
    Serial.printf("[WS] Recibido evento: %s\n", event.c_str());
    if (event == "challenge") {
        const String nonce = doc["nonce"] | "";
        if (nonce.length() == 0) {
            _recordConnectionFailure("challenge sin nonce");
            _requestDisconnect();
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
            _recordConnectionFailure(errorText.c_str());
            _requestDisconnect();
        }
        return;
    }
    if (event == "level") {
        if (isAuthenticated() && _levelCb && doc.containsKey("percent") && doc.containsKey("liters")) {
            _levelCb(doc["percent"] | 0.0f, doc["liters"] | 0.0f);
        }
        return;
    }
    if (event == "claim_code") {
        const String code = doc["code"] | "";
        const int expiresIn = doc["expires_in"] | 15;
        if (_claimCodeCb && code.length() > 0) {
            _claimCodeCb(code, expiresIn);
        }
        return;
    }
    if (event == "lcd_config") {
        if (_lcdConfigCb && doc.containsKey("config")) {
            String jsonConfig;
            serializeJson(doc["config"], jsonConfig);
            _lcdConfigCb(jsonConfig);
        }
        return;
    }
    if (event == "claim_verified") {
        _setState(AuthState::Authenticated);
        _lastAuthMs = millis();
        _notifyConnection();
        if (_claimVerifiedCb) _claimVerifiedCb();
        return;
    }
    if (event == "ota_start") {
        const String version = doc["version"] | "";
        const size_t size = doc["size"] | 0;
        if (_otaStartCb && version.length() > 0) {
            _otaStartCb(version, size);
        }
        return;
    }
    if (event == "ota_chunk") {
        if (_otaChunkCb && doc.containsKey("data")) {
            String hexData = doc["data"] | "";
            size_t len = hexData.length() / 2;
            if (len > 0) {
                uint8_t* bytes = new uint8_t[len];
                for (size_t i = 0; i < len; i++) {
                    bytes[i] = (uint8_t)strtol(hexData.c_str() + i * 2, nullptr, 16);
                }
                _otaChunkCb(bytes, len);
                delete[] bytes;
            }
        }
        return;
    }
    if (event == "ota_complete") {
        if (_otaCompleteCb) {
            _otaCompleteCb();
        }
        return;
    }
    if (event == "ota_error") {
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
        if (!_relayCb) {
            ack(requestId, false, "relay_unavailable");
            return;
        }
        const bool actual = _relayCb(state);
        // El ack lleva el estado REAL del relé para que el panel no dependa
        // de lo que pidió, sino de lo que el firmware dejó aplicado.
        ackRelay(requestId, actual);
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
    DynamicJsonDocument doc(384);
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
    DynamicJsonDocument doc(192);
    doc["event"] = "ping";
    doc["device_id"] = _config.get().deviceId;
    _sendJson(doc);
}

void DispComm::sendDeviceStatus() {
    if (!_wsConnected) return;
    const DeviceConfig& cfg = _config.get();
    DynamicJsonDocument doc(512);
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
    DynamicJsonDocument doc(256);
    doc["event"] = "ack";
    doc["request_id"] = requestId;
    doc["ok"] = ok;
    if (!ok && error.length() > 0) doc["error"] = error;
    _sendJson(doc);
}

void DispComm::ackRelay(const String& requestId, bool relayState) {
    DynamicJsonDocument doc(256);
    doc["event"] = "ack";
    doc["request_id"] = requestId;
    doc["ok"] = true;
    doc["relay_state"] = relayState;
    _sendJson(doc);
}

bool DispComm::_sendJson(JsonDocument& doc) {
    // Evita recursión (p. ej. un envío disparado desde un callback de sendTXT).
    if (_inSend) {
        Serial.println("[WS] _sendJson reentrante ignorado");
        return false;
    }
    struct Guard {
        bool& flag;
        explicit Guard(bool& f) : flag(f) { flag = true; }
        ~Guard() { flag = false; }
    } guard(_inSend);

    String output;
    serializeJson(doc, output);
    String event = doc["event"] | doc["command"] | "msg";
    if (!_wsConnected) {
        Serial.printf("[WS] No se envió %s: socket desconectado\n", event.c_str());
        return false;
    }
    const bool ok = _ws.sendTXT(output);
    Serial.printf("[WS] Envío %s: %s\n", event.c_str(), ok ? "aceptado por socket" : "falló");
    if (!ok) {
        _recordConnectionFailure("falló sendTXT");
        _requestDisconnect();
        return false;
    }
    return true;
}
