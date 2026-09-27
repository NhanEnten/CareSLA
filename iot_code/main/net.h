#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t net_start(const char *device);
bool net_time_ready(void);
// Một task gọi hàm này: giữ payload đến khi broker ACK, tự reconnect.
void net_send_reliable(const char *suffix, const char *json);
// Gửi QoS 0 (fire-and-forget), dùng cho stream, không block.
void net_publish_once(const char *suffix, const char *json);
