#include <I2C.h>
#include <cstdint>

I2C::I2C(uint8_t adress) : _lcd(adress, LCD_COLS, LCD_ROWS) {}

void I2C::init() {
  Wire.begin();
  _lcd.init();
  _lcd.backlight();
  _lcd.clear();
}

void I2C::clean() { _lcd.clear(); }

void I2C::clean(uint8_t line) {
  if (line < 0 || line > 1)
    return;
  String text = "                ";
  _lcd.setCursor(0, line);
  _lcd.print(text);
}

void I2C::light(bool state) {
  if (state)
    _lcd.backlight();
  else
    _lcd.noBacklight;
}

void I2C::off() { _lcd.noBacklight(); }

void I2C::onn() { _lcd.backlight(); }

void I2C::print(uint8_t col, uint8_t line, const String &text) {
  if (col < 0 || col > LCD_COLS)
    return;
  if (line < 0 || line > LCD_ROWS)
    return;

  _lcd.setCursor(col, line);
  _lcd.print(text);
}
