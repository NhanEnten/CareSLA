#pragma once

// Điền chân theo dây thực tế. -1 sẽ dừng với thông báo, không tự đoán chân.
#define PIN_SDA       (25)
#define PIN_SCL       (26)
#define PIN_BUTTON    (5)
#define PIN_BUZZER    (18)
#define BUZZER_PASSIVE 0
#define BUZZER_ACTIVE_LEVEL 1
#define MPU_ADDRESS 0x68

// 0: tắt monitor, 1: máy trạng thái + sự kiện MQTT có chữ ký.
#define RUN_MONITOR 1

// TẠM để thử driver, chưa phải đặc tả P4. Chỉ bật monitor sau khi đối chiếu.
#define P4_SPEC_CONFIRMED 1
#define SAMPLE_HZ 100
#define ACCEL_FS_SEL 3   // +/-16g, 2048 LSB/g (model training range)
#define GYRO_FS_SEL 3    // +/-2000 deg/s, 16.4 LSB/(deg/s) (model training range)
#define RAW_WINDOW_SAMPLES 400
#define IMPACT_G 1.5f
#define STILL_ACCEL_TOL_G 0.15f
#define STILL_GYRO_DPS 15.0f
#define IMMOBILE_MS 2000
#define CANDIDATE_TIMEOUT_MS 5000
#define CANCEL_WINDOW_MS 10000
#define ARRIVAL_HOLD_MS 3000
#define DEBOUNCE_MS 30
#define HEARTBEAT_MS 60000
#define EVENT_QUEUE_LENGTH 4
#define AI_TENSOR_ARENA_BYTES (96 * 1024)
// Thu nghiem du lieu that; golden chua dat, khong coi la AI da kiem chung.
#define AI_RUN_GOLDEN_TESTS 0
// Chỉ bật khi đối chiếu vector, không log khóa riêng.
#define SIGNER_DEBUG 0

#if SAMPLE_HZ != 100
#error "Chua ho tro tan so khac 100 Hz: doi chieu driver va P4 truoc khi doi."
#endif
#if ACCEL_FS_SEL < 0 || ACCEL_FS_SEL > 3 || GYRO_FS_SEL < 0 || GYRO_FS_SEL > 3
#error "Dai do MPU6050 khong hop le"
#endif
