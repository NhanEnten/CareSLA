#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "mbedtls/base64.h"
#include "config.h"
#include "mpu6050.h"
#include "net.h"
#include "signer.h"
#include "state.h"
#include "detector.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.h.example"
#endif

typedef struct {
    uint8_t type;
    uint64_t timestamp;
    int64_t at_us;
    size_t raw_size;
    uint8_t raw[RAW_WINDOW_SAMPLES * 12];
} event_job_t;

static const char *TAG = "care";
static QueueHandle_t sample_queue, event_queue;
#if DEBUG_STREAM
static QueueHandle_t stream_queue;
#endif
static QueueHandle_t cancel_command_queue;
static uint8_t device_key[32], device[20];
static char device_text[43];
static nvs_handle_t nonce_store;
static uint64_t last_nonce;
// Chỉ control_task sở hữu ring buffer và snapshot.
static imu_sample_t ring[RAW_WINDOW_SAMPLES];
static size_t ring_next, ring_count;
static uint8_t alarm_raw[RAW_WINDOW_SAMPLES * 12];
static size_t alarm_raw_size;

static size_t snapshot(uint8_t *raw)
{
    size_t first = (ring_next + RAW_WINDOW_SAMPLES - ring_count) % RAW_WINDOW_SAMPLES;
    size_t out = 0;
    for (size_t i = 0; i < ring_count; i++) {
        const imu_sample_t *sample = &ring[(first + i) % RAW_WINDOW_SAMPLES];
        for (int axis = 0; axis < 6; axis++) {
            uint16_t value = (uint16_t)sample->axis[axis];
            raw[out++] = value & 255; raw[out++] = value >> 8;
        }
    }
    return out;
}

static void buzzer(bool on)
{
    static bool previous;
    if (on == previous) return;
    previous = on;
    if (BUZZER_PASSIVE) {
        ESP_ERROR_CHECK(ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, on ? 512 : 0));
        ESP_ERROR_CHECK(ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0));
    } else {
        ESP_ERROR_CHECK(gpio_set_level(PIN_BUZZER, on ? BUZZER_ACTIVE_LEVEL : !BUZZER_ACTIVE_LEVEL));
    }
}

static bool valid_output_pin(int pin)
{
    return GPIO_IS_VALID_OUTPUT_GPIO(pin) && !(pin >= 6 && pin <= 11) && pin != 1 && pin != 3;
}

static bool pins_valid(void)
{
    if (!valid_output_pin(PIN_SDA) || !valid_output_pin(PIN_SCL) || PIN_SDA == PIN_SCL) return false;
    if (!RUN_MONITOR) return true;
    // Nút cần internal pull-up; GPIO34..39 không có pull-up trên ESP32.
    if (!valid_output_pin(PIN_BUTTON) || !valid_output_pin(PIN_BUZZER)) return false;
    return PIN_BUTTON != PIN_SDA && PIN_BUTTON != PIN_SCL && PIN_BUTTON != PIN_BUZZER &&
           PIN_BUZZER != PIN_SDA && PIN_BUZZER != PIN_SCL;
}

static void init_button_buzzer(void)
{
    // Biến trung gian tránh phép dịch hằng số âm khi chân chưa được điền.
    int button_pin = PIN_BUTTON;
    gpio_config_t button = {.pin_bit_mask = 1ULL << button_pin, .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE, .intr_type = GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&button));
    if (BUZZER_PASSIVE) {
        ledc_timer_config_t timer = {.speed_mode = LEDC_LOW_SPEED_MODE,
            .duty_resolution = LEDC_TIMER_10_BIT, .timer_num = LEDC_TIMER_0,
            .freq_hz = 2000, .clk_cfg = LEDC_AUTO_CLK};
        ESP_ERROR_CHECK(ledc_timer_config(&timer));
        ledc_channel_config_t channel = {.gpio_num = PIN_BUZZER,
            .speed_mode = LEDC_LOW_SPEED_MODE, .channel = LEDC_CHANNEL_0,
            .timer_sel = LEDC_TIMER_0, .duty = 0, .hpoint = 0};
        ESP_ERROR_CHECK(ledc_channel_config(&channel));
    } else {
        ESP_ERROR_CHECK(gpio_set_level(PIN_BUZZER, !BUZZER_ACTIVE_LEVEL));
        ESP_ERROR_CHECK(gpio_set_direction(PIN_BUZZER, GPIO_MODE_OUTPUT));
    }
}

