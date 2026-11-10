#ifndef CRYPTO_H
#define CRYPTO_H

#include <Arduino.h>

class Crypto {
public:
    Crypto();
    Crypto(const String &deviceId, const String &devicePass, const String &ownerId = "UNCLAIMED");

    void setCredentials(const String &deviceId, const String &devicePass, const String &ownerId = "UNCLAIMED");

    // Hashea un string cualquiera en formato hexadecimal
    static String sha256(const String &payload);

    // Obtiene el hash persistente de las credenciales del dispositivo (ID + Contraseña)
    String getDeviceKeyHash() const;

    // Genera un token de autenticación dinámico con timestamp: SHA256(DeviceKeyHash + ":" + timestamp)
    String createAuthToken(uint32_t timestamp) const;

    // Verifica si un token recibido coincide con las credenciales esperadas para un timestamp dado
    bool verifyAuthToken(const String &receivedToken, uint32_t timestamp) const;

    String getDeviceId() const { return _deviceId; }
    String getOwnerId() const { return _ownerId; }
    void setOwnerId(const String &ownerId) { _ownerId = ownerId; }

private:
    String _deviceId;
    String _devicePass;
    String _ownerId;
    String _deviceKeyHash;

    void _computeDeviceKeyHash();
};

#endif // CRYPTO_H
