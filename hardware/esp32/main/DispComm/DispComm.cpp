#include "DispComm.h"

DispComm::DispComm(Crypto &crypto)
    : _crypto(crypto),
      _ssid(nullptr),
      _wifiPass(nullptr),
      _wsHost(nullptr),
      _wsPort(80),
      _wsPath("/ws/device"),
      _wsConnected(false),
      _isAuthenticated(false),
      _lastWiFiCheck(0),
      _lastPingTime(0),
      _relayCb(nullptr),
      _displayCb(nullptr),
      _connCb(nullptr) {}

void DispComm::begin(const char *ssid, const char *password,
                     const char *wsHost, uint16_t wsPort, const char *wsPath) {
    _ssid = ssid;
    _wifiPass = password;
    _wsHost = wsHost;
    _wsPort = wsPort;
    _wsPath = wsPath;

    WiFi.mode(WIFI_STA);
    WiFi.begin(_ssid, _wifiPass);

    _webSocket.begin(_wsHost, _wsPort, _wsPath);
    _webSocket.onEvent([this](WStype_t type, uint8_t *payload, size_t length) {
        this->_handleWebSocketEvent(type, payload, length);
    });
    _webSocket.setReconnectInterval(3000);
}

void DispComm::update() {
    _checkWiFi();
    if (WiFi.status() == WL_CONNECTED) {
        _webSocket.loop();

        // Enviar ping cada 30 segundos si está autenticado
        if (_wsConnected && _isAuthenticated && (millis() - _lastPingTime > 30000)) {
            sendPing();
            _lastPingTime = millis();
        }
    }
}

void DispComm::_checkWiFi() {
    if (millis() - _lastWiFiCheck > 5000) {
        _lastWiFiCheck = millis();
        if (WiFi.status() != WL_CONNECTED && _ssid != nullptr) {
            WiFi.reconnect();
        }
    }
}

void DispComm::_handleWebSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            _wsConnected = false;
            _isAuthenticated = false;
            if (_connCb) _connCb(false);
            break;

        case WStype_CONNECTED:
            _wsConnected = true;
            _sendAuthHandshake();
            break;

        case WStype_TEXT:
            _parseIncomingJson((const char *)payload);
            break;

        default:
            break;
    }
}

void DispComm::_sendAuthHandshake() {
    uint32_t ts = millis() / 1000;
    String token = _crypto.createAuthToken(ts);

    StaticJsonDocument<256> doc;
    doc["event"] = "auth";
    doc["device_id"] = _crypto.getDeviceId();
    doc["token"] = token;
    doc["timestamp"] = ts;

    String output;
    serializeJson(doc, output);
    _webSocket.sendTXT(output);
}

void DispComm::_parseIncomingJson(const char *jsonStr) {
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, jsonStr);
    if (err) return;

    // Verificar respuesta de autenticación
    if (doc.containsKey("auth_status")) {
        const char *status = doc["auth_status"];
        if (strcmp(status, "ok") == 0) {
            _isAuthenticated = true;
            if (_connCb) _connCb(true);
        } else {
            _isAuthenticated = false;
            if (_connCb) _connCb(false);
        }
    }

    // Comandos de control enviados por el backend
    if (doc.containsKey("command")) {
        const char *cmd = doc["command"];

        if (strcmp(cmd, "set_relay") == 0 && _relayCb) {
            bool state = doc["state"].as<bool>();
            _relayCb(state);
        } else if (strcmp(cmd, "display") == 0 && _displayCb) {
            String line0 = doc["line0"] | "";
            String line1 = doc["line1"] | "";
            bool clear = doc["clear"] | false;
            _displayCb(line0, line1, clear);
        }
    }
}

bool DispComm::sendTelemetry(float distanceMm, bool relayState) {
    if (!isConnected()) return false;

    StaticJsonDocument<256> doc;
    doc["event"] = "telemetry";
    doc["device_id"] = _crypto.getDeviceId();
    doc["distance_mm"] = distanceMm;
    doc["relay_state"] = relayState;
    doc["timestamp"] = millis() / 1000;

    String output;
    serializeJson(doc, output);
    return _webSocket.sendTXT(output);
}

void DispComm::sendPing() {
    if (!_wsConnected) return;
    StaticJsonDocument<128> doc;
    doc["event"] = "ping";
    doc["device_id"] = _crypto.getDeviceId();

    String output;
    serializeJson(doc, output);
    _webSocket.sendTXT(output);
}
