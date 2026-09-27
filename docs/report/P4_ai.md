# Báo cáo P4 — Mô hình AI phát hiện té ngã

## Tài sản bàn giao
Mô hình duy nhất trong gói là `ai_model/dilated_aug_s0_int8.tflite` (51,120 byte; SHA-256 `436a3463ee4802aa960c777775b680d3f9fc50a1c5798b0204a5c8c91dff0f11`). Tệp `model_data.cc/.h` được ghi nhận là sinh từ chính mô hình này. Gói còn có tiền xử lý C, đặc tả đầu vào, golden vectors tổng hợp và script hỗ trợ tái tạo/ xuất vectors.

## Dữ liệu và huấn luyện
Đặc tả bàn giao ghi cấu hình `dilated_aug`, seed 0, huấn luyện 65 epochs, chia subject-wise gồm 20 subject train, 6 validation và 6 test. Dữ liệu nguồn là KFall. Số lượng bản ghi tổng và quy mô dữ liệu tự thu không có trong gói này nên chưa báo cáo.

## Tiền xử lý và giao diện thiết bị
Đầu vào là cửa sổ 50×6 tại 100 Hz, gồm AccX/Y/Z tính theo g và GyrX/Y/Z theo độ/giây. MPU6050 cần cấu hình ±16 g và ±2000 °/s để áp dụng các hệ số chuyển đổi trong `docs/ai_input_spec.md`. Các kênh được chuẩn hóa theo mean/std đã ghi trong đặc tả rồi lượng tử hóa int8. Cần P3 xác nhận hướng lắp thực tế; tương đương hệ trục với dữ liệu KFall hiện chưa được đo.

## Kết quả hiện có
Trên KFall test, đặc tả ghi nhận tại ngưỡng p=0.7 và 2 cửa sổ liên tiếp: TP=445, FN=0, FP=23, TN=503 (đếm theo trial/file theo ghi chú nguồn). Đây là kết quả trên dữ liệu KFall, không phải phép đo trên thiết bị. Chưa có trong gói kết quả float-vs-INT8 đầy đủ, độ trễ inference trên ESP32, mức tensor arena hoặc báo động giả mỗi giờ. Không suy diễn các số liệu này từ kết quả LiteRT trên máy tính.

## Giới hạn
Mô hình là bộ phân loại cửa sổ chuyển động dùng dữ liệu KFall; không tuyên bố là TinyFallNet nguyên bản. TinyFallNet gốc dự đoán trước va chạm, còn hệ thống CareSLA xử lý cảnh báo sau khi sự kiện được phát hiện; firmware vẫn phải giữ các bước bất động và cửa sổ hủy riêng. Dữ liệu KFall không chứng minh hiệu quả với người cao tuổi thực tế. Cần P3 xác nhận operator TFLite Micro, `AllocateTensors()`, `Invoke()`, bộ nhớ và thời gian chạy trên đúng board.
