#pragma once
#include <stdint.h>
#include <math.h>

// Physical KFall units: accel g; gyro deg/s. Input [1,50,6].
static const float kAiMean[6] = {0.021578215062618256f, -0.72014486789703369f, -0.012925770133733749f, -0.79334110021591187f, 7.5048747062683105f, -0.050110448151826859f};
static const float kAiStd[6] = {0.34529754519462585f, 0.50911349058151245f, 0.50989824533462524f, 36.189029693603516f, 43.401523590087891f, 21.957178115844727f};
static inline int8_t ai_quantize_sample(float physical_value, int channel) {
    float u = (physical_value - kAiMean[channel]) / kAiStd[channel];
    if (u > 4.0f) u = 4.0f;
    if (u < -4.0f) u = -4.0f;
    // Default FE_TONEAREST: nearbyintf agrees with Python np.rint for ties.
    int q = (int)nearbyintf(u / 0.0313725508749485f) - 1;
    if (q > 127) q = 127;
    if (q < -128) q = -128;
    return (int8_t)q;
}
static inline float ai_logit_margin(const int8_t output[2]) {
    return ((int)output[1] - (int)output[0]) * 0.102272629737854f;
}
static inline int ai_fall_candidate(const int8_t output[2]) {
    return ai_logit_margin(output) >= 0.8472978603872037f;
}
// Require two consecutive candidates; reset streak to zero on a negative window.
