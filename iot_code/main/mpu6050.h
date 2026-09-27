#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef struct { int16_t axis[6]; int64_t at_us; } imu_sample_t;
esp_err_t mpu6050_init(void);
esp_err_t mpu6050_read(imu_sample_t *sample);
float mpu6050_accel_scale(void);
float mpu6050_gyro_scale(void);