#if DEBUG_STREAM
// Stream task: gom 10 mẫu một lần, gửi QoS 0 lên topic stream, ~10 Hz update.
// Không block sample_task hay event_task.
static void stream_task(void *arg)
{
    (void)arg;
    // Gửi timestamp từng mẫu để monitor tô đúng cửa sổ AI đã đánh giá.
    static char json[900];
    imu_sample_t buf[10];
    for (;;) {
        // Đợi đủ 10 mẫu mới rồi gửi một lần.
        for (int i = 0; i < 10; i++) {
            xQueueReceive(stream_queue, &buf[i], portMAX_DELAY);
        }
        if (!RUN_MONITOR) continue; // Chỉ gửi khi đang chạy monitor có MQTT.
        // Giữ timestamp từng mẫu để ghép với window_end_us của AI_LIVE.
        int pos = 0;
        pos += snprintf(json + pos, sizeof(json) - pos, "{\"timestamps_us\":[");
        for (int i = 0; i < 10 && pos < (int)sizeof(json) - 30; i++) {
            pos += snprintf(json + pos, sizeof(json) - pos,
                "%s%" PRId64, i ? "," : "", buf[i].at_us);
        }
        pos += snprintf(json + pos, sizeof(json) - pos, "],\"samples\":[");
        for (int i = 0; i < 10 && pos < (int)sizeof(json) - 30; i++) {
            pos += snprintf(json + pos, sizeof(json) - pos,
                "%s[%d,%d,%d,%d,%d,%d]",
                i ? "," : "",
                buf[i].axis[0], buf[i].axis[1], buf[i].axis[2],
                buf[i].axis[3], buf[i].axis[4], buf[i].axis[5]);
        }
        pos += snprintf(json + pos, sizeof(json) - pos, "]}");
        net_publish_once("stream", json);
    }
}

#endif

static void sample_task(void *arg)
{
    (void)arg;
    TickType_t wake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(1000 / SAMPLE_HZ);
    uint32_t errors = 0, dropped = 0;
    int64_t report_at = 0;
    for (;;) {
        imu_sample_t s;
        if (mpu6050_read(&s) == ESP_OK) {
            if (xQueueSend(sample_queue, &s, 0) != pdTRUE) dropped++;
            // Gửi sang stream_queue (QoS 0), đầy thì bỏ qua, không ảnh hưởng sự kiện.
#if DEBUG_STREAM
            if (stream_queue) xQueueSend(stream_queue, &s, 0);
#endif
        } else errors++;
        int64_t now = esp_timer_get_time();
        if (now - report_at >= 5000000) {
            if (errors || dropped)
                ESP_LOGW(TAG, "Totals: I2C errors=%" PRIu32 ", sample drops=%" PRIu32,
                         errors, dropped);
            report_at = now;
        }
        if (xTaskGetTickCount() - wake >= period) wake = xTaskGetTickCount();
        vTaskDelayUntil(&wake, period);
    }
}

