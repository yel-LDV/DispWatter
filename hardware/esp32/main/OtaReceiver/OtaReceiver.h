#ifndef OTA_RECEIVER_H
#define OTA_RECEIVER_H

#include <Arduino.h>
#include <Update.h>

class OtaReceiver {
public:
    OtaReceiver();

    void begin();
    bool start(uint8_t* data, size_t len, size_t total);
    bool receiveChunk(uint8_t* data, size_t len);
    bool confirm();
    void rollback();
    bool isConfirming() const;
    void setConfirm();
    float progress() const;
    bool isActive() const;
    void reset();

private:
    size_t _totalSize;
    size_t _writtenSize;
    bool _confirming;
    bool _active;
};

#endif
