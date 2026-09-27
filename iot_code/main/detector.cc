#include "detector.h"

#include <math.h>
#include <new>
#include <string.h>

#include "ai_preprocess.h"
#include "config.h"
#include "esp_log.h"
#include "esp_timer.h"
#if AI_RUN_GOLDEN_TESTS
#include "golden_inputs.h"
#endif
#include "model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {

constexpr size_t kWindowSamples = 50;
constexpr size_t kFeatureCount = 6;
constexpr size_t kInferenceStep = 10;
constexpr size_t kRequiredFallWindows = 2;
constexpr size_t kOperatorCount = 12;

const char *TAG = "ai";
alignas(16) uint8_t tensor_arena[AI_TENSOR_ARENA_BYTES];
alignas(tflite::MicroInterpreter) uint8_t interpreter_storage[sizeof(tflite::MicroInterpreter)];
tflite::MicroMutableOpResolver<kOperatorCount> resolver;
const tflite::Model *model = nullptr;
tflite::MicroInterpreter *interpreter = nullptr;
bool initialized = false;
bool inference_active = false;

float samples[kWindowSamples][kFeatureCount];
size_t sample_write_index = 0;
size_t sample_count = 0;
size_t samples_since_inference = 0;
size_t consecutive_fall_windows = 0;

bool register_operators()
{
    return resolver.AddAdd() == kTfLiteOk &&
           resolver.AddBatchToSpaceNd() == kTfLiteOk &&
           resolver.AddConcatenation() == kTfLiteOk &&
           resolver.AddConv2D() == kTfLiteOk &&
           resolver.AddExpandDims() == kTfLiteOk &&
           resolver.AddFullyConnected() == kTfLiteOk &&
           resolver.AddMaxPool2D() == kTfLiteOk &&
           resolver.AddMean() == kTfLiteOk &&
           resolver.AddMul() == kTfLiteOk &&
           resolver.AddReduceMax() == kTfLiteOk &&
           resolver.AddReshape() == kTfLiteOk &&
           resolver.AddSpaceToBatchNd() == kTfLiteOk;
}

bool check_tensor_contract(const TfLiteTensor *input, const TfLiteTensor *output)
{
    if (input == nullptr || output == nullptr || input->type != kTfLiteInt8 ||
        output->type != kTfLiteInt8 || input->dims == nullptr || output->dims == nullptr) {
        return false;
    }

    if (input->dims->size != 3 || input->dims->data[0] != 1 ||
        input->dims->data[1] != static_cast<int>(kWindowSamples) ||
        input->dims->data[2] != static_cast<int>(kFeatureCount) ||
        output->dims->size != 2 || output->dims->data[0] != 1 || output->dims->data[1] != 2) {
        return false;
    }

    return fabsf(input->params.scale - 0.0313725508749485f) < 0.000001f &&
           input->params.zero_point == -1 &&
           fabsf(output->params.scale - 0.102272629737854f) < 0.000001f &&
           output->params.zero_point == -8;
}

#if AI_RUN_GOLDEN_TESTS
bool run_golden_vectors()
{
    TfLiteTensor *input = interpreter->input(0);
    TfLiteTensor *output = interpreter->output(0);
    unsigned mismatches = 0;
    for (const AiGoldenVector &vector : kAiGoldenVectors) {
        memcpy(input->data.int8, vector.input, sizeof(vector.input));
        const TfLiteStatus status = interpreter->Invoke();
        // Invoke loi thi khong doc output cu hoac chua hop le.
        if (status != kTfLiteOk) {
            ESP_LOGE(TAG, "Golden Invoke failed: %s status=%d", vector.name, static_cast<int>(status));
            return false;
        }
        const int actual_adl = output->data.int8[0];
        const int actual_fall = output->data.int8[1];
        const bool candidate = ai_fall_candidate(output->data.int8);
        const bool matched = actual_adl == vector.expected[0] &&
                             actual_fall == vector.expected[1] &&
                             candidate == (vector.candidate_fall != 0);
        ESP_LOGI(TAG, "Golden %s: actual=[%d,%d] expected=[%d,%d] delta=[%d,%d] fall=%d expected_fall=%d %s",
                 vector.name, actual_adl, actual_fall, vector.expected[0], vector.expected[1],
                 actual_adl - vector.expected[0], actual_fall - vector.expected[1],
                 static_cast<int>(candidate), static_cast<int>(vector.candidate_fall),
                 matched ? "PASS" : "FAIL");
        if (!matched) ++mismatches;
    }
    // Chay du cac mau de chan doan, van chan khoi dong neu bat ky mau nao sai.
    if (mismatches != 0) {
        ESP_LOGE(TAG, "Golden test failed: %u mismatched vectors; exact INT8 match required", mismatches);
        return false;
    }
    ESP_LOGI(TAG, "All %u synthetic INT8 golden vectors matched", static_cast<unsigned>(sizeof(kAiGoldenVectors) / sizeof(kAiGoldenVectors[0])));
    return true;
}

