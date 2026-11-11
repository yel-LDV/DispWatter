#include "PowerManager.h"

#include <esp_sleep.h>

void PowerManager::begin(uint8_t wakePin, bool activeLow) {
    _pin = wakePin;
    _activeLow = activeLow;

    pinMode(_pin, _activeLow ? INPUT_PULLUP : INPUT_PULLDOWN);

    switch (esp_sleep_get_wakeup_cause()) {
        case ESP_SLEEP_WAKEUP_TIMER:
            _wakeReason = WakeReason::Timer;
            break;
        case ESP_SLEEP_WAKEUP_EXT0:
        case ESP_SLEEP_WAKEUP_EXT1:
            _wakeReason = WakeReason::Button;
            break;
        case ESP_SLEEP_WAKEUP_UNDEFINED:
        default:
            _wakeReason = WakeReason::PowerOn;
            break;
    }
}

String PowerManager::wakeReasonString() const {
    switch (_wakeReason) {
        case WakeReason::Timer:
            return "timer";
        case WakeReason::Button:
            return "button";
        case WakeReason::PowerOn:
            return "power_on";
        default:
            return "unknown";
    }
}

void PowerManager::sleepForMinutes(uint16_t minutes) {
    if (minutes == 0) {
        minutes = 1;
    }

    Serial.printf("[POWER] Durmiendo %u minutos (despertar por GPIO%u)\n",
                  minutes, _pin);
    Serial.flush();

    esp_sleep_enable_timer_wakeup(
        static_cast<uint64_t>(minutes) * 60ULL * 1000000ULL);
    esp_sleep_enable_ext0_wakeup(
        static_cast<gpio_num_t>(_pin), _activeLow ? 0 : 1);
    esp_deep_sleep_start();
}
