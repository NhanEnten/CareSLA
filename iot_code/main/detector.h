#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool inference_ran;
    bool fall_candidate;
    float fall_probability;
    uint32_t inference_us;
} ai_inference_result_t;

#ifdef __cplusplus
extern "C" {
#endif

bool ai_detector_init(void);
void ai_detector_start(void);
void ai_detector_reset(void);
bool ai_detector_add_sample(const float sample[6], ai_inference_result_t *result);

#ifdef __cplusplus
}
#endif