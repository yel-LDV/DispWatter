#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <Arduino.h>

enum class WakeReason {
    Unknown,
    Timer,
    Button,
    PowerOn
};

/**
 * Deep sleep con despertar por temporizador y por botón físico (RTC GPIO).
 */
class PowerManager {
public:
    void begin(uint8_t wakePin, bool activeLow);

    WakeReason lastWakeReason() const { return _wakeReason; }
    String wakeReasonString() const;

    void sleepForMinutes(uint16_t minutes);

private:
    uint8_t _pin = 33;
    bool _activeLow = true;
    WakeReason _wakeReason = WakeReason::Unknown;
};

#endif // POWER_MANAGER_H
