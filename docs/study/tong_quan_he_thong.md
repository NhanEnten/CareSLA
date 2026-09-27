# Tổng quan Hệ thống CareSLA (Tài liệu học chung cho cả nhóm)

## 1. Bài toán và Giải pháp
- **Vấn đề:** Tranh chấp trách nhiệm khi có sự cố té ngã người cao tuổi. Ai cũng nói mình làm đúng nhưng bằng chứng (log) lại do chính Trung tâm dưỡng lão giữ (xung đột lợi ích).
- **Giải pháp CareSLA:** Hệ thống kết hợp AI (phát hiện té ngã nhẹ trên ESP32) + IoT (Truyền thông tin) + **Blockchain (Trọng tài tự động)**. Blockchain giữ tiền ký quỹ và tự tính phạt nếu nhân viên trung tâm phản hồi trễ.

## 2. Kiến trúc 2 luồng Tách biệt (Cực kỳ quan trọng)
Điểm cốt lõi giúp hệ thống được điểm cao:
1. **Luồng Cảnh báo (Cứu người):** ESP32 -> MQTT -> Gateway -> Telegram. Yêu cầu cực nhanh (<2s), **KHÔNG chờ Blockchain**.
2. **Luồng Trách nhiệm (Bằng chứng):** ESP32 -> Gateway -> Blockchain -> Dashboard. Đẩy lên Smart Contract để lưu lại bằng chứng không thể chối cãi.

## 3. Luồng đi của 1 sự cố Té ngã
1. Cụ già ngã -> **AI (TinyFallNet)** trên ESP32 phát hiện.
2. Thiết bị phát còi. Sau 10s không bị hủy (bấm nút) -> ESP32 dùng Khóa riêng (lưu trên bộ nhớ an toàn NVS) sinh chữ ký số ECDSA.
3. Thiết bị gửi gói tin `FALL` qua MQTT.
4. **Gateway** nhận MQTT -> Bắn luôn Telegram cho Y tá trực chính.
5. Gateway đưa `FALL` vào hàng đợi -> Gửi giao dịch `reportFall` lên mạng Sepolia Ethereum.
6. **Dashboard** frontend hiển thị sự cố đang Mở (Đếm ngược SLA 60s).
7. Y tá nhận Telegram, mở điện thoại (có MetaMask) bấm nút **Xác nhận (Acknowledge)**. Transaction ghi lại thời gian nhân viên phản hồi.
8. Y tá chạy đến phòng cụ già, bấm giữ nút trên thiết bị 3s. Thiết bị sinh gói `ARRIVAL` -> gửi lên chain (qua gateway).
9. Nếu Y tá KHÔNG xác nhận kịp trong 60s -> **Keeper (Python)** sẽ quét và gọi hàm `checkTimeout`. Contract tự động ghi 1 vi phạm, trừ tiền ký quỹ, và chuyển ca (leo thang) cho Y tá dự phòng (Backup).

## 4. Câu hỏi chung cả nhóm phải thống nhất cách trả lời

1. **Tại sao không dùng CSDL truyền thống (MySQL)?**
   Bên giữ MySQL (Trung tâm) là bên bị đánh giá năng lực và có thể bị phạt tiền. Có xung đột lợi ích nên họ có thể sửa log. Blockchain giải quyết bằng chứng phi tập trung.
2. **Tại sao Blockchain chậm mà vẫn áp dụng vào Cấp cứu?**
   Hệ thống dùng 2 luồng. Việc cấp cứu đi qua đường mạng thường (Telegram). Blockchain chỉ dùng để ghi log trách nhiệm, đến trễ vài chục giây không sao.
3. **Contract tự động chạy khi quá hạn SLA bằng cách nào?**
   Smart contract KHÔNG thể tự chạy. Cần có 1 kịch bản ngoại cảnh là **Keeper** chạy Cronjob định kỳ gọi hàm `checkTimeout` để kiểm tra.
4. **Dữ liệu sức khỏe (trục tọa độ ngã) đưa lên Blockchain có sợ lộ không?**
   Chỉ đưa **Mã băm (Hash)** của dữ liệu lên chain. Dữ liệu thô lưu ở Database cục bộ tại gia đình. Khi có tranh chấp mới lấy ra đối chiếu hash.
5. **Cơ chế chống giả mạo thiết bị?**
   Mỗi thiết bị khi mua về được ghi 1 Private Key vào bộ nhớ kín. Mọi tín hiệu té ngã đều bị yêu cầu phải có chữ ký số của chính thiết bị đó. Kể cả Gateway hay Admin cũng không thể tự giả mạo sự cố té ngã (vì không có khóa của thiết bị).