static void event_task(void *arg)
{
    (void)arg;
    for (;;) {
        event_job_t *job;
        if (!xQueueReceive(event_queue, &job, portMAX_DELAY)) continue;
        while (!net_time_ready()) vTaskDelay(pdMS_TO_TICKS(200));
        // SNTP tới sau sự kiện: quy đổi thời điểm monotonic đã lưu sang Unix.
        if (!job->timestamp) {
            struct timeval wall;
            gettimeofday(&wall, NULL);
            int64_t epoch_us = (int64_t)wall.tv_sec * 1000000 + wall.tv_usec;
            job->timestamp = (uint64_t)((epoch_us - (esp_timer_get_time() - job->at_us)) / 1000000);
        }
        if (last_nonce == UINT64_MAX) { ESP_LOGE(TAG, "Nonce exhausted"); abort(); }
        uint64_t nonce = last_nonce + 1;
        // Commit trước ký/gửi; không xóa NVS vì sẽ dùng lại nonce.
        ESP_ERROR_CHECK(nvs_set_u64(nonce_store, "nonce", nonce));
        ESP_ERROR_CHECK(nvs_commit(nonce_store));
        last_nonce = nonce;
        uint8_t hash[32] = {0}, packed[69], message[32], eth[32], sig[65];
        if (job->type != 3) signer_hash(job->raw, job->raw_size, hash);
        if (!signer_event(device_key, device, job->type, job->timestamp, nonce,
                          hash, packed, message, eth, sig)) {
            ESP_LOGE(TAG, "Signing failed; stopped without publishing"); abort();
        }
        char hash_text[67], sig_text[133], json[480];
        signer_hex_encode(hash, 32, hash_text); signer_hex_encode(sig, 65, sig_text);
        if (SIGNER_DEBUG) {
            char text[141];
            signer_hex_encode(packed, 69, text); printf("packed=%s\n", text);
            signer_hex_encode(message, 32, text); printf("messageHash=%s\n", text);
            signer_hex_encode(eth, 32, text); printf("ethSigned=%s\n", text);
            printf("sig=%s\n", sig_text);
        }
        snprintf(json, sizeof(json),
            "{\"device\":\"%s\",\"eventType\":%u,\"timestamp\":%" PRIu64
            ",\"nonce\":%" PRIu64 ",\"dataHash\":\"%s\",\"sig\":\"%s\"}",
            device_text, job->type, job->timestamp, nonce, hash_text, sig_text);
        ESP_LOGI(TAG, "Sending type=%u nonce=%" PRIu64 " ts=%" PRIu64, job->type, nonce, job->timestamp);
        net_send_reliable("event", json);
        if (job->type != 3) {
            size_t capacity = 4 * ((job->raw_size + 2) / 3) + 1, written = 0;
            unsigned char *base64 = malloc(capacity);
            char *raw_json = malloc(capacity + 160);
            if (!base64 || !raw_json) { ESP_LOGE(TAG, "Raw allocation failed"); abort(); }
            ESP_ERROR_CHECK(mbedtls_base64_encode(base64, capacity, &written, job->raw, job->raw_size));
            base64[written] = 0;
            snprintf(raw_json, capacity + 160, "{\"device\":\"%s\",\"nonce\":%" PRIu64 ",\"samples_b64\":\"%s\"}",
                     device_text, nonce, (char *)base64);
            net_send_reliable("raw", raw_json);
            free(raw_json); free(base64);
        }
        ESP_LOGI(TAG, "Broker ACK type=%u nonce=%" PRIu64, job->type, nonce);
        free(job);
    }
}

static void serial_command_task(void *arg)
{
    (void)arg;
    char line[32];
    for (;;) {
        if (!fgets(line, sizeof(line), stdin)) continue;
        char *end = strpbrk(line, "\r\n");
        if (end) *end = '\0';
        if (strcmp(line, "CANCEL_FALL") == 0) {
            uint8_t command = 1;
            xQueueSend(cancel_command_queue, &command, 0);
        }
    }
}

