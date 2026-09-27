#include "signer.h"
#include <string.h>
#include "bignum.h"
#include "ecdsa.h"
#include "memzero.h"
#include "secp256k1.h"
#include "sha3.h"

static int nibble(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

bool signer_hex_decode(const char *hex, uint8_t *out, size_t bytes)
{
    if (!hex || !out) return false;
    if (hex[0] == '0' && hex[1] == 'x') hex += 2;
    if (strlen(hex) != bytes * 2) return false;
    for (size_t i = 0; i < bytes; i++) {
        int hi = nibble(hex[2*i]), lo = nibble(hex[2*i+1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

void signer_hex_encode(const uint8_t *data, size_t bytes, char *out)
{
    static const char digits[] = "0123456789abcdef";
    out[0] = '0'; out[1] = 'x';
    for (size_t i = 0; i < bytes; i++) {
        out[2+2*i] = digits[data[i] >> 4];
        out[3+2*i] = digits[data[i] & 15];
    }
    out[2+2*bytes] = 0;
}

void signer_hash(const uint8_t *data, size_t bytes, uint8_t out[32])
{
    keccak_256(data, bytes, out);
}

static bool valid_key(const uint8_t key[32])
{
    bignum256 number;
    bn_read_be(key, &number);
    bool valid = !bn_is_zero(&number) && bn_is_less(&number, &secp256k1.order);
    memzero(&number, sizeof(number));
    return valid;
}

bool signer_address(const uint8_t key[32], uint8_t address[20])
{
    uint8_t pub[65], hash[32];
    if (!valid_key(key) || ecdsa_get_public_key65(&secp256k1, key, pub) != 0)
        return false;
    signer_hash(pub + 1, 64, hash);
    memcpy(address, hash + 12, 20);
    return true;
}

static void put_u64_be(uint8_t *out, uint64_t value)
{
    for (int i = 7; i >= 0; i--) { out[i] = value & 255; value >>= 8; }
}

static int ethereum_recovery(uint8_t recid, uint8_t sig[64])
{
    (void)sig;
    return recid < 2; // Chỉ chấp nhận v = 27 hoặc 28.
}

bool signer_event(const uint8_t key[32], const uint8_t device[20], uint8_t type,
                  uint64_t timestamp, uint64_t nonce, const uint8_t data_hash[32],
                  uint8_t packed[69], uint8_t message_hash[32],
                  uint8_t eth_signed[32], uint8_t sig[65])
{
    if (!valid_key(key) || type < 1 || type > 3 || nonce == 0) return false;
    memcpy(packed, device, 20); packed[20] = type;
    put_u64_be(packed + 21, timestamp);
    put_u64_be(packed + 29, nonce);
    memcpy(packed + 37, data_hash, 32);
    signer_hash(packed, 69, message_hash);
    static const char prefix[] = "\x19" "Ethereum Signed Message:\n32";
    uint8_t eip191[60];
    memcpy(eip191, prefix, 28); memcpy(eip191 + 28, message_hash, 32);
    signer_hash(eip191, sizeof(eip191), eth_signed);
    uint8_t recid = 0;
    if (ecdsa_sign_digest(&secp256k1, key, eth_signed, sig, &recid,
                          ethereum_recovery) != 0) return false;
    // Trezor chuẩn hóa low-s và đổi recovery bit tương ứng.
    sig[64] = recid + 27;
    return true;
}
