#include "mpu6050.h"
#include "config.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static i2c_master_dev_handle_t sensor;

static esp_err_t write_reg(uint8_t reg, uint8_t value)
{
    uint8_t data[] = {reg, value};
    return i2c_master_transmit(sensor, data, sizeof(data), 50);
}

esp_err_t mpu6050_init(void)
{
    i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0, .sda_io_num = PIN_SDA, .scl_io_num = PIN_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    esp_err_t err = i2c_new_master_bus(&bus_config, &bus);
    if (err != ESP_OK) return err;
    i2c_device_config_t device = {.dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = MPU_ADDRESS, .scl_speed_hz = 100000};
    err = i2c_master_bus_add_device(bus, &device, &sensor);
    if (err != ESP_OK) return err;
    uint8_t reg = 0x75, who = 0;
    err = i2c_master_transmit_receive(sensor, &reg, 1, &who, 1, 50);
    if (err != ESP_OK) return err;
    if (who != 0x68) return ESP_ERR_NOT_FOUND;
    if ((err = write_reg(0x6B, 0x80)) != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(100));
    if ((err = write_reg(0x6B, 0x01)) != ESP_OK) return err;
    if ((err = write_reg(0x1A, 3)) != ESP_OK) return err; // DLPF, sample clock 1 kHz
    if ((err = write_reg(0x19, 9)) != ESP_OK) return err; // 1 kHz / (9+1) = 100 Hz
    if ((err = write_reg(0x1B, GYRO_FS_SEL << 3)) != ESP_OK) return err;
    return write_reg(0x1C, ACCEL_FS_SEL << 3);
}

esp_err_t mpu6050_read(imu_sample_t *sample)
{
    uint8_t reg = 0x3B, bytes[14];
    esp_err_t err = i2c_master_transmit_receive(sensor, &reg, 1, bytes, sizeof(bytes), 20);
    if (err != ESP_OK) return err;
    for (int i = 0; i < 6; i++) {
        int offset = i < 3 ? i * 2 : i * 2 + 2; // Bỏ 2 byte nhiệt độ.
        sample->axis[i] = (int16_t)(((uint16_t)bytes[offset] << 8) | bytes[offset+1]);
    }
    sample->at_us = esp_timer_get_time();
    return ESP_OK;
}

float mpu6050_accel_scale(void)
{
    const float scale[] = {16384, 8192, 4096, 2048};
    return scale[ACCEL_FS_SEL];
}
float mpu6050_gyro_scale(void)
{
    const float scale[] = {131, 65.5f, 32.8f, 16.4f};
    return scale[GYRO_FS_SEL];
}
