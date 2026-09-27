# Bản sửa local cho TFLite Micro

Chẩn đoán tạm: `micro/micro_interpreter_graph.cc` in AI_TRACE output INT8
sau từng op trong lần Invoke đầu tiên. Đối chiếu với `tests/trace_ai_layers.py`.
Gỡ trace sau khi giải quyết sai lệch; không dùng thời gian Invoke lần đầu có
in log làm số liệu hiệu năng.

`esp-tflite-micro/tensorflow/lite/micro/kernels/space_to_batch_nd.cc`:
trong Prepare, khởi tạo `SpaceToBatchParams.output_offset` bằng zero-point
của output INT8 (float dùng 0). Bản local trước đó chỉ cấp phát tham số,
không khởi tạo trường này, trong khi reference kernel dùng nó để padding.
Giữ bản sửa khi thay dependency; kiểm tra lại upstream trước khi bỏ bản sửa.

Model dilated_aug_s0 có hai output SPACE_TO_BATCH_ND với zero-point -128.
Test host: `iot_code/tests/space_to_batch_padding_test.cc`.
Đối chiếu model/header/JSON và ba backend PC:
`iot_code/tests/verify_ai_golden.py` (NumPy + ai-edge-litert 2.2.0).

Golden trên board vẫn cần chạy sau mỗi cập nhật. Chưa đổi tolerance hoặc
đáp án chuẩn. Bản thử tắt ESP-NN Conv2D đã được hoàn nguyên vì không thay đổi
đầu ra sai trên board.
