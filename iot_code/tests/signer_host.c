// Harness PC: khóa test chỉ đọc từ stdin, không nhúng vào firmware.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "signer.h"
#include "rand.h"
#include <windows.h>
#include <bcrypt.h>

void random_buffer(uint8_t *buffer, size_t length)
{
    if (BCryptGenRandom(NULL, buffer, (ULONG)length,
                       BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) abort();
}

static void print_hex(uint8_t *data, size_t length)
{
    char text[141];
    signer_hex_encode(data, length, text);
    puts(text);
}

int main(void)
{
    char key_text[67], hash_text[67];
    unsigned type;
    unsigned long long ts, nonce;
    uint8_t key[32], hash[32], device[20], packed[69], msg[32], eth[32], sig[65];
    if (scanf("%66s %u %llu %llu %66s", key_text, &type, &ts, &nonce, hash_text) != 5)
        return 1;
    if (!signer_hex_decode(key_text, key, 32) ||
        !signer_hex_decode(hash_text, hash, 32) || !signer_address(key, device)) return 2;
    if (!signer_event(key, device, type, ts, nonce, hash, packed, msg, eth, sig)) return 3;
    print_hex(device, 20); print_hex(packed, 69); print_hex(msg, 32);
    print_hex(eth, 32); print_hex(sig, 65);
    return 0;
}
