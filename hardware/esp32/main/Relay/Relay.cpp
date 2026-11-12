#include "Relay.h"

// Nivel físico que hay que escribir en el pin para el estado lógico pedido.
//   activo en LOW : ON -> LOW,  OFF -> HIGH
//   activo en HIGH: ON -> HIGH, OFF -> LOW
uint8_t Relay::_levelFor(bool on) const {
    const bool high = _activeLow ? !on : on;
    return high ? HIGH : LOW;
}

void Relay::begin(uint8_t pin, bool activeLow) {
    _pin = pin;
    _activeLow = activeLow;
    _state = false;
    _onSince = 0;
    // Primero se fija el nivel de "apagado" y después se pasa a salida, así el
    // pin nunca emite un pulso en el nivel de "encendido" durante el arranque.
    digitalWrite(_pin, _levelFor(false));
    pinMode(_pin, OUTPUT);
    digitalWrite(_pin, _levelFor(false));
}

void Relay::setPolarity(bool activeLow) {
    _activeLow = activeLow;
    forceOff();
}

void Relay::set(bool on) {
    if (on && !_state) {
        _onSince = millis();
    }
    if (!on) {
        _onSince = 0;
    }
    _state = on;
    digitalWrite(_pin, _levelFor(on));
}

void Relay::forceOff() {
    _state = false;
    _onSince = 0;
    digitalWrite(_pin, _levelFor(false));
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