static void control_task(void *arg)
{
    (void)arg;
    detector_state_t state = {0};
    button_state_t button = {0};
    int64_t last_sample = 0, warning_at = 0;
    event_job_t *pending = NULL;
    bool arrival_armed = false;
    bool impact_latched = false;
    uint8_t below_impact_samples = 0;
    bool ai_session_active = false;
    int64_t pending_at_us = 0;
    uint64_t pending_timestamp = 0;
    int64_t ai_armed_at = 0;
    int64_t ai_report_at = 0;
    uint32_t ai_window_count = 0, ai_max_inference_us = 0;
    int64_t ai_live_log_at = 0;
    int ai_logged_candidate = -1;
    for (;;) {
        imu_sample_t sample;
        bool got = xQueueReceive(sample_queue, &sample, pdMS_TO_TICKS(10));
        int64_t now = esp_timer_get_time();
        bool valid = got && now - sample.at_us < 100000;
        bool impact = false, still = false;
        bool gap = valid && last_sample && sample.at_us - last_sample > 30000;
        if (gap) {
            if (DETECTOR_MODE == 1) ai_detector_reset();
            ai_session_active = false;
            impact_latched = false;
            below_impact_samples = 0;
        }
        if (valid) {
            if (gap) ring_count = 0;
            last_sample = sample.at_us;
            ring[ring_next] = sample;
            ring_next = (ring_next + 1) % RAW_WINDOW_SAMPLES;
            if (ring_count < RAW_WINDOW_SAMPLES) ring_count++;
            float a2 = 0, g2 = 0;
            for (int i = 0; i < 3; i++) {
                float a = sample.axis[i] / mpu6050_accel_scale();
                float g = sample.axis[i+3] / mpu6050_gyro_scale();
                a2 += a*a; g2 += g*g;
            }
            still = fabsf(sqrtf(a2) - 1.0f) <= STILL_ACCEL_TOL_G && g2 <= STILL_GYRO_DPS * STILL_GYRO_DPS;
            if (DETECTOR_MODE == 0 && !gap) impact = sqrtf(a2) >= IMPACT_G;
            if (DETECTOR_MODE == 1 && !gap) {
                float acceleration_g = sqrtf(a2);
                if (acceleration_g >= IMPACT_G) {
                    below_impact_samples = 0;
                    if (!impact_latched) {
                        impact_latched = true;
                        if (RUN_MONITOR && state.state == IDLE && !ai_session_active) {
                            ai_detector_start();
                            ai_session_active = true;
                            ai_armed_at = now;
                            ESP_LOGI(TAG, "Impact threshold %.2fg crossed; AI inference armed", acceleration_g);
                        }
                    }
                } else if (impact_latched) {
                    below_impact_samples++;
                    if (below_impact_samples >= 10) {
                        impact_latched = false;
                        below_impact_samples = 0;
                    }
                }
            }
            if (RUN_MONITOR && DETECTOR_MODE == 1 && !gap) {
                float physical_sample[6] = {
                    sample.axis[0] / mpu6050_accel_scale(),
                    sample.axis[1] / mpu6050_accel_scale(),
                    sample.axis[2] / mpu6050_accel_scale(),
                    sample.axis[3] / mpu6050_gyro_scale(),
                    sample.axis[4] / mpu6050_gyro_scale(),
                    sample.axis[5] / mpu6050_gyro_scale(),
                };
                ai_inference_result_t ai_result;
                if (!ai_detector_add_sample(physical_sample, &ai_result)) {
                    ESP_LOGE(TAG, "AI inference failed; stopping monitor task");
                    abort();
                }
                impact = ai_result.fall_candidate;
                if (ai_result.inference_ran) {
                    int candidate = ai_result.fall_candidate ? 1 : 0;
                    // Gửi ngay khi candidate đổi để GUI không bỏ lỡ dự đoán ngắn.
                    if (candidate != ai_logged_candidate || now - ai_live_log_at >= 500000) {
                        ESP_LOGI(TAG, "AI_LIVE p_fall=%.4f candidate=%d invoke_us=%" PRIu32 " golden=%d window_end_us=%" PRId64,
                                 (double)ai_result.fall_probability, candidate,
                                 ai_result.inference_us, AI_RUN_GOLDEN_TESTS, sample.at_us);
                        ai_live_log_at = now;
                        ai_logged_candidate = candidate;
                    }
                    ai_window_count++;
                    if (ai_result.inference_us > ai_max_inference_us)
                        ai_max_inference_us = ai_result.inference_us;
                }
            }
        }
        if (!RUN_MONITOR) continue;
        bool short_press, long_press;
        button_step(&button, now / 1000, gpio_get_level(PIN_BUTTON) == 0, &short_press, &long_press);
        uint8_t cancel_command = 0;
        bool serial_cancel = xQueueReceive(cancel_command_queue, &cancel_command, 0) == pdTRUE;
        short_press = short_press || serial_cancel;
        if (state.state != REPORTED) arrival_armed = false;
        else if (!button.raw && !button.stable) arrival_armed = true;
        long_press = long_press && arrival_armed;
        state_t before = state.state;
        uint8_t type = state.pending;
        if (got || now - last_sample > 100000 || state.state == ALARM_WINDOW || state.state == REPORTED)
            type = state_step(&state, now / 1000, valid && !gap, impact, still, short_press, long_press);
        if (serial_cancel) {
            if (type == 3) ESP_LOGI(TAG, "CANCEL_COMMAND_ACCEPTED");
            else ESP_LOGW(TAG, "CANCEL_COMMAND_REJECTED");
        }
        if (before != state.state) {
            ESP_LOGI(TAG, "State %d -> %d", before, state.state);
            if (state.state == ALARM_WINDOW) {
                alarm_raw_size = snapshot(alarm_raw);
                ESP_LOGI(TAG, "FALL_WINDOW_OPEN seconds=%d", CANCEL_WINDOW_MS / 1000);
            } else if (state.state == IDLE && before != IDLE) {
                ESP_LOGI(TAG, "FALL_CANDIDATE_CLEARED");
            }
        }
        if (state.state == IDLE && before != IDLE) {
            if (DETECTOR_MODE == 1) ai_detector_reset();
            ai_session_active = false;
        }
        if (ai_session_active && state.state == IDLE &&
            now - ai_armed_at >= (int64_t)CANDIDATE_TIMEOUT_MS * 1000) {
            if (DETECTOR_MODE == 1) ai_detector_reset();
            ai_session_active = false;
            ESP_LOGI(TAG, "AI candidate window expired without confirmed fall");
        }
        buzzer(state.state == ALARM_WINDOW && state.pending != 3);
        if (type && !pending_at_us) {
            pending_at_us = now;
            if (net_time_ready()) { struct timeval wall; gettimeofday(&wall, NULL); pending_timestamp = wall.tv_sec; }
        }
        if (type && !pending) {
            if (type == 2 && (!ring_count || now - last_sample > 100000)) continue;
            pending = calloc(1, sizeof(*pending));
            if (!pending) { ESP_LOGE(TAG, "No memory for event; retrying"); continue; }
            pending->type = type; pending->at_us = pending_at_us;
            pending->timestamp = pending_timestamp;
            if (type == 1) { pending->raw_size = alarm_raw_size; memcpy(pending->raw, alarm_raw, alarm_raw_size); }
            if (type == 2) pending->raw_size = snapshot(pending->raw);
        }
        if (pending) {
            // Sau xQueueSend worker có thể giải phóng ngay: lấy log trước khi chuyển ownership.
            unsigned queued_type = pending->type;
            if (xQueueSend(event_queue, &pending, 0) == pdTRUE) {
                ESP_LOGI(TAG, "Queued type=%u", queued_type);
                pending = NULL;
                pending_at_us = 0; pending_timestamp = 0;
                state_event_queued(&state);
                if (state.state == IDLE || state.state == REPORTED) {
                    if (DETECTOR_MODE == 1) ai_detector_reset();
                    ai_session_active = false;
                }
                buzzer(false);
                button.long_sent = button.stable;
            }
        }
        if (now - warning_at >= 5000000) {
            if (!net_time_ready()) ESP_LOGW(TAG, "Waiting for SNTP; events remain in RAM");
            if (pending) ESP_LOGW(TAG, "Event queue full; holding current event");
            if (now - last_sample > 100000) ESP_LOGW(TAG, "Sensor samples missing");
            warning_at = now;
        }
        if (now - ai_report_at >= 5000000) {
            if (ai_window_count) {
                ESP_LOGI(TAG, "AI windows=%" PRIu32 ", max Invoke=%" PRIu32 " us",
                         ai_window_count, ai_max_inference_us);
                ai_window_count = 0;
                ai_max_inference_us = 0;
            }
            ai_report_at = now;
        }
    }
}

