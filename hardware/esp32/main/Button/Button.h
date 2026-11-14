#ifndef BUTTON_H
#define BUTTON_H

#include <Arduino.h>
#include <functional>

/**
 * Callback invocado cuando el botón se presiona (transición HIGH -> LOW con debounce).
 * @param id        ID único del botón.
 * @param pressedMs Marca de tiempo (millis()) cuando se detectó la presión.
 */
typedef std::function<void(uint8_t id, unsigned long pressedMs)> ButtonPressCallback;

/**
 * Callback invocado cuando el botón se suelta (transición LOW -> HIGH con debounce).
 * @param id        ID único del botón.
 * @param pressedMs Marca de tiempo cuando se presionó.
 * @param releasedMs Marca de tiempo cuando se soltó.
 * @param durationMs Duración de la presión en milisegundos.
 */
typedef std::function<void(uint8_t id, unsigned long pressedMs, unsigned long releasedMs, unsigned long durationMs)> ButtonReleaseCallback;

/**
 * Botón individual con debounce, bloqueo remoto y callbacks de press/release.
 *
 * Cada botón se identifica con un ID único que se pasa a los callbacks,
 * similar a los listeners de plugins de Minecraft.
 *
 * El botón se puede bloquear/desbloquear en caliente (desde el panel vía WebSocket)
 * para deshabilitar su funcionamiento sin desconectarlo físicamente.
 */
class Button {
public:
    /**
     * Construye un botón.
     * @param id   ID único del botón (0-255).
     * @param pin  GPIO al que está conectado.
     */
    Button(uint8_t id, uint8_t pin);

    /**
     * Inicializa el pin como INPUT_PULLUP.
     * El botón se conecta a GND al presionarse (activo en LOW).
     */
    void begin();

    /**
     * Actualiza el estado del botón. Llamar desde loop() frecuentemente.
     */
    void update();

    /**
     * Registra un callback que se ejecuta cuando el botón se presiona.
     */
    void onPress(ButtonPressCallback cb);

    /**
     * Registra un callback que se ejecuta cuando el botón se suelta.
     */
    void onRelease(ButtonReleaseCallback cb);

    // -- Estado de consulta --

    /** @return ID único del botón. */
    uint8_t getId() const { return _id; }

    /** @return GPIO asignado. */
    uint8_t getPin() const { return _pin; }

    /** @return true si el botón está presionado ahora (después de debounce). */
    bool isPressed() const { return _pressed; }

    /** @return true si el botón se presionó en este ciclo de update(). */
    bool wasPressed() const { return _wasPressed; }

    /** @return true si el botón se soltó en este ciclo de update(). */
    bool wasReleased() const { return _wasReleased; }

    /**
     * @return Duración en ms desde que se presionó (0 si no está presionado).
     * Útil para detectar long press personalizado.
     */
    unsigned long pressDuration() const;

    // -- Bloqueo remoto --

    /**
     * Bloquea el botón: ignora cualquier presión física.
     * El panel puede llamar esto para deshabilitar un botón.
     */
    void setLocked(bool locked);

    /** @return true si el botón está bloqueado por software. */
    bool isLocked() const { return _locked; }

    /**
     * Cambia el estado de bloqueo y devuelve el nuevo estado.
     * @return true si quedó bloqueado, false si quedó desbloqueado.
     */
    bool toggleLock();

private:
    uint8_t _id;
    uint8_t _pin;

    bool _locked = false;

    // Estado actual (después de debounce)
    bool _pressed = false;

    // Eventos de un solo ciclo
    bool _wasPressed = false;
    bool _wasReleased = false;

    // Timing
    unsigned long _pressStartMs = 0;
    unsigned long _lastTransitionMs = 0;

    // Debounce
    static const unsigned long DEBOUNCE_MS = 50;

    // Callbacks
    ButtonPressCallback _onPressCb;
    ButtonReleaseCallback _onReleaseCb;
};

#endif // BUTTON_H
