#ifndef RELAY_H
#define RELAY_H

#include <Arduino.h>

/**
 * Relé con lógica activa-baja/alta y protecciones básicas.
 */
class Relay {
public:
    void begin(uint8_t pin, bool activeLow);
    void set(bool on);
    bool state() const { return _state; }
    void forceOff();

    /**
     * Apaga el relé si lleva demasiado tiempo encendido o si el backend
     * lleva demasiado tiempo sin autenticarse.
     *
     * @return true si el guard actuó (apagó el relé).
     */
    bool guard(unsigned long now, unsigned long lastAuthMs,
               unsigned long maxOnMs, unsigned long maxOfflineMs);

private:
    uint8_t _pin = 0;
    bool _activeLow = true;
    bool _state = false;
    unsigned long _onSince = 0;
};

#endif // RELAY_H
