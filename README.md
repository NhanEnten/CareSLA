# CareSLA — Giám sát té ngã và hợp đồng chăm sóc có cam kết SLA

Đồ án môn **Blockchain và Ứng dụng** (BCAP437964): hệ thống CPS kết hợp **IoT + AI + Blockchain**.

- **Bài toán:** gia đình trả phí cho trung tâm chăm sóc người cao tuổi; trung tâm cam kết phản hồi té ngã trong thời hạn SLA. Khi có sự cố, nhật ký lại nằm trong tay trung tâm, tức chính bên bị đánh giá.
- **Giải pháp:** thiết bị ESP32 phát hiện té ngã bằng mô hình AI INT8 và **ký số** mỗi sự kiện. Smart contract `CareSLA.sol` làm trọng tài: giữ tiền ký quỹ, xác thực chữ ký thiết bị, khóa lịch trực đã cam kết, ghi vi phạm khi quá hạn và tự chia tiền cuối kỳ.
- **Hai luồng tách biệt:** còi trên thiết bị kêu ngay, không chờ mạng hay blockchain (luồng cảnh báo). Sự kiện đã ký đi qua MQTT → Gateway → Contract → Dashboard (luồng trách nhiệm).

Báo cáo kỹ thuật: [`Report_NhomXX.pdf`](Report_NhomXX.pdf).

## 1. Cấu trúc repository

| Thư mục / file | Nội dung |
|---|---|
| `contracts/` | Dự án Hardhat: `contracts/CareSLA.sol` (Solidity 0.8.24), test, script deploy và tạo hợp đồng demo |
| `ai_model/` | Notebook huấn luyện `Model_AI_nhom3.ipynb`, model `dilated_aug_s0_int8.tflite` (INT8, 51.120 byte), `model_data.cc` cho firmware, thông số chuẩn hóa đầu vào |
| `iot_code/` | Firmware ESP-IDF cho ESP32 + MPU6050: đọc cảm biến, chạy AI (TFLite Micro), máy trạng thái, còi/nút, ký sự kiện, MQTT |
| `backend/` | `gateway.py` (MQTT → contract, kiểm tra chữ ký, lưu off-chain SQLite), `keeper.py` (gọi `checkTimeout` khi quá hạn) |
| `dashboard/` | Web HTML/JS + ethers v6: `setup.html` (tạo hợp đồng, chấp nhận, cam kết ca, chia tiền), `index.html` (giám sát sự cố) |
| `tools/` | `fake_device.py` (thiết bị giả lập ký sự kiện), sinh khóa thiết bị, test vector, script kiểm thử E2E |
| `visualizer/` | `monitor.py`: xem dạng sóng cảm biến ESP32 theo thời gian thực (debug) |
| `docs/` | Đặc tả giao diện (`interface_changes.md`, `ai_input_spec.md`, `test_vectors.json`), kiến trúc, runbook demo, kết quả kiểm thử |

## 2. Yêu cầu cài đặt

| Thành phần | Phiên bản |
|---|---|
| Node.js | ≥ 22 (Hardhat 2.29.1, ethers 6) |
| Python | ≥ 3.10 |
| Mosquitto | MQTT broker chạy trên laptop demo |
| MetaMask | Trình duyệt, để ký giao dịch trên dashboard |
| ESP-IDF | 5.5.x (chỉ cần khi nạp firmware ESP32 thật) |

