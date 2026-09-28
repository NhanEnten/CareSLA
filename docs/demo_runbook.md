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

## Demo 10 phút

Trang mới: `http://127.0.0.1:8000/dashboard/setup.html` (chỉ Hardhat Local, chainId 31337).
SLA đề xuất 30 giây đang **CHỜ CHỐT IC-18**; mặc định hiện giữ 60 giây theo AGENTS.md.
Kịch bản dưới đây vẫn có đủ thời gian khi dùng 60 giây; chỉ nhập 30 khi nhóm chốt.

### Chuẩn bị trước giờ demo

1. Trong `contracts/`, chạy `npm run node`, terminal khác chạy `npm run deploy:local`.
   Không chạy `demo-setup` / `setup:local`: hợp đồng tạo trên web phải là plan #1.
   Chỉ dùng node riêng cho buổi demo; không reset node đang có phiên thiết bị khác.
2. Chạy Mosquitto, gateway và keeper bằng môi trường local đã cấu hình.
   `PLAN_ID=1`, `REGISTERED_DEVICES` phải đúng địa chỉ thiết bị giả hoặc ESP32 sẽ dùng.
   Gateway dùng cấu hình của dự án; kiểm tra file .env thực tế đang được tiến trình nạp,
   không suy ra từ tab đang mở trong IDE. Không đưa khóa vào trang web.
3. Từ gốc `integration/`: `python -m http.server 8000`.
4. MetaMask import ví Hardhat #1–#4, mạng 31337. Nếu vừa restart node, xóa lịch sử
   giao dịch local cũ. #1 gia đình, #2 trung tâm, #3 chính, #4 dự phòng.
5. Có sẵn file khóa thiết bị giả riêng trong `.keys/` hoặc `.local/`, không dùng khóa
   ESP32; nhập địa chỉ công khai tương ứng vào trang thiết lập. Giữ nonce SQLite.
   Không cấu hình Telegram (IC-17); cảnh báo quan sát qua `ALERT_DISPATCH` ở gateway.

### Kịch bản trình diễn

| Phút | Thao tác | Kết quả cần quan sát |
|---|---|---|
| 0:00 | Ví #1 tạo hợp đồng: 1 ETH, phạt 0.2 ETH, kỳ +15 phút | Số dư gia đình giảm, contract giữ tiền; Tx và block |
| 1:00 | Đổi ví #2, chấp nhận | Vai trò đổi ngay; điều khoản đọc từ chain |
| 1:30 | Điền mặc định ca +20 giây, cam kết, thử ca quá khứ | Bảng ca và thông báo contract từ chối; phép thử không gửi tx |
| 2:30 | Ca bắt đầu, kiểm tra PLAN_ID, mở giám sát | Checklist đủ điều kiện; URL có planId |
| 3:00 | Gửi CANCEL | Gateway ghi off-chain, eventCount không tăng |
| 3:30 | FALL #1, ví #3 xác nhận trong SLA, rồi ARRIVAL | Không vi phạm, trạng thái đã đến nơi |
| 5:00 | FALL #2, không xác nhận | Keeper chuyển dự phòng rồi gia đình; 2 vi phạm |
| 7:15 | Sau khi thấy cấp 2, gửi ARRIVAL | Hoàn tất trước khi tua giờ |
| 7:30 | Về setup, tua giờ cuối demo, Settle | Gia đình 0.4 ETH, trung tâm 0.6 ETH; số dư ví ký còn trừ gas |
| 8:00–10:00 | Dự phòng và hỏi đáp | Giải thích giữ tiền, lịch bất biến, keeper, công thức phạt |

Với SLA 60 giây, hai cấp cần hơn 120 giây cộng chu kỳ keeper; với 30 giây cần hơn
60 giây. Quan sát cấp 2 thực tế trước ARRIVAL, không chỉ dựa vào đồng hồ kịch bản.
Nếu chuyển ví trên trang giám sát cũ, tải lại trang rồi kết nối lại ví #3; trang thiết
lập tự xử lý đổi ví. Không có thay đổi logic `app.js` trong nhiệm vụ này.

Lệnh gửi thiết bị giả (từ gốc repo, MQTT_HOST/MQTT_PORT phải trỏ broker demo):

```powershell
.venv/Scripts/python.exe tools/fake_device.py cancel --key-file .keys/device.key
.venv/Scripts/python.exe tools/fake_device.py fall --key-file .keys/device.key
.venv/Scripts/python.exe tools/fake_device.py arrival --key-file .keys/device.key
```

Lặp FALL/ARRIVAL lần hai theo bảng. ESP32 thật có bất động khoảng 2 giây + cửa sổ
hủy 10 giây, ARRIVAL giữ nút 3 giây. AI `DETECTOR_MODE 1` chưa khớp golden; luôn
chuẩn bị `fake_device.py`. Không thử sự kiện mới sau khi tua giờ; lần demo sau phải
restart node, deploy và khởi động lại gateway/keeper cho chain mới.

### Kiểm thử và tổng dượt phần mềm có bấm giờ

```powershell
node --check dashboard/setup.js
node --check dashboard/app.js
.venv/Scripts/python.exe tools/check_setup_demo.py --mosquitto .local/mosquitto/mosquitto.exe
```

Script dùng node riêng 18545 và broker 18885, từ chối chiếm cổng đang bận, sinh khóa
local riêng; không sửa deployment, .env hay ABI. Adapter transport trong tiến trình
kiểm thử chuyển URL 8545 của setup/gateway sang 18545; trang thật vẫn dùng 8545.
VM chạy setup.js/app.js với DOM và ví EIP-1193 giả, nhưng giao dịch, MQTT,
fake_device, gateway và keeper là thật. SLA chờ theo giờ thực, chỉ tua ở bước cuối.
Kết quả và thời gian từng mốc ở `.local/setup-demo-*/results.json`.
Nếu có `.local/ethers-6.13.4.cjs` tải từ đúng CDN của trang, test dùng phiên bản đó;
nếu không sẽ dùng ethers đã cài ở contracts và ghi rõ version vào kết quả.
Đây là tổng dượt phần mềm tự động, không thay bằng chứng bấm MetaMask thủ công.
