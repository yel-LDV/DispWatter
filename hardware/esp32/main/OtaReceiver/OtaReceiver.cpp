#include "OtaReceiver.h"
#include <Arduino.h>

OtaReceiver::OtaReceiver()
    : _totalSize(0), _writtenSize(0), _confirming(false), _active(false) {
}

void OtaReceiver::begin() {
    reset();
}

bool OtaReceiver::start(uint8_t* data, size_t len, size_t total) {
    if (_active) {
        rollback();
    }
    _totalSize = total;
    _writtenSize = 0;
    _confirming = false;
    _active = true;

    if (!Update.begin(total, U_FLASH)) {
        Update.printError(Serial);
        _active = false;
        return false;
    }
    if (data && len > 0) {
        _writtenSize = Update.write(data, len);
    }
    return true;
}

bool OtaReceiver::receiveChunk(uint8_t* data, size_t len) {
    if (!_active || !data || len == 0) return false;
    _writtenSize = Update.write(data, len);
    return true;
}

bool OtaReceiver::confirm() {
    if (!_active) return false;
    _confirming = true;
    return true;
}

void OtaReceiver::rollback() {
    if (_active) {
        Update.abort();
    }
    reset();
}

bool OtaReceiver::isConfirming() const {
    return _confirming;
}

void OtaReceiver::setConfirm() {
    _confirming = true;
    if (_active && Update.end(true)) {
        ESP.restart();
    }
    _active = false;
}

float OtaReceiver::progress() const {
    if (_totalSize == 0) return 0.0f;
    return (static_cast<float>(_writtenSize) / _totalSize) * 100.0f;
}

bool OtaReceiver::isActive() const {
    return _active;
}

void OtaReceiver::reset() {
    _totalSize = 0;
    _writtenSize = 0;
    _confirming = false;
    _active = false;
}