```bash
git clone --recursive https://github.com/NhanEnten/CareSLA.git
cd CareSLA

# Contract
cd contracts
npm ci
npm test            # 66 test: nghiệp vụ SLA, chữ ký theo test vector, chia tiền
cd ..

# Gateway, keeper, công cụ
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

## 3. Cấu hình môi trường

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Chạy Hardhat local (mục 4, bước 1) thì node in ra 20 tài khoản test có sẵn ETH. Đây là khóa **công khai của Hardhat**, chỉ dùng trên máy local. Vai trò trong demo:

| Tài khoản | Vai trò | Dùng ở đâu |
|---|---|---|
| #0 | Deployer | `npm run deploy:local` |
| #1 | Gia đình (ký quỹ) | MetaMask |
| #2 | Trung tâm (provider) | MetaMask |
| #3 / #4 | Nhân viên chính / dự phòng | MetaMask |
| #5 | Gateway | `GATEWAY_PRIVATE_KEY` trong `.env` |
| #6 | Keeper | `KEEPER_PRIVATE_KEY` trong `.env` |

Điền trong `.env`:

- `NETWORK=localhost`, `PLAN_ID=1`
- `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY`: khóa của tài khoản #5 và #6
- `MQTT_HOST`, `MQTT_PORT`: địa chỉ Mosquitto
- `REGISTERED_DEVICES`: địa chỉ thiết bị (ESP32 hoặc thiết bị giả)

Khóa thiết bị giả: tạo một ví bất kỳ, rồi lưu khóa riêng (dạng `0x…`) vào `.keys/device.key`.

> Không commit `.env`, `.keys/`, `iot_code/main/secrets.h`; các file này đã có trong `.gitignore`. Chỉ dùng ví testnet.

## 4. Chạy demo trên Hardhat local (khoảng 10 phút)

Mỗi lệnh chạy ở một terminal riêng, đứng tại thư mục gốc repo trừ khi ghi khác.

1. **Blockchain local** (tạo block mỗi giây): `cd contracts && npm run node`
2. **Deploy contract:** `cd contracts && npm run deploy:local`. Lệnh này sinh `deployments/localhost.json` và ABI cho gateway, dashboard.
3. **MQTT broker:** `mosquitto -p 1883`. Nếu dùng ESP32 thật, broker phải nhận kết nối từ mạng LAN.
4. **Gateway:** `python backend/gateway.py`
5. **Keeper:** `python backend/keeper.py`
6. **Dashboard:** `python -m http.server 8000`, rồi mở `http://127.0.0.1:8000/dashboard/setup.html`
7. **MetaMask:** thêm mạng RPC `http://127.0.0.1:8545`, chainId `31337`, import tài khoản #1–#4.

Kịch bản trên `setup.html`:

| Bước | Ví | Thao tác | Kết quả |
|---|---|---|---|
| ① | #1 Gia đình | Tạo hợp đồng: ký quỹ 100 ETH, phạt 20 ETH/vi phạm, SLA 60 s, nhập địa chỉ thiết bị | Contract giữ 100 ETH |
| ② | #2 Trung tâm | Chấp nhận hợp đồng | |
| ③ | #2 Trung tâm | Cam kết ca trực (nhân viên #3, dự phòng #4) | Thử sửa ca đã bắt đầu thì contract từ chối |
| ④ | | Mở trang giám sát | |

Gửi sự kiện từ thiết bị giả (hoặc thao tác trên ESP32 thật):

```bash
python tools/fake_device.py cancel  --key-file .keys/device.key   # chỉ ghi off-chain
python tools/fake_device.py fall    --key-file .keys/device.key   # báo té ngã lên chain
python tools/fake_device.py arrival --key-file .keys/device.key   # nhân viên có mặt
```

- **FALL lần 1:** ví #3 bấm *Xác nhận* trong 60 s → không vi phạm.
- **FALL lần 2:** không ai xác nhận → keeper chuyển cho dự phòng rồi báo gia đình → **2 vi phạm**.
- **Cuối kỳ:** trên `setup.html` bấm *Tua giờ* rồi *Settle* → gia đình nhận 40 ETH, trung tâm nhận 60 ETH (phạt = min(2 × 20, 100)).

Chi tiết từng phút và cách xử lý sự cố: [`docs/demo_runbook.md`](docs/demo_runbook.md).

## 5. Nạp firmware ESP32

Phần cứng: ESP32 DevKit V1, MPU6050 (SDA GPIO25, SCL GPIO26), nút nhấn GPIO5 nối GND, còi GPIO18.

```bash
cd iot_code
cp main/secrets.h.example main/secrets.h
```

