# Ôn phản biện — P4 (AI phát hiện té ngã)

## 1. Tôi đã làm gì
Tôi bàn giao một mô hình INT8 cùng đặc tả đầu vào, mã nhúng C và golden vectors. Mô hình được huấn luyện với KFall và chia tập theo người để hạn chế rò rỉ giữa train và test. Đầu vào gồm gia tốc và gyro ba trục. Kết quả hiện có trong đặc tả là trên tập KFall test, chưa phải kết quả ESP32. Phần tích hợp phần cứng cần P3 xác nhận tiếp.

## 2. Luồng xử lý
1. Đọc 6 kênh IMU theo thứ tự AccX, AccY, AccZ, GyrX, GyrY, GyrZ.
2. Đổi raw MPU6050 sang g và độ/giây theo cấu hình full-scale.
3. Giữ cửa sổ 50 mẫu, chuẩn hóa theo mean/std đã chốt.
4. Lượng tử hóa thành tensor int8 `[1, 50, 6]`.
5. Chạy inference, diễn giải hai đầu ra là logits ADL và FALL.
6. Theo thiết kế huấn luyện, yêu cầu margin tương ứng p≥0.7 trong 2 cửa sổ liên tiếp để tạo candidate FALL.
7. Firmware tiếp tục quy trình bất động và cửa sổ hủy 10 giây; AI không thay thế các bước an toàn này.

## 3. Các đoạn code quan trọng nhất
Các tệp bàn giao chính là `ai_model/ai_preprocess.h` (chuẩn hóa/ lượng tử hóa), `ai_model/model_data.cc/.h` (mô hình được nhúng), và `ai_model/golden_inputs.h` (vectors đối chiếu). P3 nên dùng golden vectors để so khớp đầu ra Python với board trước khi nối cảm biến.

## 4. Quyết định thiết kế
- Dùng 6 kênh gia tốc và gyro vì MPU6050 cung cấp hai nhóm này.
- Chia theo subject để đánh giá khả năng tổng quát hóa sang người chưa thấy trong train.
- Dùng INT8 để hướng tới inference trên vi điều khiển; khả năng chạy thực tế vẫn chờ đo trên board.
- Không gọi đây là TinyFallNet nguyên bản. TinyFallNet gốc nhắm dự đoán trước va chạm cho túi khí, còn CareSLA cần cảnh báo sau khi sự cố xảy ra.

## 5. Câu hỏi giảng viên có thể hỏi
1. **Mô hình khác TinyFallNet gốc thế nào?** Đây là mô hình phân loại cửa sổ IMU lấy cảm hứng từ hướng TinyFallNet; không khẳng định kiến trúc hay mục tiêu y hệt bản gốc. Bản gốc dự đoán trước va chạm.
2. **Có dùng được cho người cao tuổi không?** Chưa thể kết luận; KFall và mô phỏng không thay thế đánh giá lâm sàng hoặc dữ liệu người cao tuổi.
3. **INT8 là gì?** Biểu diễn tensor bằng số nguyên 8 bit theo scale và zero point; cần kiểm tra sai khác đầu ra sau lượng tử hóa.
4. **Vì sao chia theo người?** Để cửa sổ từ cùng một người không lọt cả vào train lẫn test, tránh kết quả lạc quan do rò rỉ.
5. **Độ nhạy và độ đặc hiệu khác nhau thế nào?** Độ nhạy đo tỷ lệ ca té phát hiện được; độ đặc hiệu đo tỷ lệ hoạt động bình thường nhận đúng. Bỏ sót té ngã là rủi ro lớn nên cần xem độ nhạy cùng false positives.
6. **AI báo sai thì sao?** Firmware kiểm tra bất động và có cửa sổ hủy 10 giây trước khi gửi FALL lên chain.
7. **Vì sao chạy trên ESP32?** Để xử lý gần cảm biến và không phụ thuộc kết nối server; đây là mục tiêu kiến trúc, còn hiệu năng board cần đo.
8. **Đã xác nhận model chạy trên ESP32 chưa?** Chưa. P3 cần build đúng component, xác nhận operator, cấp phát tensor và so golden vectors.
9. **Kết quả KFall hiện có là gì?** Tại p=0.7, N=2: TP=445, FN=0, FP=23, TN=503 theo ghi chú đặc tả. Đây là KFall test, không phải thử nghiệm phần cứng.
10. **Vì sao không báo accuracy đơn lẻ?** Vì nó không cho thấy riêng số té bị bỏ sót và hoạt động bình thường bị báo nhầm; ma trận nhầm lẫn giúp thấy cả hai.

## 6. Giới hạn và điều chưa chắc chắn
Chưa có kết quả inference trên ESP32, đo tensor arena, độ trễ, báo động giả mỗi giờ hay kiểm chứng hướng lắp MPU6050. Golden vectors hiện có là tổng hợp để kiểm tra số học; chưa phải các mẫu KFall gắn nhãn thật.

## 7. Liên hệ với phần của người khác
P4 giao P3 model nhúng, preprocessing, đặc tả input và golden vectors. P3 trả lại lỗi operator/build, mức arena, thời gian Invoke và kết quả đối chiếu trên board. Gateway có thể dùng model dự phòng nếu P5 tích hợp inference phía backend.

## 8. Ba câu tự kiểm tra
1. Tại sao cần chia tập theo subject thay vì chia ngẫu nhiên theo cửa sổ?
2. Khi lượng tử hóa input, scale và zero point được dùng ở bước nào?
3. Vì sao số liệu KFall không thể được trình bày như độ chính xác trên ESP32 hoặc người cao tuổi?
