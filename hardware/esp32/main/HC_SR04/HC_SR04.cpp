#include "HC_SR04.h"

HC_SR04::HC_SR04(uint8_t pinTrig, uint8_t pinEcho, uint8_t muestras) {
  _pinTrig = pinTrig;
  _pinEcho = pinEcho;
  _muestras =
      (muestras == 0)
          ? 1
          : (muestras > HCSR04_MAX_MUESTRAS ? HCSR04_MAX_MUESTRAS : muestras);
  _offsetCm = 0.0f;
  _ultimaCm = FUERA_DE_RANGO;
}

void HC_SR04::init() {
  pinMode(_pinTrig, OUTPUT);
  pinMode(_pinEcho, INPUT);
  digitalWrite(_pinTrig, LOW);
  _ultimaCm = FUERA_DE_RANGO;
}

long HC_SR04::_pulsar() {
  digitalWrite(_pinTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(_pinTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(_pinTrig, LOW);
  return pulseIn(_pinEcho, HIGH, 30000); // timeout 30 ms ≈ 5 m
}

float HC_SR04::_pulsarACm() {
  long d = _pulsar();
  if (d == 0)
    return FUERA_DE_RANGO;
  return (d * 0.034f / 2.0f) + _offsetCm;
}

float HC_SR04::getCem() {
  float muestras[HCSR04_MAX_MUESTRAS];
  int validas = 0;

  for (int i = 0; i < _muestras; i++) {
    float cm = _pulsarACm();
    if (cm > 0)
      muestras[validas++] = cm;
    delay(10);
  }

  if (validas == 0) {
    _ultimaCm = FUERA_DE_RANGO;
    return _ultimaCm;
  }

  for (int i = 0; i < validas - 1; i++) {
    for (int j = i + 1; j < validas; j++) {
      if (muestras[j] < muestras[i]) {
        float tmp = muestras[i];
        muestras[i] = muestras[j];
        muestras[j] = tmp;
      }
    }
  }

  _ultimaCm = muestras[validas / 2]; // mediana
  return _ultimaCm;
}

float HC_SR04::getMm() {
  float cm = getCem();
  return (cm < 0) ? cm : cm * 10.0f;
}