Điền trong `main/secrets.h`:

- `WIFI_SSID`, `WIFI_PASSWORD`
- `MQTT_BROKER_URI`: địa chỉ **IP laptop** trong LAN, không dùng `localhost`
- `DEVICE_PRIVATE_KEY_HEX`: chuỗi `"0x…"` 64 ký tự hex

```bash
idf.py build
idf.py -p <CỔNG> flash monitor
```

Serial in ra địa chỉ Ethereum của thiết bị. Dùng địa chỉ này cho `REGISTERED_DEVICES` và cho ô thiết bị khi tạo hợp đồng. `main/config.h`: `DETECTOR_MODE 1` dùng AI, `0` dùng ngưỡng gia tốc. Hướng dẫn chi tiết: [`iot_code/README.md`](iot_code/README.md).

Luồng trên thiết bị:

1. AI nghi ngã.
2. Kiểm tra bất động 2 s.
3. Còi kêu, mở **cửa sổ hủy 10 s**. Nhấn ngắn thì hủy: gửi CANCEL, chỉ ghi off-chain.
4. Hết 10 s mà không hủy: gửi **FALL** đã ký.
5. Nhân viên đến và **giữ nút 3 s**: gửi **ARRIVAL** đã ký.

## 6. Mô hình AI

- **Dữ liệu:** KFall, 32 người, cảm biến ở lưng dưới, 100 Hz, 6 kênh. Chia theo người: train 20, validation 6, test 6.
- **Mô hình:** CNN 1 chiều kiểu ResNet 14 lớp (4 khối dư giãn nở 1, 1, 2, 4), 14.914 tham số. Đầu vào là cửa sổ 50 × 6 (0,5 s). Báo ngã khi p ≥ 0,7 ở 2 cửa sổ liên tiếp.
- **Huấn luyện lại:** chạy `ai_model/Model_AI_nhom3.ipynb` (Kaggle/Colab, có dữ liệu KFall). Notebook xuất model INT8. `model_data.cc` là mảng byte của file `.tflite` để nhúng vào firmware.
- **Đặc tả đầu vào** (thứ tự kênh, chuẩn hóa, lượng tử): [`docs/ai_input_spec.md`](docs/ai_input_spec.md).

| Phiên bản | TP | FN | TN | FP | Độ nhạy | Độ đặc hiệu | File |
|---|---|---|---|---|---|---|---|
| Float32 | 445 | 0 | 503 | 23 | 100% | 95,6% | 74,2 KiB |
| INT8 | 445 | 0 | 503 | 23 | 100% | 95,6% | 49,9 KiB |

## 7. Kiểm thử

```bash
cd contracts && npm test                                     # 66 test contract
python -m unittest tools.test_p6_gateway -v                  # gateway: hash, heartbeat, chữ ký
python tools/check_local_e2e.py --mosquitto <đường dẫn mosquitto>   # E2E 3 vòng tự động
```

Kết quả đã chạy lưu ở `docs/report/`:

- `P2_test_results.txt`
- `P6_local_results.json`
- `P6_dashboard_postmerge_results.json`: kịch bản 100/20 ETH → chia 40/60 ETH

## 8. Giới hạn đã biết

- Chữ ký thiết bị chưa gắn `chainId` và địa chỉ contract.
- SLA tính tới lúc nhân viên xác nhận (`acknowledge`), chưa tính tới lúc có mặt.
- `settle` chuyển tiền kiểu "đẩy": nếu bên nhận là contract từ chối ETH thì `settle` bị chặn.
- Gateway và keeper là thành phần tập trung. Tuy vậy, ai cũng gọi được `checkTimeout` và `settle`.
- Khóa thiết bị lưu trong flash ESP32, chưa có chip bảo mật.
- AI học từ người trẻ và té ngã mô phỏng; kết quả trên board chưa được đánh giá định lượng.
- Mới chạy trên Hardhat local, **chưa deploy Sepolia**. Lệnh deploy Sepolia có sẵn: `npm run deploy:sepolia`, `npm run setup:sepolia`.
