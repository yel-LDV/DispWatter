#ifndef RELAY_H
#define RELAY_H

#include <Arduino.h>

/**
 * Relé con lógica activa-baja/alta y protecciones básicas.
 *
 * state() es el estado LÓGICO (true = bomba encendida), independiente de la
 * polaridad del módulo. La polaridad solo decide qué nivel se escribe en el pin.
 */
class Relay {
public:
    void begin(uint8_t pin, bool activeLow);

    /**
     * Cambia la polaridad en caliente (p. ej. tras leer /config.json).
     * Siempre deja el relé apagado con el nivel correcto de la nueva polaridad.
     */
    void setPolarity(bool activeLow);
    bool activeLow() const { return _activeLow; }

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
               unsigned long maxOnMs, unsigned long maxOfflineMs,
               unsigned long minOffMs, bool overflowProtection, float currentPercent, float maxPercent);

    void setMinOffMs(unsigned long ms) { _minOffMs = ms; }
    unsigned long getMinOffMs() const { return _minOffMs; }
    
    /**
     * Check if relay can be turned on (min off time protection).
     * @return true if the relay can be turned on.
     */
    bool canTurnOn(unsigned long now);

private:
    uint8_t _levelFor(bool on) const;

    uint8_t _pin = 0;
    bool _activeLow = true;
    bool _state = false;
    unsigned long _onSince = 0;
    unsigned long _offSince = 0;  // When relay was last turned off
    unsigned long _minOffMs = 180000;  // Default 3 minutes
};

#endif // RELAY_H
