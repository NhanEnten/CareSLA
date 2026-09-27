# CareSLA — Firmware P3

Firmware ESP-IDF v5.5.5 cho ESP32 DevKit V1: đọc MPU6050, chạy model INT8 bằng
TFLite Micro, máy trạng thái FALL, nút/còi, MQTT/SNTP và ký sự kiện.
**Golden AI trên ESP32 chưa đạt; firmware mới chưa được xác nhận end-to-end trên board.**

Sau khi clone repo, lấy component source:

```powershell
git submodule update --init --recursive
```

## 1. Điền cấu hình trước khi nạp

- `main/config.h`: điền `PIN_SDA`, `PIN_SCL`; nếu giám sát thì điền cả `PIN_BUTTON`, `PIN_BUZZER`.
  Mặc định -1 sẽ in lỗi và dừng, không truy cập chân tùy ý. Không dùng GPIO6–11 (flash),
  GPIO1/3 (serial), GPIO34–39 cho cấu hình cần output/pull-up. Tránh chân boot strap nếu chưa hiểu mạch board.
- MPU6050: địa chỉ `0x68` khi AD0 thấp, `0x69` khi AD0 cao. Nối chung GND,
  I2C mức logic 3,3V; kiểm tra pull-up của module. Xem nhãn module trước khi nối nguồn.
- Nút nối GPIO với GND, code dùng pull-up và nhấn ở mức thấp.
- `BUZZER_PASSIVE=0` cho còi active (chọn mức kích bằng `BUZZER_ACTIVE_LEVEL`);
  `=1` cho passive dùng PWM 2 kHz. Còi cần dòng lớn phải qua transistor/module driver,
  không nối tải lớn trực tiếp vào GPIO. GPIO trong config là chân điều khiển driver.
- Cấu hình hiện tại: 100 Hz, ±16g, ±2000 deg/s, ring buffer 400 mẫu. Scale khớp
  đặc tả model P4; chiều gá/trục MPU6050 trên người **chưa được xác minh**.
- Ngưỡng arm AI 1.5g, bất động 2 giây và cửa sổ hủy 10 giây là tham số firmware hiện tại,
  chưa phải kết quả hiệu chỉnh/đánh giá thực nghiệm.

## 2. Thử cảm biến

Giữ `RUN_MONITOR=0`. Không cần Wi-Fi/khóa thiết bị ở chế độ này.
Task đọc dùng `vTaskDelayUntil`. Có bộ đếm lỗi I2C và mất mẫu.
UART 115200.

Mở ESP-IDF Terminal v5.5.5, vào thư mục này và chạy:

```powershell
idf.py -DIDF_TARGET=esp32 build
idf.py -p COM5 flash monitor
```

Thay COM5 bằng cổng board trong Device Manager. Flash sẽ thay chương trình đang có trên board.
Thoát monitor bằng Ctrl + ].

## 3. Bật giám sát sau khi thử cảm biến

1. Copy `main/secrets.h.example` thành `main/secrets.h`; điền Wi-Fi, broker và khóa thiết bị testnet từ P5 tại máy.
   Không gửi khóa lên chat, không commit secrets.h. Broker phải là IP laptop trong LAN, không dùng localhost trên ESP32.
2. Đối chiếu spec P4 rồi đặt `P4_SPEC_CONFIRMED=1`, `RUN_MONITOR=1`.
3. Build/nạp lại. Địa chỉ Ethereum của thiết bị được suy ra từ khóa và in ra serial, viết thường.
4. Trên laptop chạy broker và `mosquitto_sub -h localhost -t "carensla/#" -v`.
5. Sau SNTP, heartbeat mỗi 60 giây. Kiểm tra các ca trong bảng dưới.

| Ca thử | Kết quả cần thấy |
|---|---|
| Va chạm rồi bất động | Còi và ALARM_WINDOW 10 giây |
| Bấm nút vật lý hoặc nút monitor qua USB trong cửa sổ | CANCEL có chữ ký, hash 0; không có FALL cho lần đó |
| Không hủy | FALL có chữ ký, sau đó raw cùng nonce |
| Nhấn ngắn sau FALL | Không hủy sự cố |
| Thả nút rồi giữ đủ 3 giây sau FALL | ARRIVAL và raw, trở lại IDLE (monitor chưa có lệnh ARRIVAL) |
| Reset rồi gây sự kiện mới | Nonce lớn hơn trước, không xóa NVS |
| Ngắt Wi-Fi rồi nối lại | Sự kiện trong RAM gửi lại theo FIFO, giữ nguyên nonce khi retry |

