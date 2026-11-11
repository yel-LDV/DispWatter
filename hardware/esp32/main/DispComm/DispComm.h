#ifndef DISP_COMM_H
#define DISP_COMM_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "Crypto.h"
#include <functional>

struct WiFiCred {
    const char *ssid;
    const char *pass;
};

typedef std::function<void(bool state)> RelayCommandCallback;
typedef std::function<void(const String &line0, const String &line1, bool clear)> DisplayCommandCallback;
typedef std::function<void(bool isConnected)> ConnectionStatusCallback;

class DispComm {
public:
    DispComm(Crypto &crypto);

    // Inicializa con lista de múltiples redes WiFi (cambia automáticamente a la disponible)
    void begin(const WiFiCred *networks, size_t networkCount,
               const char *wsHost, uint16_t wsPort, const char *wsPath = "/ws/device");

    // Sobrecarga para una sola red WiFi
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

    void setDeviceInfo(const char *name, const char *location = "Sin ubicación", const char *fwVersion = "1.0.0") {
        _name = name;
        _location = location;
        _fwVersion = fwVersion;
    }

    bool isConnected() const { return _wsConnected && _isAuthenticated; }
    bool isWiFiConnected() const { return WiFi.status() == WL_CONNECTED; }
    String getConnectedSSID() const { return WiFi.SSID(); }

private:
    Crypto &_crypto;
    WiFiMulti _wifiMulti;
    WebSocketsClient _webSocket;

    const char *_wsHost;
    uint16_t _wsPort;
    const char *_wsPath;
    const char *_name;
    const char *_location;
    const char *_fwVersion;

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
