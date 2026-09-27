# Bàn giao AI cho firmware CareSLA

Đọc `docs/ai_input_spec.md` trước khi tích hợp. Bản model duy nhất trong gói là
`dilated_aug_s0_int8.tflite` (SHA-256 `436a3463ee4802aa960c777775b680d3f9fc50a1c5798b0204a5c8c91dff0f11`).
`model_data.cc` và `model_data.h` được tạo từ đúng file này, đã kiểm tra khớp từng byte.

- Chép `model_data.cc`, `model_data.h`, `ai_preprocess.h`, `golden_inputs.h` vào `iot_code/main/`.
- Thêm `model_data.cc` vào `idf_component_register(SRCS ...)` nếu dự án liệt kê nguồn tường minh.
- Dùng `g_dilated_aug_s0_model` và `g_dilated_aug_s0_model_len` cho `tflite::GetModel`.
- Cấp tensor arena, đăng ký toán tử theo đúng `docs/ai_input_spec.md`, gọi
  `AllocateTensors`, sau đó nạp từng `kAiGoldenVectors[i].input` và đối chiếu
  **chính xác** `expected[0..1]` sau mỗi lần `Invoke`.
- Chỉ sau khi golden trên ESP32 khớp Python mới nối cửa sổ MPU6050 vào luồng
  inference và đo RAM/thời gian suy luận.

`golden_inputs_synthetic.json` là vector so khớp số học, không có nhãn hoạt
động thực. Muốn 10 mẫu KFall có nhãn thật, chạy script
`export_real_golden_kaggle.py` trong phiên notebook Kaggle còn chứa `Xte`.

**Chưa xác nhận khả năng build, hỗ trợ op, dung lượng tensor arena hoặc kết quả
trên ESP32 DevKit V1. Chưa xác nhận chiều lắp MPU6050 của P3 khớp hệ tọa độ
KFall.**