Chữ ký dùng secp256k1/RFC6979 low-s của Trezor, Keccak-256 và prefix EIP-191.
Nonce chung cho 3 loại sự kiện được commit NVS trước ký/gửi. Không có nhánh gateway ký thay.
Raw là int16 little-endian; hash và base64 dùng cùng bytes. FALL giữ snapshot trước cửa sổ hủy,
ARRIVAL lấy snapshot khi xử lý nhấn giữ. CANCEL không có raw.
`SIGNER_DEBUG=1` in packed/messageHash/ethSigned/sig để đối chiếu, không in khóa.

## 4. Kiểm thử trên PC

Từ gốc repo (Python + GCC trên Windows):

```powershell
python iot_code/tests/check_vectors.py contracts/p1_tmp/sample_test_vectors.json
gcc -std=c11 -Wall -Wextra -I iot_code/main iot_code/tests/state_test.c iot_code/main/state.c -o iot_code/build/host_tests/state_test.exe
& iot_code/build/host_tests/state_test.exe
```

Khi P5 cung cấp vector chính thức, chạy `python iot_code/tests/check_vectors.py docs/test_vectors.json`.
Vector P1 chỉ là kiểm tra tạm trên PC, không thay thế kiểm tra chữ ký trên ESP32.
Trong ESP-IDF Terminal có thể chạy `python tests/check_build_modes.py` từ iot_code:
script tạm đổi config để build monitor active/passive, rồi khôi phục; **không sửa config đồng thời, không flash khi script đang chạy**.

## 5. Giới hạn và bàn giao

- Hàng đợi có 4 job chờ + 1 job đang gửi và 1 job đang giữ; đầy thì giữ sự kiện hiện tại,
  không tự bỏ nonce hay ghi nhận sự cố mới vô hạn. Hàng đợi và trạng thái sự cố không bền qua mất điện;
  chỉ nonce bền qua reset. Sau reset trong một sự cố, cần đối chiếu log gateway.
- Không có giờ SNTP: còi/state vẫn chạy; lưu monotonic trong RAM, quy đổi Unix sau đồng bộ rồi mới gửi.
  Không đổi timestamp của gói cũ để né cửa sổ 600 giây của contract. Offline dài có thể bị chain từ chối.
- ACK MQTT chỉ xác nhận broker nhận, không chứng minh gateway/Telegram/contract xử lý thành công.
  QoS1 có thể lặp gói; P5 cần xử lý trùng device/nonce và giữ thứ tự giao dịch.
- Heartbeat là thiết bị còn kết nối, không chứng minh cảm biến đang đo đúng; xem bộ đếm lỗi serial.
- `AI_RUN_GOLDEN_TESTS=0`; golden INT8 trên board từng mismatch, vì vậy chưa thể xác nhận
  chất lượng suy luận trên ESP32. Build thành công không chứng minh AI đúng.
- Chưa có số liệu đo trên board về độ trễ, thời gian inference, arena, heap/stack hoặc
  accuracy. Không báo các giá trị này như kết quả thực nghiệm.

### Xem AI từ cảm biến thật qua USB

Bản hiện tại tắt `AI_RUN_GOLDEN_TESTS`; lỗi golden chưa được giải quyết.
Build đã đạt không có nghĩa dự đoán AI đúng. Firmware vẫn chạy máy trạng thái
và có thể phát FALL theo cấu hình `RUN_MONITOR`.

Trong ESP-IDF Terminal tại iot_code, thay COM5 bằng cổng thật:

```powershell
idf.py -p COM5 flash
```

Đóng `idf.py monitor` / Serial Monitor để nhường cổng COM, rồi tại thư mục gốc repo:

```powershell
python visualizer/monitor.py --serial COM5
```

GUI cần pyserial (`python -m pip install pyserial` nếu thiếu). Dòng AI riêng
hiển thị điểm FALL, candidate và thời gian Invoke từ ESP32. Đồ thị MPU6050
vẫn nhận qua MQTT; cấu hình MQTT_HOST/MQTT_PORT phải khớp broker firmware.
Cảnh báo ngưỡng gia tốc GUI không phải dự đoán AI. Khi quá 3 giây không có
AI_LIVE mới, dòng AI báo thiếu dữ liệu. Không mở hai ứng dụng cùng cổng COM.
