#ifndef DISP_COMM_H
#define DISP_COMM_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <functional>

#include "ConfigStore.h"
#include "Crypto.h"
#include "NetManager.h"

// Recibe el estado pedido y devuelve el estado lógico real del relé tras aplicarlo.
typedef std::function<bool(bool state)> RelayCommandCallback;
// Porcentaje y litros calculados por el backend (se reciben tras cada telemetría).
typedef std::function<void(float percent, float liters)> LevelCallback;
typedef std::function<void(const String& line0, const String& line1, bool clear)> DisplayCommandCallback;
typedef std::function<void(const String& code, int expiresIn)> ClaimCodeCallback;
typedef std::function<void()> ClaimVerifiedCallback;
typedef std::function<void(const String& jsonConfig)> LcdConfigCallback;
typedef std::function<void(const String& line0, const String& line1, bool clear)> DisplayCommandCallback;
typedef std::function<void(bool isConnected)> ConnectionStatusCallback;
typedef std::function<void()> RebootCallback;
typedef std::function<void(uint16_t minutes)> SleepCallback;
typedef std::function<void()> FactoryResetCallback;
typedef std::function<void(const String& version, size_t size)> OtaStartCallback;
typedef std::function<void(uint8_t* data, size_t len)> OtaChunkCallback;
typedef std::function<void()> OtaCompleteCallback;
// Bloqueo remoto de un botón físico por su ID.
typedef std::function<void(uint8_t buttonId, bool locked)> ButtonLockCallback;
// Cerrar menú de ajustes remotamente desde el panel.
typedef std::function<void()> MenuCloseCallback;

class DispComm {
public:
    DispComm(Crypto& crypto, ConfigStore& config, NetManager& net);
    void begin();
    void update();
    bool sendTelemetry(float distanceMm, bool relayState);
    void sendPing();
    void sendDeviceStatus();
    void ack(const String& requestId, bool ok, const String& error = "");
    void ackRelay(const String& requestId, bool relayState);
    void onRelayCommand(RelayCommandCallback cb) { _relayCb = cb; }
    void onDisplayCommand(DisplayCommandCallback cb) { _displayCb = cb; }
    void onLevel(LevelCallback cb) { _levelCb = cb; }
    void onConnectionStatus(ConnectionStatusCallback cb) { _connCb = cb; }
    void onReboot(RebootCallback cb) { _rebootCb = cb; }
    void onSleep(SleepCallback cb) { _sleepCb = cb; }
    void onFactoryReset(FactoryResetCallback cb) { _factoryResetCb = cb; }
    void onClaimCode(ClaimCodeCallback cb) { _claimCodeCb = cb; }
    void onClaimVerified(ClaimVerifiedCallback cb) { _claimVerifiedCb = cb; }
    void onLcdConfig(LcdConfigCallback cb) { _lcdConfigCb = cb; }
    void onOtaStart(OtaStartCallback cb) { _otaStartCb = cb; }
    void onOtaChunk(OtaChunkCallback cb) { _otaChunkCb = cb; }
    void onOtaComplete(OtaCompleteCallback cb) { _otaCompleteCb = cb; }
    void onButtonLock(ButtonLockCallback cb) { _buttonLockCb = cb; }
    void onMenuClose(MenuCloseCallback cb) { _menuCloseCb = cb; }
    bool isWsConnected() const { return _wsConnected; }
    bool isAuthenticated() const { return _state == AuthState::Authenticated; }
    bool isPendingClaim() const { return _state == AuthState::PendingClaim; }
    bool isConnected() const { return isAuthenticated(); }
    unsigned long lastAuthenticatedMs() const { return _lastAuthMs; }
    bool backendFailureVisible() const {
        return _hasConnectionFailure && (millis() - _lastFailureMs < 3000UL);
    }
    void setWakeReason(const String& reason) { _wakeReason = reason; }

private:
    enum class AuthState { Disconnected, AwaitChallenge, Authenticating, PendingClaim, Authenticated };
    void _handleEvent(WStype_t type, uint8_t* payload, size_t length);
    void _sendAuth(const String& nonce);
    void _handleJson(const char* json);
    void _handleCommand(JsonDocument& doc);
    bool _sendJson(JsonDocument& doc);
    void _setState(AuthState state);
    void _notifyConnection();
    void _recordConnectionFailure(const char* reason);
    void _requestDisconnect();

    Crypto& _crypto;
    ConfigStore& _config;
    NetManager& _net;
    WebSocketsClient _ws;
    AuthState _state = AuthState::Disconnected;
    bool _wsConnected = false;
    bool _hasConnectionFailure = false;
    bool _pendingDisconnect = false;
    bool _inSend = false;
    unsigned long _lastFailureMs = 0;
    unsigned long _connectedAt = 0;
    unsigned long _lastPing = 0;
    unsigned long _lastAuthMs = 0;
    String _wakeReason = "power_on";
    RelayCommandCallback _relayCb;
    DisplayCommandCallback _displayCb;
    LevelCallback _levelCb;
    ConnectionStatusCallback _connCb;
    RebootCallback _rebootCb;
    SleepCallback _sleepCb;
    FactoryResetCallback _factoryResetCb;
    ClaimCodeCallback _claimCodeCb;
    ClaimVerifiedCallback _claimVerifiedCb;
    LcdConfigCallback _lcdConfigCb;
    OtaStartCallback _otaStartCb;
    OtaChunkCallback _otaChunkCb;
    OtaCompleteCallback _otaCompleteCb;
    ButtonLockCallback _buttonLockCb;
    MenuCloseCallback _menuCloseCb;
};

#endif // DISP_COMM_H
