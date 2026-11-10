#ifndef HC_SR04_H
#define HC_SR04_H

#include <Arduino.h>

#define HCSR04_MAX_MUESTRAS 16

class HC_SR04 {
public:
  static constexpr float FUERA_DE_RANGO = -1.0f;
  static constexpr float ERROR = -2.0f;

  HC_SR04(uint8_t pinTrig, uint8_t pinEcho, uint8_t muestras = 5);

  void init();

  float getMm();

  float getCem();

private:
  uint8_t _pinTrig;
  uint8_t _pinEcho;
  uint8_t _muestras;
  float _offsetCm;
  float _ultimaCm;

  long _pulsar(); // envía pulso y devuelve duración en µs (0 = sin eco)
  float _pulsarACm();
};

#endif