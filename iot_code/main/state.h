#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef enum { IDLE, CANDIDATE, IMMOBILITY_CHECK, ALARM_WINDOW, REPORTED } state_t;
typedef struct {
    state_t state;
    int64_t candidate_at, still_at, alarm_at;
    uint8_t pending;
} detector_state_t;
// Trả event cần gửi: 0=không, 1=FALL, 2=ARRIVAL, 3=CANCEL.
uint8_t state_step(detector_state_t *s, int64_t now_ms, bool valid_sample,
                   bool impact, bool still, bool short_press, bool long_press);
void state_event_queued(detector_state_t *s);

typedef struct {
    bool raw, stable, long_sent;
    int64_t changed_at, pressed_at;
} button_state_t;
void button_step(button_state_t *s, int64_t now_ms, bool pressed,
                 bool *short_press, bool *long_press);
