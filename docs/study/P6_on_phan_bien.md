# Ôn phản biện — P6 (tích hợp)

## 1. Tôi đã làm gì

Tôi lấy main đã chứa công việc các thành viên và tạo nhánh tích hợp riêng.
Tôi giữ nguyên bản firmware cục bộ và sao lưu cấu hình riêng của P3.
Tôi bổ sung mẫu cấu hình để máy khác có thể build khi chưa có bí mật.
Tôi thêm chế độ ngưỡng tạm để demo không phụ thuộc AI đang sai golden.
Tôi sửa gateway để kiểm tra dữ liệu thô theo cả hai thứ tự nhận gói.
Tôi tạo thiết bị giả và các kiểm thử cho toàn luồng trách nhiệm.
Kết quả phần mềm được tách khỏi những việc cần thử trên board hoặc Telegram.

## 2. Luồng xử lý

1. Thiết bị ký FALL và gửi event, sau đó raw qua MQTT.
2. Gateway kiểm tra chữ ký, cảnh báo ngay qua Telegram hoặc log dự phòng.
3. Worker riêng gửi giao dịch; RPC lỗi thì chờ và thử lại.
4. Keeper gọi checkTimeout khi quá hạn, contract ghi phạt và chuyển cấp.
5. ARRIVAL có chữ ký được ghi nhận; cuối kỳ contract chia tiền theo vi phạm.

## 3. Đoạn code quan trọng

```python
valid = bytes(Web3.keccak(raw)) == bytes.fromhex(data_hash.removeprefix('0x'))
```

So toàn bộ 32 byte hash. Không cắt hai ký tự đầu một chuỗi hex khi chưa
chắc nó có tiền tố 0x, vì có thể bỏ mất byte đầu.

```c
if (DETECTOR_MODE == 0 && !gap) impact = sqrtf(a2) >= IMPACT_G;
```

Ngưỡng chỉ tạo candidate; vẫn phải đi qua bất động và cửa sổ hủy.

## 4. Quyết định thiết kế và lý do

- Clone riêng giữ được bản build và secrets cũ; không ghi đè thư mục ZIP.
- Lấy main vì đã merge cả nhóm và có các sửa P1 sau merge.
- Cờ ngưỡng tạm giúp kiểm tra hệ thống khi AI chưa đạt, không thay đáp án golden.
- SQLite lưu nonce trước publish; publish lỗi được phép bỏ qua một số nonce,
  nhưng không được tái sử dụng. Không dùng chung khóa giả với ESP32.
- Không gọi RPC trong đường cảnh báo vì chain chậm không được chặn cứu người.

## 5. Câu hỏi phản biện

1. Vì sao không merge lại từng nhánh? Main đã chứa chúng; nhánh cũ thiếu sửa mới.
2. Build thành công chứng minh gì? Toolchain/link đúng, chưa chứng minh cảm biến và AI đúng.
3. Vì sao có secrets.h.example? Máy mới cần biết macro nhưng không nhận bí mật.
4. Vì sao không xóa NVS? Nonce phải tăng qua reboot/nạp chương trình.
5. Fake device có thay thế board không? Chỉ kiểm tra giao diện/phần mềm, không đo phần cứng.
6. Vì sao raw có thể tới sau? ESP32 gửi event trước; kiểm tra hash phải xử lý cả hai thứ tự.
7. Heartbeat khôi phục có xóa sự cố không? Không; heartbeat chỉ là giám sát kết nối off-chain.
8. RPC chết thì gì còn chạy? MQTT và cảnh báo, giao dịch chờ worker thử lại.
9. Ai thực hiện chuyển cấp? Keeper gửi giao dịch, contract kiểm tra điều kiện và ghi phạt.
10. Log dưới hai giây có chứng minh Telegram dưới hai giây? Không, cần đo Telegram thật.

## 6. Giới hạn và điều chưa chắc chắn

Golden AI trên board còn sai; chưa có số liệu accuracy/độ trễ thực nghiệm
mới. Hàng đợi gateway và trạng thái firmware chưa bền qua mất điện.
Mô phỏng tăng thời gian Hardhat không đại diện tốc độ chain thật.
Không tuyên bố Sepolia, giao diện MetaMask hay thao tác nút/còi đã đạt
nếu chưa có bằng chứng trong nhật ký P6.

## 7. Liên hệ với thành viên khác

Nhận contract/giao diện từ P1; deploy/test/keeper từ P2; firmware/cấu hình
máy từ P3; model/spec từ P4; gateway/dashboard/vector từ P5. Bàn giao lại
nhánh p6-finish, test, log và runbook để P1 review.

## 8. Ba câu tự kiểm tra

1. Khi event tới trước raw, gateway kiểm tra hash ở đâu?
2. Nếu xóa file nonce rồi dùng lại cùng khóa, contract sẽ xử lý thế nào?
3. Cần thêm bằng chứng gì để từ kiểm thử PC chuyển sang nghiệm thu Mốc 2?
