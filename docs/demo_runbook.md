# Chạy bản tích hợp P6

## Bảo toàn firmware P3

Bản dự án mới nằm trong `integration/`, nhánh `p6-finish`. Thư mục cha chứa
bản P3 gốc và build cũ, không bị thay đổi. Không copy thư mục build giữa hai
vị trí vì CMake lưu đường dẫn tuyệt đối.

Các file riêng đã sao lưu cục bộ tại `.local/p3-backup/`, bị Git bỏ qua.
Không gửi thư mục này lên GitHub. Không dùng `erase-flash` hoặc xóa NVS:
nonce thiết bị phải giữ qua lần nạp tiếp theo.

ESP32 đã được nhận diện tại **COM5**, flash **4 MB**. Bản tích hợp vẫn giữ
partition 2 MB cũ để không thay bố cục flash trong giai đoạn baseline.
SDA25/SCL26, nút5/còi18 giữ theo P3. Nếu chưa gắn nút GPIO5, sửa
`PIN_BUTTON (0)` để dùng BOOT; không giữ BOOT khi reset/cấp nguồn.

Mở **ESP-IDF 5.5.5 Terminal**, đứng trong `integration/iot_code`:

```powershell
idf.py build
idf.py -p COM5 flash monitor
```

Lệnh flash thay chương trình trên board; chỉ chạy khi sẵn sàng thử firmware
mới. Đóng visualizer/Serial Monitor trước khi sử dụng COM5. Mặc định
`DETECTOR_MODE=0` là phương án phát hiện ngưỡng tạm, không phải AI đã được
kiểm chứng. `DETECTOR_MODE=1` giữ luồng AI cũ; golden trên board chưa đạt.
`DEBUG_STREAM=0` tắt đồ thị stream; heartbeat/event/raw vẫn hoạt động.
Nếu tự clone mới và đã build bằng file mẫu trước khi thêm secrets.h, chạy
`idf.py fullclean build` một lần. Bản tích hợp tại máy đã được compile lại
các file dùng secrets sau khi khôi phục cấu hình riêng.

## Kiểm thử phần mềm tự động

Từ gốc `integration/`, Node >=22, Python >=3.10:

```powershell
cd contracts
npm ci
npm test
cd ..
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe -m unittest tools.test_p6_gateway -v
.venv/Scripts/python.exe -m unittest discover -s contracts/test -p 'test_*.py'
.venv/Scripts/python.exe tools/check_local_e2e.py --mosquitto .local/mosquitto/mosquitto.exe
```

E2E sở hữu node/broker riêng, từ chối chạy nếu cổng 8545/8546/18884 đang bận.
Script sinh khóa **chỉ để kiểm thử local** trong `.local/`; không đọc khóa
thiết bị thật. Ba vòng thử CANCEL off-chain, FALL/raw, mất RPC vẫn có log
cảnh báo, gửi lại FALL, keeper gửi giao dịch hai cấp, ARRIVAL và chia tiền.
Thời gian Hardhat được tăng để kiểm tra SLA/settle; đây không phải đo độ
trễ blockchain thực. Telegram dùng log dự phòng, không gọi Telegram thật.

## Demo tương tác với ESP32

1. Tại `contracts/`: `npm run node`, giữ terminal.
2. Terminal khác: `npm run deploy:local`, rồi
   `npm run setup:local -- --device 0xDIA_CHI_THIET_BI`.
   Dùng địa chỉ công khai in trên serial, không tạo lại khóa ESP32.
3. Copy `.env.example` sang `.env` nếu chưa có. Điền PLAN_ID, các ví local
   gateway #5 và keeper #6, REGISTERED_DEVICES, MQTT, Telegram nếu có.
   Chờ ca bắt đầu theo log setup.
4. Chạy Mosquitto trên laptop theo mạng LAN của thiết bị. Broker URI trong
   secrets.h phải trỏ IP laptop; broker phải cho phép kết nối LAN. Broker
   của script E2E ở cổng 18884 chỉ phục vụ kiểm thử trên PC.
5. Từ gốc repo: `.venv/Scripts/python.exe backend/gateway.py` và ở terminal
   khác `.venv/Scripts/python.exe backend/keeper.py`.
6. Từ gốc repo: `python -m http.server 8000`. Mở
   `http://127.0.0.1:8000/dashboard/`. MetaMask mạng local: RPC
   `http://127.0.0.1:8545`, chainId 31337; ví primary #3 để xác nhận.
7. Thử cảm biến trên nệm, có người hỗ trợ: va chạm → bất động → còi 10 giây;
   nhấn ngắn để CANCEL; lần khác không hủy để FALL; sau FALL thả nút rồi
   giữ 3 giây để ARRIVAL. Kiểm tra raw giải mã đủ 4800 byte.

Thiết bị giả dùng khóa riêng khác với ESP32:

```powershell
.venv/Scripts/python.exe tools/fake_device.py fall --key-file .keys/device.key
.venv/Scripts/python.exe tools/fake_device.py arrival --key-file .keys/device.key
.venv/Scripts/python.exe tools/fake_device.py cancel --key-file .keys/device.key
.venv/Scripts/python.exe tools/fake_device.py heartbeat --key-file .keys/device.key --repeat
```

Không xóa `.local/fake-device.sqlite` khi dùng lại cùng khóa/plan. Sau khi
restart Hardhat, deploy/setup lại rồi restart gateway/keeper. Đọc
`docs/progress/P6.md` để biết bước nào đã chạy thật và bước nào còn chờ.
