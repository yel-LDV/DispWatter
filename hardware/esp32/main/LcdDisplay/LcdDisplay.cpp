#include "LcdDisplay.h"

#define LCD_COLS 16

void LcdDisplay::begin(LiquidCrystal_I2C& lcd) {
    _lcd = &lcd;
    _lcd->init();
    _lcd->backlight();
    _lcd->clear();
}

void LcdDisplay::setConfig(const String& line0Format, const String& line1Format,
                           int scrollSpeed, int scrollPause,
                           const String& distanceUnit,
                           const String& customText0, const String& customText1,
                           bool showScroll0, bool showScroll1) {
    if (line0Format.length() > 0) _line0Format = line0Format;
    if (line1Format.length() > 0) _line1Format = line1Format;
    if (scrollSpeed > 0) _scrollSpeed = scrollSpeed;
    if (scrollPause > 0) _scrollPause = scrollPause;
    if (distanceUnit.length() > 0) _distanceUnit = distanceUnit;
    _customText0 = customText0;
    _customText1 = customText1;
    _showScroll0 = showScroll0;
    _showScroll1 = showScroll1;
    
    // Reset scroll state
    _scrollPos0 = 0;
    _scrollPos1 = 0;
    _scrolling0 = false;
    _scrolling1 = false;
    _paused0 = false;
    _paused1 = false;
}

void LcdDisplay::refresh(float percent, float liters, float distanceMm, bool pumpOn) {
    // Don't refresh if showing claim code
    if (_showingClaim) {
        if (millis() > _claimExpiry) {
            resetClaim();
        } else {
            return;
        }
    }
    
    _line0Text = buildLine0(percent, liters, distanceMm, pumpOn);
    _line1Text = buildLine1(percent, liters, distanceMm, pumpOn);
    
    scrollLine(0, _line0Text, _scrollPos0, _lastScroll0, _scrollPauseStart0, _scrolling0, _paused0);
    scrollLine(1, _line1Text, _scrollPos1, _lastScroll1, _scrollPauseStart1, _scrolling1, _paused1);
}

void LcdDisplay::showClaimCode(const String& code) {
    _showingClaim = true;
    _claimCode = code;
    _claimExpiry = millis() + 20000; // 20 seconds
    
    _lcd->clear();
    _lcd->setCursor(0, 0);
    _lcd->print("CODIGO CLAIM:");
    _lcd->setCursor(4, 1);
    _lcd->print(code);
    _lcd->print("   ");
}

void LcdDisplay::showStandalone() {
    _lcd->clear();
    _lcd->setCursor(0, 0);
    _lcd->print("MODO STANDALONE");
    _lcd->setCursor(0, 1);
    _lcd->print("Sin conexion");
}

void LcdDisplay::showPendingClaim(const String& token) {
    _lcd->clear();
    _lcd->setCursor(0, 0);
    _lcd->print("PENDING CLAIM");
    _lcd->setCursor(0, 1);
    // Show first 8 chars of token
    String shortToken = token.substring(0, min(token.length(), (size_t)8));
    _lcd->print(shortToken);
}

void LcdDisplay::resetClaim() {
    _showingClaim = false;
    _claimCode = "";
    _claimExpiry = 0;
}

LiquidCrystal_I2C& LcdDisplay::getLcd() {
    return *_lcd;
}

String LcdDisplay::formatDistance(float distanceMm) {
    if (_distanceUnit == "cm") {
        return String(distanceMm / 10.0, 1) + "cm";
    } else if (_distanceUnit == "m") {
        return String(distanceMm / 1000.0, 2) + "m";
    }
    return String((int)distanceMm) + "mm";
}

void LcdDisplay::scrollLine(int line, const String& text, int& pos,
                            unsigned long& lastScroll, unsigned long& pauseStart,
                            bool& scrolling, bool& paused) {
    if (text.length() <= LCD_COLS) {
        // No scrolling needed
        _lcd->setCursor(0, line);
        _lcd->print(text);
        // Clear remaining
        for (int i = text.length(); i < LCD_COLS; i++) {
            _lcd->print(" ");
        }
        scrolling = false;
        paused = false;
        pos = 0;
        return;
    }
    
    // Check if we should scroll
    if (!scrolling) {
        scrolling = true;
        pos = 0;
        lastScroll = millis();
        paused = false;
    }
    
    unsigned long now = millis();
    
    // Check if we're in pause at the end
    if (paused) {
        if (now - pauseStart >= (unsigned long)(_scrollPause * 1000)) {
            // Reset scroll
            paused = false;
            pos = 0;
            lastScroll = now;
        } else {
            return; // Still pausing
        }
    }
    
    // Check if it's time to scroll
    if (now - lastScroll < (unsigned long)_scrollSpeed) {
        return;
    }
    lastScroll = now;
    
    // Move position
    pos++;
    
    // Check if we've scrolled past the text
    if (pos > (int)text.length()) {
        // Start pause at end
        paused = true;
        pauseStart = now;
        return;
    }
    
    // Display the substring
    _lcd->setCursor(0, line);
    String display = text.substring(pos);
    _lcd->print(display);
    // Clear remaining
    for (int i = display.length(); i < LCD_COLS; i++) {
        _lcd->print(" ");
    }
}

String LcdDisplay::buildLine0(float percent, float liters, float distanceMm, bool pumpOn) {
    if (_line0Format == "percent") {
        return String((int)percent) + "% Agua";
    } else if (_line0Format == "liters") {
        return String(liters, 1) + "L";
    } else if (_line0Format == "distance") {
        return formatDistance(distanceMm);
    } else if (_line0Format == "pump_status") {
        return pumpOn ? "Bomba: ON" : "Bomba: OFF";
    } else if (_line0Format == "custom") {
        return _customText0;
    }
    return "";
}

String LcdDisplay::buildLine1(float percent, float liters, float distanceMm, bool pumpOn) {
    if (_line1Format == "percent") {
        return String((int)percent) + "% Agua";
    } else if (_line1Format == "liters") {
        return String(liters, 1) + "L";
    } else if (_line1Format == "distance") {
        return formatDistance(distanceMm);
    } else if (_line1Format == "pump_status") {
        return pumpOn ? "Bomba: ON" : "Bomba: OFF";
    } else if (_line1Format == "custom") {
        return _customText1;
    }
    return "";
}
