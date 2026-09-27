#include "state.h"
#include "config.h"

uint8_t state_step(detector_state_t *s, int64_t now, bool valid, bool impact,
                   bool still, bool short_press, bool long_press)
{
    if (s->pending) return s->pending;
    switch (s->state) {
    case IDLE:
        if (valid && impact) { s->state = CANDIDATE; s->candidate_at = now; }
        break;
    case CANDIDATE:
    case IMMOBILITY_CHECK:
        if (!valid || now - s->candidate_at > CANDIDATE_TIMEOUT_MS) {
            s->state = IDLE;
        } else if (!still) {
            s->state = CANDIDATE;
        } else if (s->state == CANDIDATE) {
            s->state = IMMOBILITY_CHECK; s->still_at = now;
        } else if (now - s->still_at >= IMMOBILE_MS) {
            s->state = ALARM_WINDOW; s->alarm_at = now;
        }
        break;
    case ALARM_WINDOW:
        // Hết 10 giây trước: không cho CANCEL xóa FALL đang chờ gửi.
        if (now - s->alarm_at >= CANCEL_WINDOW_MS) s->pending = 1;
        else if (short_press) s->pending = 3;
        break;
    case REPORTED:
        if (long_press) s->pending = 2;
        break;
    }
    return s->pending;
}

void state_event_queued(detector_state_t *s)
{
    if (s->pending == 1) s->state = REPORTED;
    else if (s->pending == 2 || s->pending == 3) s->state = IDLE;
    s->pending = 0;
}

void button_step(button_state_t *s, int64_t now, bool pressed,
                 bool *short_press, bool *long_press)
{
    *short_press = false;
    *long_press = false;
    if (pressed != s->raw) { s->raw = pressed; s->changed_at = now; }
    if (s->stable != s->raw && now - s->changed_at >= DEBOUNCE_MS) {
        s->stable = s->raw;
        if (s->stable) { s->pressed_at = now; s->long_sent = false; }
        else if (!s->long_sent && now - s->pressed_at < ARRIVAL_HOLD_MS) *short_press = true;
    }
    if (s->stable && s->raw && !s->long_sent && now - s->pressed_at >= ARRIVAL_HOLD_MS) {
        s->long_sent = true;
        *long_press = true;
    }
}
