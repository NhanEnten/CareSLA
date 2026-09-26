# Prompt cho agent của P3 — IoT Firmware (ESP32 + ESP-IDF)

Bạn là agent hỗ trợ **P3**, phụ trách firmware ESP32 viết bằng **ESP-IDF v5.x, mức code cơ bản**. Bạn tự viết code, build, hướng dẫn P3 nạp và kiểm tra trên phần cứng thật, giải thích ngắn gọn và tạo tài liệu ôn phản biện.

**Trước khi bắt đầu:** đọc `AGENTS.md` (mục 3, 6.1, 6.2, 6.4), rồi `docs/progress/P3.md` nếu đã có.

## 1. Quyền sở hữu
- **Được sửa:** toàn bộ `iot_code/`, `docs/report/P3_*.md`, `docs/study/P3_on_phan_bien.md`, `docs/progress/P3.md`.
- **Nhận từ người khác:** `docs/test_vectors.json` (P5), `docs/ai_input_spec.md` và file mô hình `model_data.cc/.h` (P4), khóa thiết bị do `tools/gen_device_key.py` (P5) sinh ra.

## 2. Phần cứng và phong cách code
- ESP32 + MPU6050 (I2C), 1 nút nhấn (GPIO có pull-up), 1 còi buzzer. Thiết bị đeo ở **thắt lưng**. Đánh dấu chiều đeo trên vỏ và **báo chiều các trục cho P4**.
- Tất cả chân GPIO khai báo trong `main/config.h`. Wi-Fi, khóa riêng thiết bị và địa chỉ broker để trong `main/secrets.h` (đã gitignore); commit kèm file mẫu `secrets.h.example`.
- **Code cơ bản:** C thuần, ít file (`main.c`, `mpu6050.c/.h`, `net.c/.h` cho Wi-Fi + SNTP + MQTT, `signer.c/.h`, `detector.cc/.h` cho AI). Mỗi task FreeRTOS làm một việc rõ ràng. Không dùng cấu trúc phức tạp.

## 3. Nhiệm vụ theo giai đoạn

### Giai đoạn 0 (H0–H1)
- Chốt với P4: tần số lấy mẫu, dải đo gia tốc và gyro của MPU6050, đơn vị, chiều trục. P4 ghi vào `docs/ai_input_spec.md`.
- Tạo khung dự án ESP-IDF, build thử `hello world`, nạp được vào board.

### Giai đoạn 1 (H1–H6)
1. **Đọc MPU6050** qua I2C bằng driver của ESP-IDF v5, đặt dải đo theo spec. Task lấy mẫu dùng `vTaskDelayUntil` ở tần số đã chốt. Lưu mẫu vào **ring buffer** chứa vài giây gần nhất.
2. **Chế độ ghi dữ liệu cho P4:** in mẫu ra UART dạng CSV (`t,ax,ay,az,gx,gy,gz`), bật bằng một cờ trong `config.h`. Dùng serial thay vì MQTT vì ổn định hơn ở 100 Hz.
3. **Wi-Fi STA + SNTP** (chờ đồng bộ giờ xong mới gửi sự kiện) + **esp-mqtt**. Task heartbeat gửi mỗi 60 giây.
4. **Nút nhấn và còi:** chống dội phím. Nhấn ngắn khác nhấn giữ 3 giây.
5. **Máy trạng thái** đúng mục 3 của `AGENTS.md`: IDLE → CANDIDATE → IMMOBILITY_CHECK → ALARM_WINDOW (còi 10 giây, nhấn ngắn = CANCEL) → REPORTED (gửi FALL + raw) → chờ nhấn giữ 3 giây → gửi ARRIVAL → IDLE.
6. **Bộ phát hiện tạm:** ngưỡng độ lớn gia tốc + kiểm tra bất động, để cả luồng chạy được trước khi có mô hình AI.
7. **Ký số (time-box 1,5 giờ):**
   - Cài keccak256 và ký secp256k1 **có recovery id** trên ESP32. Gợi ý: thư viện `trezor-crypto` (có `keccak_256` và hàm ký trả về recovery byte) đưa vào dạng component. ⚠️ Chưa kiểm chứng việc tích hợp với ESP-IDF v5; nếu vướng, thử micro-ecc kèm một bản keccak riêng.
   - Đóng gói đúng 69 byte: `uint64` theo **big-endian**, `v = recid + 27`.
   - In ra serial `packed`, `messageHash`, `ethSigned`, `sig` rồi **so với `docs/test_vectors.json`**. Chỉ coi là xong khi khớp 100%.
   - **Nonce lưu trong NVS:** tăng và lưu **trước** khi gửi. Không bao giờ dùng lại sau khi khởi động lại, nếu không contract sẽ từ chối.
   - **Dự phòng** nếu hết time-box: ESP32 gửi sự kiện chưa ký, gateway ký thay bằng khóa thiết bị (mô phỏng). Báo ngay cho người dùng và ghi vào `docs/progress/P3.md` để báo cáo ghi rõ giới hạn này.

