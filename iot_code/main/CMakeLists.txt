idf_component_register(SRCS "main.c" "mpu6050.c" "state.c" "net.c" "signer.c"
    "detector.cc" "model_data.cc"
    INCLUDE_DIRS "." REQUIRES freertos esp_driver_i2c esp_driver_gpio esp_driver_ledc
    esp_timer esp_wifi esp_netif mqtt nvs_flash mbedtls trezor_crypto esp-tflite-micro)
