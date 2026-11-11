#include "Crypto.h"

#include <mbedtls/md.h>
#include <cstdio>

namespace {
String toHex(const unsigned char* data, size_t length) {
    char buffer[65];
    if (length > 32) {
        length = 32;
    }
    for (size_t i = 0; i < length; ++i) {
        sprintf(&buffer[i * 2], "%02x", data[i]);
    }
    buffer[length * 2] = '\0';
    return String(buffer);
}
} // namespace

Crypto::Crypto() : _keyHash("") {}

void Crypto::setKeyHash(const String& keyHash) {
    _keyHash = keyHash;
}

String Crypto::sha256(const String& payload) {
    unsigned char result[32];
    mbedtls_md_context_t ctx;
    const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

    mbedtls_md_init(&ctx);
    if (mbedtls_md_setup(&ctx, info, 0) != 0) {
        mbedtls_md_free(&ctx);
        return String("");
    }
    mbedtls_md_starts(&ctx);
    mbedtls_md_update(&ctx,
                      reinterpret_cast<const unsigned char*>(payload.c_str()),
                      payload.length());
    mbedtls_md_finish(&ctx, result);
    mbedtls_md_free(&ctx);

    return toHex(result, 32);
}

String Crypto::hmacSha256Hex(const String& key, const String& message) {
    unsigned char result[32];
    mbedtls_md_context_t ctx;
    const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

    mbedtls_md_init(&ctx);
    if (mbedtls_md_setup(&ctx, info, 1) != 0) {
        mbedtls_md_free(&ctx);
        return String("");
    }
    mbedtls_md_hmac_starts(
        &ctx, reinterpret_cast<const unsigned char*>(key.c_str()), key.length());
    mbedtls_md_hmac_update(
        &ctx, reinterpret_cast<const unsigned char*>(message.c_str()),
        message.length());
    mbedtls_md_hmac_finish(&ctx, result);
    mbedtls_md_free(&ctx);

    return toHex(result, 32);
}

String Crypto::createAuthProof(const String& nonce) const {
    if (!hasKey() || nonce.length() == 0) {
        return String("");
    }
    return hmacSha256Hex(_keyHash, nonce);
}