static void start_firmware(void)
{
    if (!pins_valid()) {
        ESP_LOGE(TAG, "Fill valid, distinct GPIO pins in main/config.h before flashing again"); return;
    }
    if (RUN_MONITOR && !P4_SPEC_CONFIRMED) {
        ESP_LOGE(TAG, "Confirm sensor/detector parameters with P4 before RUN_MONITOR"); return;
    }
    ESP_LOGW(TAG, "Detector mode=%d (0=temporary threshold, 1=unverified INT8)", DETECTOR_MODE);
    ESP_ERROR_CHECK(mpu6050_init());
    if (RUN_MONITOR && DETECTOR_MODE == 1 && !ai_detector_init()) {
        ESP_LOGE(TAG, "AI model initialization or golden test failed"); return;
    }
    sample_queue = xQueueCreate(32, sizeof(imu_sample_t));
    if (!sample_queue) abort();
    if (RUN_MONITOR) {
        if (!signer_hex_decode(DEVICE_PRIVATE_KEY_HEX, device_key, 32) || !signer_address(device_key, device)) {
            ESP_LOGE(TAG, "Set a valid device key in secrets.h; never print the key"); return;
        }
        signer_hex_encode(device, 20, device_text);
        ESP_LOGI(TAG, "Device address: %s", device_text);
        // Không tự nvs_flash_erase(): nonce phải tồn tại qua reboot.
        ESP_ERROR_CHECK(nvs_flash_init());
        ESP_ERROR_CHECK(nvs_open("carensla", NVS_READWRITE, &nonce_store));
        esp_err_t err = nvs_get_u64(nonce_store, "nonce", &last_nonce);
        if (err != ESP_ERR_NVS_NOT_FOUND) ESP_ERROR_CHECK(err);
        init_button_buzzer();
        event_queue = xQueueCreate(EVENT_QUEUE_LENGTH, sizeof(event_job_t *));
        if (!event_queue) abort();
        ESP_ERROR_CHECK(net_start(device_text));
        if (xTaskCreate(event_task, "sign_send", 12288, NULL, 2, NULL) != pdPASS) abort();
        cancel_command_queue = xQueueCreate(1, sizeof(uint8_t));
        if (!cancel_command_queue) abort();
        if (xTaskCreate(serial_command_task, "serial_cmd", 3072, NULL, 1, NULL) != pdPASS) abort();
    }
    if (xTaskCreate(control_task, "control", 8192, NULL, 4, NULL) != pdPASS) abort();
    if (xTaskCreate(sample_task, "sample", 3072, NULL, 5, NULL) != pdPASS) abort();
    // Stream task: chỉ khởi động khi muốn xem sóng (có thể bắt đầu dù ở chế độ nào).
#if DEBUG_STREAM
    stream_queue = xQueueCreate(32, sizeof(imu_sample_t));
    if (!stream_queue) abort();
    if (xTaskCreate(stream_task, "stream", 3072, NULL, 1, NULL) != pdPASS) abort();
#endif
    ESP_LOGI(TAG, "Sampling %d Hz", SAMPLE_HZ);
    ESP_LOGI(TAG, "DEVICE_READY");
}

static void startup_task(void *arg)
{
    (void)arg;
    start_firmware();
    vTaskDelete(NULL);
}

void app_main(void)
{
    // Sinh public key cần stack lớn hơn main task mặc định.
    if (xTaskCreate(startup_task, "startup", 12288, NULL, 2, NULL) != pdPASS) abort();
}
