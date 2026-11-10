#ifndef DISP_COMM_H
#define DISP_COMM_H

#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "Crypto.h"
#include <functional>

typedef std::function<void(bool state)> RelayCommandCallback;
typedef std::function<void(const String &line0, const String &line1, bool clear)> DisplayCommandCallback;
typedef std::function<void(bool isConnected)> ConnectionStatusCallback;

class DispComm {
public:
    DispComm(Crypto &crypto);

    // Inicializa la configuración de red y WebSocket
    void begin(const char *ssid, const char *password,
               const char *wsHost, uint16_t wsPort, const char *wsPath = "/ws/device");

    // Debe llamarse en el loop() principal para atender eventos de red
    void update();

    // Envía la medición de distancia y el estado actual del relé
    bool sendTelemetry(float distanceMm, bool relayState);

    // Envía mensaje ping para mantener vivo el enlace
    void sendPing();

    // Callbacks para que el backend controle el hardware
    void onRelayCommand(RelayCommandCallback cb) { _relayCb = cb; }
    void onDisplayCommand(DisplayCommandCallback cb) { _displayCb = cb; }
    void onConnectionStatus(ConnectionStatusCallback cb) { _connCb = cb; }

    bool isConnected() const { return _wsConnected && _isAuthenticated; }
    bool isWiFiConnected() const { return WiFi.status() == WL_CONNECTED; }

private:
    Crypto &_crypto;
    WebSocketsClient _webSocket;

    const char *_ssid;
    const char *_wifiPass;
    const char *_wsHost;
    uint16_t _wsPort;
    const char *_wsPath;

    bool _wsConnected;
    bool _isAuthenticated;
    unsigned long _lastWiFiCheck;
    unsigned long _lastPingTime;

    RelayCommandCallback _relayCb;
    DisplayCommandCallback _displayCb;
    ConnectionStatusCallback _connCb;

    void _checkWiFi();
    void _sendAuthHandshake();
    void _handleWebSocketEvent(WStype_t type, uint8_t *payload, size_t length);
    void _parseIncomingJson(const char *jsonStr);
};

#endif // DISP_COMM_H
