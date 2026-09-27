#include <cassert>
#include <cstdio>
#include "tensorflow/lite/kernels/internal/reference/space_to_batch_nd.h"

int main() {
  // Mot mau, them padding tren, roi tach thanh hai batch.
  const int8_t input[] = {7};
  const int32_t block[] = {2, 1};
  const int32_t padding[] = {1, 0, 0, 0};
  int8_t output[2] = {};
  const int32_t in_dims[] = {1,1,1,1}, out_dims[] = {2,1,1,1};
  tflite::SpaceToBatchParams params{};
  params.output_offset = -128;
  tflite::reference_ops::SpaceToBatchND(
      params, tflite::RuntimeShape(4, in_dims), input,
      tflite::RuntimeShape(1, 2), block,
      tflite::RuntimeShape(2, 2), padding,
      tflite::RuntimeShape(4, out_dims), output);
  assert(output[0] == -128 && output[1] == 7);
  // Gia tri 0 trong INT8 khong phai zero that khi zero_point=-128.
  params.output_offset = 0;
  tflite::reference_ops::SpaceToBatchND(
      params, tflite::RuntimeShape(4, in_dims), input,
      tflite::RuntimeShape(1, 2), block,
      tflite::RuntimeShape(2, 2), padding,
      tflite::RuntimeShape(4, out_dims), output);
  assert(output[0] == 0 && output[1] == 7);
  puts("PASS: INT8 SpaceToBatchND pads with supplied zero-point");
}
