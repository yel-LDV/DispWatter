#include "Relay.h"

void Relay::begin(uint8_t pin, bool activeLow) {
    _pin = pin;
    _activeLow = activeLow;
    _state = false;
    _onSince = 0;
    pinMode(_pin, OUTPUT);
    forceOff();
}

void Relay::set(bool on) {
    if (on && !_state) {
        _onSince = millis();
    }
    _state = on;
    const uint8_t level = on ? (_activeLow ? LOW : HIGH)
                             : (_activeLow ? HIGH : LOW);
    digitalWrite(_pin, level);
}

void Relay::forceOff() {
    _state = false;
    _onSince = 0;
    digitalWrite(_pin, _activeLow ? HIGH : LOW);
}

bool Relay::guard(unsigned long now, unsigned long lastAuthMs,
                  unsigned long maxOnMs, unsigned long maxOfflineMs) {
    if (!_state) {
        return false;
    }

    bool shouldOff = false;

    if (maxOnMs > 0 && (now - _onSince) >= maxOnMs) {
        Serial.println("[RELE] Fail-safe: tiempo máximo encendido superado.");
        shouldOff = true;
    }

    if (maxOfflineMs > 0 && lastAuthMs != 0 &&
        (now - lastAuthMs) >= maxOfflineMs) {
        Serial.println("[RELE] Fail-safe: backend sin autenticar demasiado tiempo.");
        shouldOff = true;
    }

    if (shouldOff) {
        forceOff();
    }
    return shouldOff;
}
