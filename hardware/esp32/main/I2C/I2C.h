#ifndef I2C_H
#define I2C_H

#include <Arduino.h>
#include <LiquidCrystal_I2C.h>
#include <Wire.h>

#define LCD_COLS 16
#define LCD_ROWS 2

class I2C {
public:
  I2C(uint8_t adress = 0x27);

  void init();

  void clean();

  void clean(uint8_t line);

  void light(bool state);

  void off();

  void onn();

  void print(uint8_t col, uint8_t line, const String &text);

private:
  LiquidCrystal_I2C _lcd;
};

#endif
