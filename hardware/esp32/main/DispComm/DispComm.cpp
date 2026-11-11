#ifndef DISP_COMM_H
#define DISP_COMM_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <functional>

#include "ConfigStore.h"
#include "Crypto.h"
#include "NetManager.h"

typedef std::function<void(bool state)> RelayCommandCallback;
typedef std::function<void(const String& line0, const String& line1, bool clear)>
    DisplayCommandCallback;
typedef std::function<void(bool isConnected)> ConnectionStatusCallback;
typedef std::function<void()> RebootCallback;
typedef std::function<void(uint16_t minutes)> SleepCallback;
typedef std::function<void()> FactoryResetCallback;

/**
 * Comunicación WebSocket con el backend.
 *
 * Autenticación challenge-response:
 *   backend -> {event:"challenge", nonce}
 *   device  -> {event:"auth", device_id, nonce, proof=HMAC(key_hash, nonce)}
 */
class DispComm {
public:
    DispComm(Crypto& crypto, ConfigStore& config, NetManager& net);

    void begin();
    void update();

    bool sendTelemetry(float distanceMm, bool relayState);
    void sendPing();
    void sendDeviceStatus();
    void ack(const String& requestId, bool ok, const String& error = "");

    void onRelayCommand(RelayCommandCallback cb) { _relayCb = cb; }
    void onDisplayCommand(DisplayCommandCallback cb) { _displayCb = cb; }
    void onConnectionStatus(ConnectionStatusCallback cb) { _connCb = cb; }
    void onReboot(RebootCallback cb) { _rebootCb = cb; }
    void onSleep(SleepCallback cb) { _sleepCb = cb; }
    void onFactoryReset(FactoryResetCallback cb) { _factoryResetCb = cb; }

    bool isWsConnected() const { return _wsConnected; }
    bool isAuthenticated() const { return _state == AuthState::Authenticated; }
    bool isPendingClaim() const { return _state == AuthState::PendingClaim; }
    bool isConnected() const { return isAuthenticated(); }
    unsigned long lastAuthenticatedMs() const { return _lastAuthMs; }
    void setWakeReason(const String& reason) { _wakeReason = reason; }

private:
    enum class AuthState {
        Disconnected,
        AwaitChallenge,
        Authenticating,
        PendingClaim,
        Authenticated
    };

    void _handleEvent(WStype_t type, uint8_t* payload, size_t length);
    void _sendAuth(const String& nonce);
    void _handleJson(const char* json);
    void _handleCommand(JsonDocument& doc);
    bool _sendJson(JsonDocument& doc);
    void _setState(AuthState state);
    void _notifyConnection();

    Crypto& _crypto;
    ConfigStore& _config;
    NetManager& _net;
    WebSocketsClient _ws;

    AuthState _state = AuthState::Disconnected;
    bool _wsConnected = false;
    unsigned long _connectedAt = 0;
    unsigned long _lastPing = 0;
    unsigned long _lastAuthMs = 0;
    String _wakeReason = "power_on";

    RelayCommandCallback _relayCb;
    DisplayCommandCallback _displayCb;
    ConnectionStatusCallback _connCb;
    RebootCallback _rebootCb;
    SleepCallback _sleepCb;
    FactoryResetCallback _factoryResetCb;
};

#endif // DISP_COMM_H
