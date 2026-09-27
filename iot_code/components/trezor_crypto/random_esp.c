#include "esp_random.h"
#include "rand.h"

void random_buffer(uint8_t *buffer, size_t length)
{
    esp_fill_random(buffer, length);
}
