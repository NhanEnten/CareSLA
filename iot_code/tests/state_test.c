#include <assert.h>
#include <stdio.h>
#include "state.h"
#include "config.h"

static detector_state_t alarm(void)
{
    detector_state_t s = {0};
    state_step(&s, 0, true, true, false, false, false);
    state_step(&s, 10, true, false, true, false, false);
    state_step(&s, 10 + IMMOBILE_MS, true, false, true, false, false);
    assert(s.state == ALARM_WINDOW);
    return s;
}
int main(void)
{
    detector_state_t s = alarm();
    assert(state_step(&s, s.alarm_at+9999, true, false, true, true, false) == 3);
    // Queue đầy không làm mất CANCEL: lặp lại cho đến khi nhận vào queue.
    assert(state_step(&s, s.alarm_at+11000, true, false, true, false, false) == 3);
    state_event_queued(&s); assert(s.state == IDLE);
    s = alarm();
    assert(state_step(&s, s.alarm_at+10000, true, false, true, true, false) == 1);
    state_event_queued(&s); assert(s.state == REPORTED);
    assert(state_step(&s, 20000, true, false, true, true, false) == 0);
    assert(state_step(&s, 21000, true, false, true, false, true) == 2);
    state_event_queued(&s); assert(s.state == IDLE);
    s = (detector_state_t){0};
    state_step(&s, 0, true, true, false, false, false);
    state_step(&s, 10, false, false, true, false, false);
    assert(s.state == IDLE);
    button_state_t b = {0};
    bool short_press, long_press;
    button_step(&b, 0, true, &short_press, &long_press);
    button_step(&b, 10, false, &short_press, &long_press);
    button_step(&b, 40, false, &short_press, &long_press);
    assert(!short_press && !long_press); // Dội phím không thành một lần nhấn.
    button_step(&b, 100, true, &short_press, &long_press);
    button_step(&b, 130, true, &short_press, &long_press);
    button_step(&b, 3129, true, &short_press, &long_press);
    assert(!long_press);
    button_step(&b, 3130, true, &short_press, &long_press);
    assert(long_press && !short_press);
    button_step(&b, 4000, true, &short_press, &long_press);
    assert(!long_press);
    button_step(&b, 4010, false, &short_press, &long_press);
    button_step(&b, 4040, false, &short_press, &long_press);
    assert(!short_press && !long_press);
    button_step(&b, 5000, true, &short_press, &long_press);
    button_step(&b, 5030, true, &short_press, &long_press);
    button_step(&b, 5100, false, &short_press, &long_press);
    button_step(&b, 5130, false, &short_press, &long_press);
    assert(short_press && !long_press);
    puts("PASS: cancel boundary, queue retry, FALL/ARRIVAL, sensor loss");
}