#endif

bool run_inference(ai_inference_result_t *result)
{
    TfLiteTensor *input = interpreter->input(0);
    TfLiteTensor *output = interpreter->output(0);
    for (size_t time_index = 0; time_index < kWindowSamples; time_index++) {
        size_t source_index = (sample_write_index + time_index) % kWindowSamples;
        for (size_t channel = 0; channel < kFeatureCount; channel++) {
            input->data.int8[time_index * kFeatureCount + channel] =
                ai_quantize_sample(samples[source_index][channel], static_cast<int>(channel));
        }
    }

    int64_t started_at = esp_timer_get_time();
    if (interpreter->Invoke() != kTfLiteOk) {
        ESP_LOGE(TAG, "TFLite Micro Invoke failed");
        return false;
    }
    int64_t elapsed = esp_timer_get_time() - started_at;

    float margin = ai_logit_margin(output->data.int8);
    if (margin >= 0.0f) {
        result->fall_probability = 1.0f / (1.0f + expf(-margin));
    } else {
        float exp_margin = expf(margin);
        result->fall_probability = exp_margin / (1.0f + exp_margin);
    }

    if (ai_fall_candidate(output->data.int8)) {
        consecutive_fall_windows++;
    } else {
        consecutive_fall_windows = 0;
    }

    result->inference_ran = true;
    result->fall_candidate = consecutive_fall_windows >= kRequiredFallWindows;
    result->inference_us = static_cast<uint32_t>(elapsed);
    return true;
}

}  // namespace

extern "C" bool ai_detector_init(void)
{
    if (initialized) return true;
    ESP_LOGI(TAG, "SpaceToBatchND INT8 padding fix; ESP-NN Conv2D enabled");
    if (!register_operators()) {
        ESP_LOGE(TAG, "Failed to register model operators");
        return false;
    }

    model = tflite::GetModel(g_dilated_aug_s0_model);
    if (model == nullptr || model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "Invalid model or schema version mismatch");
        return false;
    }

    interpreter = new (interpreter_storage) tflite::MicroInterpreter(
        model, resolver, tensor_arena, sizeof(tensor_arena));
    if (interpreter->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "AllocateTensors failed with arena size %u bytes", static_cast<unsigned>(sizeof(tensor_arena)));
        interpreter = nullptr;
        return false;
    }

    if (!check_tensor_contract(interpreter->input(0), interpreter->output(0))) {
        ESP_LOGE(TAG, "Model tensor shape, type, or quantization does not match spec");
        return false;
    }
    ESP_LOGI(TAG, "Tensor arena used: %u / %u bytes",
             static_cast<unsigned>(interpreter->arena_used_bytes()),
             static_cast<unsigned>(sizeof(tensor_arena)));

#if AI_RUN_GOLDEN_TESTS
    if (!run_golden_vectors()) return false;
#else
    ESP_LOGW(TAG, "LIVE TEST: golden tests disabled; AI results are unverified");
#endif

    initialized = true;
    ai_detector_reset();
    return true;
}

extern "C" void ai_detector_reset(void)
{
    inference_active = false;
    sample_write_index = 0;
    sample_count = 0;
    samples_since_inference = 0;
    consecutive_fall_windows = 0;
}

extern "C" void ai_detector_start(void)
{
    if (!initialized) return;
    inference_active = true;
    samples_since_inference = 0;
    consecutive_fall_windows = 0;
}

extern "C" bool ai_detector_add_sample(const float sample[6], ai_inference_result_t *result)
{
    if (!initialized || sample == nullptr || result == nullptr) return false;
    memset(result, 0, sizeof(*result));
    for (size_t channel = 0; channel < kFeatureCount; channel++) {
        if (!isfinite(sample[channel])) return false;
        samples[sample_write_index][channel] = sample[channel];
    }
    sample_write_index = (sample_write_index + 1) % kWindowSamples;

    if (sample_count < kWindowSamples) {
        sample_count++;
        if (sample_count < kWindowSamples || !inference_active) return true;
    }

    if (!inference_active) return true;
    samples_since_inference++;
    if (samples_since_inference < kInferenceStep) return true;
    samples_since_inference = 0;
    return run_inference(result);
}
