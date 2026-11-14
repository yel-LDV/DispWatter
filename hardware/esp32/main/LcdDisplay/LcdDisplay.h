#ifndef LCDDISPLAY_H
#define LCDDISPLAY_H

#include <Arduino.h>
#include <LiquidCrystal_I2C.h>

class LcdDisplay {
public:
    void begin(LiquidCrystal_I2C& lcd);
    
    // Config from backend
    void setConfig(const String& line0Format, const String& line1Format,
                   int scrollSpeed, int scrollPause,
                   const String& distanceUnit,
                   const String& customText0, const String& customText1,
                   bool showScroll0, bool showScroll1);
    
    // Update display with current data
    void refresh(float percent, float liters, float distanceMm, bool pumpOn);
    
    // Show claim code (6 digits) with countdown
    void showClaimCode(const String& code, int expiresIn);
    
    // Update claim countdown display
    void updateClaimCountdown();
    
    // Show standalone mode message
    void showStandalone();
    
    // Show pending claim message
    void showPendingClaim(const String& token);
    
    // Check if currently showing claim code
    bool isShowingClaimCode() const { return _showingClaim; }
    
    // Get the current claim code
    String getClaimCode() const { return _claimCode; }
    
    // Get claim code expiry time
    unsigned long getClaimExpiry() const { return _claimExpiry; }
    
    // Reset claim code display
    void resetClaim();
    
    // Get LCD reference
    LiquidCrystal_I2C& getLcd();

private:
    LiquidCrystal_I2C* _lcd = nullptr;
    
    // Config
    String _line0Format = "percent";
    String _line1Format = "liters";
    int _scrollSpeed = 400;
    int _scrollPause = 6;
    String _distanceUnit = "cm";
    String _customText0;
    String _customText1;
    bool _showScroll0 = true;
    bool _showScroll1 = true;
    
    // Scroll state
    String _line0Text;
    String _line1Text;
    int _scrollPos0 = 0;
    int _scrollPos1 = 0;
    unsigned long _lastScroll0 = 0;
    unsigned long _lastScroll1 = 0;
    unsigned long _scrollPauseStart0 = 0;
    unsigned long _scrollPauseStart1 = 0;
    bool _scrolling0 = false;
    bool _scrolling1 = false;
    bool _paused0 = false;
    bool _paused1 = false;
    
    // Claim code state
    bool _showingClaim = false;
    String _claimCode;
    unsigned long _claimExpiry = 0;
    unsigned long _claimFailUntil = 0;
    
    // Format distance based on unit
    String formatDistance(float distanceMm);
    
    // Scroll a line
    void scrollLine(int line, const String& text, int& pos, 
                    unsigned long& lastScroll, unsigned long& pauseStart,
                    bool& scrolling, bool& paused);
    
    // Build line text based on format
    String buildLine0(float percent, float liters, float distanceMm, bool pumpOn);
    String buildLine1(float percent, float liters, float distanceMm, bool pumpOn);
};

#endif // LCDDISPLAY_H