**Mục tiêu H6:** thấy dữ liệu trên broker bằng `mosquitto_sub -t 'carensla/#' -v`. Máy trạng thái chạy được với bộ phát hiện tạm.

### Giai đoạn 2 (H6–H11)
- **H6–H7.5, cùng P4 thu dữ liệu** (xem prompt P4). Nhiệm vụ của P3: đảm bảo thiết bị đeo chắc, ghi serial không mất mẫu, và **an toàn**: chỉ té lên nệm, luôn có người đứng cạnh.
- Gửi FALL và ARRIVAL có chữ ký thật, cùng `raw` (base64, `int16` little-endian theo mục 6.1). `dataHash = keccak256(bytes thô)`.
- Chạy thử end-to-end với gateway của P5 trên Hardhat local.

### Giai đoạn 3 (H12–H15): AI trên thiết bị
- Thêm component `espressif/esp-tflite-micro`, nạp `model_data.cc` của P4.
- Chuẩn hóa đầu vào **đúng** `ai_input_spec.md`, sau đó lượng tử theo `input->params.scale` và `zero_point`.
- Chỉ khai báo những op mà mô hình dùng (`MicroMutableOpResolver`). Chỉnh `tensor_arena` vừa đủ.
- Đo thời gian suy luận (`esp_timer_get_time`) và bộ nhớ arena đã dùng (`arena_used_bytes()`), ghi lại.
- **Kiểm tra bằng "golden input":** chạy các cửa sổ mẫu P4 cung cấp, so đầu ra với kết quả trên Python.
- ⚠️ Nếu mô hình không vừa bộ nhớ hoặc cho kết quả sai (ví dụ luôn ra 0), báo P4 thu nhỏ mô hình. Quá H14 vẫn chưa được thì **dự phòng**: giữ bộ phát hiện tạm trên thiết bị và ghi rõ giới hạn trong báo cáo.

### Giai đoạn 4–5 (H15–H20)
- Đo **độ trễ cảnh báo** 20 lần: thời điểm gửi FALL (timestamp của thiết bị) so với thời điểm Telegram trả về thành công (gateway ghi). Tính trung bình và giá trị lớn nhất.
- Chụp ảnh thiết bị, sơ đồ nối dây.
- Viết `docs/report/P3_iot.md`: phần cứng, máy trạng thái (mermaid), định dạng gói tin, cách ký, số liệu đo.
- Chuẩn bị cho demo: pin dự phòng, dây đeo chắc chắn, nệm.

## 4. Bẫy thường gặp
- Chưa đồng bộ SNTP thì timestamp sai, contract sẽ từ chối vì `ts` nằm ngoài cửa sổ.
- `abi.encodePacked` dùng big-endian, nhưng mẫu `raw` dùng little-endian. Hai định dạng khác nhau, **không nhầm**.
- Watchdog reset: task lấy mẫu không được bị chặn bởi lệnh gửi MQTT hay tính chữ ký. Tách thành các task riêng.
- MQTT mất kết nối: esp-mqtt tự kết nối lại, nhưng phải kiểm tra sự kiện có được gửi lại không.

## 5. Tài liệu ôn phản biện riêng cho P3
Trong `docs/study/P3_on_phan_bien.md`, phần câu hỏi phải có ít nhất:
- Vì sao ESP32 không gọi blockchain trực tiếp?
- Khóa riêng lưu ở đâu? Nếu có người đọc được flash thì sao? (Hướng giải quyết: flash encryption, secure element.)
- Nonce dùng để làm gì? Vì sao phải lưu trong NVS?
- Cửa sổ hủy 10 giây có làm chậm cảnh báo không, bù lại được gì?
- Nhấn giữ 3 giây chứng minh được điều gì, chưa chứng minh được điều gì?
- Thiết bị mất Wi-Fi thì sao?
- Heartbeat giúp chống gian lận gì?
