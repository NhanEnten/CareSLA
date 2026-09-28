#include "net.h"
#include "config.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "mqtt_client.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.h.example"
#endif

#define CONNECTED BIT0
#define TIME_READY BIT1
static EventGroupHandle_t flags;
static QueueHandle_t acknowledgements;
static esp_mqtt_client_handle_t client;
static char device_addr[43];
static const char *TAG = "net";

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == WIFI_EVENT && (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED)) {
        if (id == WIFI_EVENT_STA_DISCONNECTED) xEventGroupClearBits(flags, CONNECTED);
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) ESP_LOGI(TAG, "Wi-Fi connected");
}

static void time_synced(struct timeval *tv)
{
    (void)tv;
    xEventGroupSetBits(flags, TIME_READY);
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    esp_mqtt_event_handle_t event = data;
    if (id == MQTT_EVENT_CONNECTED) {
        xEventGroupSetBits(flags, CONNECTED);
        ESP_LOGI(TAG, "MQTT connected");
    } else if (id == MQTT_EVENT_DISCONNECTED) {
        xEventGroupClearBits(flags, CONNECTED);
    } else if (id == MQTT_EVENT_PUBLISHED || id == MQTT_EVENT_DELETED) {
        int message = id == MQTT_EVENT_PUBLISHED ? event->msg_id : -event->msg_id;
        xQueueSend(acknowledgements, &message, 0);
    }
}

bool net_time_ready(void)
{
    return flags && (xEventGroupGetBits(flags) & TIME_READY);
}

static void heartbeat_task(void *arg)
{
    (void)arg;
    char topic[100], json[160];
    snprintf(topic, sizeof(topic), "carensla/%s/heartbeat", device_addr);
    for (;;) {
        xEventGroupWaitBits(flags, CONNECTED | TIME_READY, pdFALSE, pdTRUE, portMAX_DELAY);
        snprintf(json, sizeof(json), "{\"device\":\"%s\",\"timestamp\":%" PRIu64 ",\"battery\":null}",
                 device_addr, (uint64_t)time(NULL));
        esp_mqtt_client_publish(client, topic, json, 0, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_MS));
    }
}

esp_err_t net_start(const char *device)
{
    if (!WIFI_SSID[0] || !MQTT_BROKER_URI[0]) return ESP_ERR_INVALID_ARG;
    snprintf(device_addr, sizeof(device_addr), "%s", device);
    flags = xEventGroupCreate();
    acknowledgements = xQueueCreate(8, sizeof(int));
    if (!flags || !acknowledgements) return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    if (!esp_netif_create_default_wifi_sta()) return ESP_ERR_NO_MEM;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    wifi_config_t wifi = {0};
    if (strlen(WIFI_SSID) > sizeof(wifi.sta.ssid) || strlen(WIFI_PASSWORD) > sizeof(wifi.sta.password))
        return ESP_ERR_INVALID_SIZE;
    memcpy(wifi.sta.ssid, WIFI_SSID, strlen(WIFI_SSID));
    memcpy(wifi.sta.password, WIFI_PASSWORD, strlen(WIFI_PASSWORD));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi));
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_sntp_config_t sntp = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    sntp.sync_cb = time_synced;
    ESP_ERROR_CHECK(esp_netif_sntp_init(&sntp));
    esp_mqtt_client_config_t mqtt = {
        .broker.address.uri = MQTT_BROKER_URI,
        .credentials.client_id = device_addr,
        .outbox.limit = 32768,
        .buffer.size = 8192,
    };
    client = esp_mqtt_client_init(&mqtt);
    if (!client) return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(client));
    return xTaskCreate(heartbeat_task, "heartbeat", 3072, NULL, 2, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}

void net_send_reliable(const char *suffix, const char *json)
{
    char topic[100];
    snprintf(topic, sizeof(topic), "carensla/%s/%s", device_addr, suffix);
    for (;;) {
        xEventGroupWaitBits(flags, CONNECTED, pdFALSE, pdTRUE, portMAX_DELAY);
        int id = esp_mqtt_client_enqueue(client, topic, json, 0, 1, 0, true);
        if (id < 0) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        for (;;) {
            int ack;
            if (xQueueReceive(acknowledgements, &ack, pdMS_TO_TICKS(5000))) {
                if (ack == id) return;
                if (ack == -id) break; // Outbox hết hạn: gửi lại nguyên payload/nonce.
            } else {
                // Nếu SDK không phát DELETED, outbox rỗng nghĩa là gói đã hết hạn.
                // Chỉ một publisher QoS1 nên không nhầm với gói khác.
                if (esp_mqtt_client_get_outbox_size(client) == 0) break;
                ESP_LOGW(TAG, "Waiting for broker ACK, id=%d (RAM queue only)", id);
            }
        }
    }
}

// Gửi QoS 0, không đợi ACK — dùng cho dữ liệu stream (mất gói không sao).
void net_publish_once(const char *suffix, const char *json)
{
    if (!(xEventGroupGetBits(flags) & CONNECTED)) return;
    char topic[100];
    snprintf(topic, sizeof(topic), "carensla/%s/%s", device_addr, suffix);
    esp_mqtt_client_publish(client, topic, json, 0, 0, 0);
}
