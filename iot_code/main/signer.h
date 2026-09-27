#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool signer_hex_decode(const char *hex, uint8_t *out, size_t bytes);
void signer_hex_encode(const uint8_t *data, size_t bytes, char *out);
void signer_hash(const uint8_t *data, size_t bytes, uint8_t out[32]);
bool signer_address(const uint8_t key[32], uint8_t address[20]);
bool signer_event(const uint8_t key[32], const uint8_t device[20], uint8_t type,
                  uint64_t timestamp, uint64_t nonce, const uint8_t data_hash[32],
                  uint8_t packed[69], uint8_t message_hash[32],
                  uint8_t eth_signed[32], uint8_t sig[65]);
