#include "Crypto.h"
#include <mbedtls/md.h>
#include <cstdio>

Crypto::Crypto() : _deviceId(""), _devicePass(""), _ownerId("UNCLAIMED"), _deviceKeyHash("") {}

Crypto::Crypto(const String &deviceId, const String &devicePass, const String &ownerId)
    : _deviceId(deviceId), _devicePass(devicePass), _ownerId(ownerId) {
    _computeDeviceKeyHash();
}

void Crypto::setCredentials(const String &deviceId, const String &devicePass, const String &ownerId) {
    _deviceId = deviceId;
    _devicePass = devicePass;
    _ownerId = ownerId;
    _computeDeviceKeyHash();
}

void Crypto::_computeDeviceKeyHash() {
    if (_deviceId.length() == 0 || _devicePass.length() == 0) {
        _deviceKeyHash = "";
        return;
    }
    // Hash base: SHA256(deviceId + ":" + devicePass)
    String raw = _deviceId + ":" + _devicePass;
    _deviceKeyHash = sha256(raw);
}

String Crypto::getDeviceKeyHash() const {
    return _deviceKeyHash;
}

String Crypto::sha256(const String &payload) {
    byte shaResult[32];
    mbedtls_md_context_t ctx;
    mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 0);
    mbedtls_md_starts(&ctx);
    mbedtls_md_update(&ctx, (const unsigned char *)payload.c_str(), payload.length());
    mbedtls_md_finish(&ctx, shaResult);
    mbedtls_md_free(&ctx);

    char hexBuffer[65];
    for (int i = 0; i < 32; i++) {
        sprintf(&hexBuffer[i * 2], "%02x", shaResult[i]);
    }
    hexBuffer[64] = '\0';
    return String(hexBuffer);
}

String Crypto::createAuthToken(uint32_t timestamp) const {
    if (_deviceKeyHash.length() == 0) return "";
    String raw = _deviceKeyHash + ":" + String(timestamp);
    return sha256(raw);
}

bool Crypto::verifyAuthToken(const String &receivedToken, uint32_t timestamp) const {
    String expected = createAuthToken(timestamp);
    return expected.equalsIgnoreCase(receivedToken);
}
