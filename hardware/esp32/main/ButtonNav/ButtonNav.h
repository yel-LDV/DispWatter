#ifndef BUTTON_NAV_H
#define BUTTON_NAV_H

#include <Arduino.h>

typedef enum {
    BTN_MODE_NORMAL,
    BTN_MODE_OTA,
    BTN_MODE_DOWNGRADE,
    BTN_MODE_DEV
} ButtonMode;

typedef void (*ButtonCallback)();

class ButtonNav {
public:
    ButtonNav();

    void begin(int upPin, int downPin, int leftPin, int rightPin, int okPin, int powerPin);
    void update();
    void onPress(ButtonCallback callback);
    void onLongPress(ButtonCallback callback);
    void onPowerPress(ButtonCallback callback);
    ButtonMode getMode() const;
    bool isUpPressed() const;
    bool isDownPressed() const;
    bool isLeftPressed() const;
    bool isRightPressed() const;
    bool isOkPressed() const;
    bool isPowerPressed() const;
    bool wasUpPressed() const;
    bool wasDownPressed() const;
    bool wasLeftPressed() const;
    bool wasRightPressed() const;
    bool wasOkPressed() const;
    bool wasOkLongPressed() const;
    bool wasPowerPressed() const;

private:
    int _upPin;
    int _downPin;
    int _leftPin;
    int _rightPin;
    int _okPin;
    int _powerPin;
    ButtonMode _mode;
    ButtonCallback _onPress;
    ButtonCallback _onLongPress;
    ButtonCallback _onPowerPress;

    bool _upState;
    bool _downState;
    bool _leftState;
    bool _rightState;
    bool _okState;
    bool _powerState;
    bool _upPressed;
    bool _downPressed;
    bool _leftPressed;
    bool _rightPressed;
    bool _okPressed;
    bool _powerPressed;
    bool _okLongPressed;
    unsigned long _okPressTime;
    unsigned long _lastUpTime;
    unsigned long _lastDownTime;
    unsigned long _lastLeftTime;
    unsigned long _lastRightTime;
    unsigned long _lastOkTime;
    unsigned long _lastPowerTime;

    static const unsigned long DEBOUNCE_MS = 50;
    static const unsigned long LONG_PRESS_MS = 1500;
    static const unsigned long MODE_SWITCH_MS = 2000;

    bool readButton(int pin);
    void checkModeSwitch();
};

#endif
