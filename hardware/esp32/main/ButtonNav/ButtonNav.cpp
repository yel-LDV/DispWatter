#include "ButtonNav.h"

ButtonNav::ButtonNav()
    : _mode(BTN_MODE_NORMAL), _onPress(nullptr), _onLongPress(nullptr), _onPowerPress(nullptr),
      _upState(false), _downState(false), _leftState(false), _rightState(false), _okState(false), _powerState(false),
      _upPressed(false), _downPressed(false), _leftPressed(false), _rightPressed(false),
      _okPressed(false), _powerPressed(false), _okLongPressed(false),
      _okPressTime(0), _lastUpTime(0), _lastDownTime(0), _lastLeftTime(0),
      _lastRightTime(0), _lastOkTime(0), _lastPowerTime(0) {
}

void ButtonNav::begin(int upPin, int downPin, int leftPin, int rightPin, int okPin, int powerPin) {
    _upPin = upPin;
    _downPin = downPin;
    _leftPin = leftPin;
    _rightPin = rightPin;
    _okPin = okPin;
    _powerPin = powerPin;

    pinMode(_upPin, INPUT_PULLUP);
    pinMode(_downPin, INPUT_PULLUP);
    pinMode(_leftPin, INPUT_PULLUP);
    pinMode(_rightPin, INPUT_PULLUP);
    pinMode(_okPin, INPUT_PULLUP);
    pinMode(_powerPin, INPUT_PULLUP);
}

void ButtonNav::update() {
    unsigned long now = millis();

    _upState = readButton(_upPin);
    _downState = readButton(_downPin);
    _leftState = readButton(_leftPin);
    _rightState = readButton(_rightPin);
    _okState = readButton(_okPin);
    _powerState = readButton(_powerPin);

    if (_upState && (now - _lastUpTime >= DEBOUNCE_MS)) {
        _upPressed = true;
        _lastUpTime = now;
    }
    if (_downState && (now - _lastDownTime >= DEBOUNCE_MS)) {
        _downPressed = true;
        _lastDownTime = now;
    }
    if (_leftState && (now - _lastLeftTime >= DEBOUNCE_MS)) {
        _leftPressed = true;
        _lastLeftTime = now;
    }
    if (_rightState && (now - _lastRightTime >= DEBOUNCE_MS)) {
        _rightPressed = true;
        _lastRightTime = now;
    }
    if (_powerState && (now - _lastPowerTime >= DEBOUNCE_MS)) {
        _powerPressed = true;
        _lastPowerTime = now;
        if (_onPowerPress) _onPowerPress();
    }

    if (_okState && (now - _lastOkTime >= DEBOUNCE_MS)) {
        if (_okPressTime == 0) {
            _okPressTime = now;
        } else if (now - _okPressTime >= LONG_PRESS_MS) {
            _okLongPressed = true;
            _okPressed = true;
            _okPressTime = 0;
            _lastOkTime = now;
            if (_onLongPress) _onLongPress();
        }
    } else if (!_okState && _okPressTime > 0) {
        if (_onPress) _onPress();
        _okPressTime = 0;
    }

    checkModeSwitch();

    _upPressed = false;
    _downPressed = false;
    _leftPressed = false;
    _rightPressed = false;
    _okPressed = false;
    _powerPressed = false;
    _okLongPressed = false;
}

void ButtonNav::onPress(ButtonCallback callback) {
    _onPress = callback;
}

void ButtonNav::onLongPress(ButtonCallback callback) {
    _onLongPress = callback;
}

void ButtonNav::onPowerPress(ButtonCallback callback) {
    _onPowerPress = callback;
}

ButtonMode ButtonNav::getMode() const {
    return _mode;
}

bool ButtonNav::isUpPressed() const { return _upState; }
bool ButtonNav::isDownPressed() const { return _downState; }
bool ButtonNav::isLeftPressed() const { return _leftState; }
bool ButtonNav::isRightPressed() const { return _rightState; }
bool ButtonNav::isOkPressed() const { return _okState; }
bool ButtonNav::isPowerPressed() const { return _powerState; }
bool ButtonNav::wasUpPressed() const { return _upPressed; }
bool ButtonNav::wasDownPressed() const { return _downPressed; }
bool ButtonNav::wasLeftPressed() const { return _leftPressed; }
bool ButtonNav::wasRightPressed() const { return _rightPressed; }
bool ButtonNav::wasOkPressed() const { return _okPressed; }
bool ButtonNav::wasOkLongPressed() const { return _okLongPressed; }
bool ButtonNav::wasPowerPressed() const { return _powerPressed; }

bool ButtonNav::readButton(int pin) {
    return digitalRead(pin) == LOW;
}

void ButtonNav::checkModeSwitch() {
    // Mode switching is handled via onLongPress callback in main.cpp
    // to avoid false triggers from floating pins when buttons are not connected.
    // Only switch to NORMAL mode via OK+Left (explicit exit from special modes).
    if (_okState && _leftState && !_upState && !_downState) {
        _mode = BTN_MODE_NORMAL;
    }
}
