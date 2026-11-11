#ifndef NET_MANAGER_H
#define NET_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <vector>

#include "ConfigStore.h"

struct WifiStatus {
    String ssid;
    int32_t rssi = 0;
    bool stored = false;
    bool connected = false;
    bool hasPassword = false;
    bool visible = false;
};

/**
 * Conexión WiFi con prioridad manual: recorre las redes guardadas
 * en el orden de /config.json.
 */
class NetManager {
public:
    explicit NetManager(ConfigStore& store);

    void begin();
    void update();

    bool isConnected() const;
    String connectedSSID() const;
    int32_t rssi() const;
    IPAddress ip() const;

    // Estado de conexión resumido para la pantalla LCD de 16 columnas.
    String statusLine0() const;
    String statusLine1() const;

    bool addAndSave(const String& ssid, const String& password);
    bool removeAndSave(const String& ssid);
    bool reorderAndSave(const String& ssid, size_t newIndex);
    void requestScan();

    String networksJson() const;
    const String& lastError() const { return _lastError; }

private:
    enum class State { Idle, Scanning, Connecting, Connected, Backoff };

    void _startScan();
    void _pollScan();
    void _buildCandidates();
    void _tryNext(const String& failedSsid = "", const String& reason = "");
    void _showTransientMessage(const String& line0, const String& line1);
    String _nextSsid() const;

    ConfigStore& _store;
    State _state = State::Idle;
    unsigned long _stateSince = 0;
    unsigned long _lastScan = 0;
    unsigned long _messageUntil = 0;
    size_t _candidate = 0;
    bool _wasConnected = false;
    std::vector<String> _candidates;
    std::vector<WifiStatus> _scan;
    String _lastError;
    String _currentSsid;
    String _messageLine0;
    String _messageLine1;
};

#endif // NET_MANAGER_H
