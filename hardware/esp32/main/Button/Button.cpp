#include "Button.h"

Button::Button(uint8_t id, uint8_t pin)
    : _id(id), _pin(pin) {
}

void Button::begin() {
    pinMode(_pin, INPUT_PULLUP);
}

void Button::update() {
    unsigned long now = millis();

    // Si el botón está bloqueado por software, ignorar todo
    if (_locked) {
        _wasPressed = false;
        _wasReleased = false;
        return;
    }

    bool rawState = (digitalRead(_pin) == LOW);

    // Debounce: ignorar transiciones cercanas en el tiempo
    if (now - _lastTransitionMs < DEBOUNCE_MS) {
        _wasPressed = false;
        _wasReleased = false;
        return;
    }

    bool newState = rawState;

    if (newState != _pressed) {
        // Transición detectada
        _lastTransitionMs = now;

        if (newState) {
            // Se presionó
            _pressed = true;
            _wasPressed = true;
            _pressStartMs = now;
            if (_onPressCb) {
                _onPressCb(_id, _pressStartMs);
            }
        } else {
            // Se soltó
            _pressed = false;
            _wasReleased = true;
            unsigned long releasedMs = now;
            unsigned long durationMs = releasedMs - _pressStartMs;
            if (_onReleaseCb) {
                _onReleaseCb(_id, _pressStartMs, releasedMs, durationMs);
            }
            _pressStartMs = 0;
        }
    } else {
        _wasPressed = false;
        _wasReleased = false;
    }
}

void Button::onPress(ButtonPressCallback cb) {
    _onPressCb = cb;
}

void Button::onRelease(ButtonReleaseCallback cb) {
    _onReleaseCb = cb;
}

unsigned long Button::pressDuration() const {
    if (!_pressed || _pressStartMs == 0) {
        return 0;
    }
    return millis() - _pressStartMs;
}

void Button::setLocked(bool locked) {
    _locked = locked;
}

bool Button::toggleLock() {
    _locked = !_locked;
    return _locked;
}
