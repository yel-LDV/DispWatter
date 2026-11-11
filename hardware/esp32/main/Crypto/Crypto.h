#ifndef CRYPTO_H
#define CRYPTO_H

#include <Arduino.h>

/**
 * Utilidades criptográficas del dispositivo.
 *
 * El ESP32 no guarda la contraseña de vinculación: solo el hash
 * SHA256(device_id:claim_secret). La autenticación usa HMAC-SHA256
 * con un nonce enviado por el backend.
 */
class Crypto {
public:
    Crypto();

    void setKeyHash(const String& keyHash);
    const String& getKeyHash() const { return _keyHash; }
    bool hasKey() const { return _keyHash.length() == 64; }

    static String sha256(const String& payload);
    static String hmacSha256Hex(const String& key, const String& message);

    String createAuthProof(const String& nonce) const;

private:
    String _keyHash;
};

#endif // CRYPTO_H
