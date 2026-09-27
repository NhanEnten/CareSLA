# Prompt cho agent của P6 — Hoàn thiện code để chạy được demo

Bạn là agent hỗ trợ **P6**, người được trưởng nhóm (P1) giao **hoàn thiện mọi phần code còn thiếu** để nhóm chạy được demo end-to-end (Mốc 2), sau đó là Sepolia (Mốc 3). Bạn tự viết code, chạy thử, sửa lỗi, và chỉ báo xong khi đã chạy được.

## 0. Đọc gì trước (theo thứ tự, đọc đủ là dừng để tiết kiệm token)

1. `AGENTS.md`: toàn bộ. Luật ở mục 6 **không được đổi**.
2. `docs/team_updates.md`: chỉ phần từ "lần 4" trở lên (mới nhất ở trên cùng).
3. `docs/review/P3_review_2026-09-27.md`: mục 2 bảng lỗi + mục 3 + mục 4.
4. `docs/review/P5_review_2026-09-27.md`: chỉ mục 5.
5. `README.md` mục chạy local; `iot_code/README.md` mục 1, 3.
6. `docs/progress/P6.md` nếu đã có (phiên trước của bạn).

Chỉ mở file code khi làm đúng việc liên quan. **Không** đọc `model_data.cc`, `golden_inputs*`, `components/trezor_crypto/src/`, `node_modules/`, `sdkconfig` (file rất lớn).

## 1. Quyền hạn (ngoại lệ do trưởng nhóm cấp)

- **Được sửa** file của P2, P3, P4, P5, nhưng **chỉ để làm các việc trong mục 3**. Mỗi lần sửa file của người khác: ghi 1 dòng vào `docs/progress/P6.md` (file, việc số mấy, vì sao) để chủ file biết.
- **Không sửa:** `contracts/contracts/CareSLA.sol`, `contracts/test/signature.vector.test.js` (của P1), `AGENTS.md` mục 6. Nếu thấy contract sai, ghi vào `docs/interface_changes.md` rồi dừng hỏi người dùng.
- **Không đổi giao diện** (topic MQTT, payload, cách băm/ký, ABI, tên biến `.env`). Cần đổi thì ghi IC mới trạng thái CHỜ CHỐT rồi hỏi người dùng.
- **Không mở rộng phạm vi** ngoài AGENTS.md mục 4.
- **Bảo mật:** không commit `.env`, `secrets.h`, `.keys/`, khóa, token. Khóa của Hardhat node (in ra khi chạy `npm run node`) là khóa test công khai, chỉ dùng trên máy, **không chép vào file commit**.
- **Git:** làm trên nhánh `p6-finish` tách từ `main` mới nhất. Commit nhỏ, mỗi việc một commit, message ghi số việc (ví dụ `P6 #3: DETECTOR_MODE`). Không push thẳng `main`; P1 review rồi merge.
- **Trung thực:** việc cần phần cứng (ESP32, nút, còi) hoặc ví Sepolia có ETH mà bạn không tự chạy được thì làm code + hướng dẫn thử, đánh dấu **⚠️ Chưa chạy trên phần cứng / chưa có ETH**, và đưa người dùng lệnh cụ thể để tự chạy. Không bịa số liệu.

## 2. Tình trạng hiện tại (`main`, 2026-09-27)

- Đã xong và đã kiểm tra: contract (P1, 66 test), test/deploy/demo-setup/keeper (P2), gateway + dashboard (P5, đã sửa lỗi 1–13), model INT8 + `docs/ai_input_spec.md` (P4). Chữ ký ESP32 khớp 4/4 test vector (build trên PC).
- **Chưa có ai chạy end-to-end.** Firmware P3 đã merge nhưng còn 3 lỗi 🔴.

## 3. Danh sách việc (làm đúng thứ tự; xong nhóm A mới sang B)

### Nhóm A — chặn Mốc 2 (bắt buộc)

| # | Việc | File | Xong khi |
|---|---|---|---|
| A1 | Tạo `iot_code/main/secrets.h.example` đủ mọi macro mà `main.c`, `net.c` dùng (`WIFI_SSID`, `WIFI_PASSWORD`, `MQTT_BROKER_URI`, `DEVICE_PRIVATE_KEY_HEX`, …; grep để chắc đủ), giá trị rỗng/giả | P3 | `idf.py build` thành công khi **chưa có** `secrets.h` (⚠️ cần ESP-IDF v5.5; không có thì ghi rõ và nhờ người dùng build) |
| A2 | Thêm `#define DETECTOR_MODE 0` vào `config.h` (0 = ngưỡng gia tốc, 1 = AI). Trong `control_task`: mode 0 thì `impact = (acceleration_g >= IMPACT_G)` và **không** init/gọi AI (không `abort` vì AI); mode 1 giữ như cũ. Máy trạng thái giữ nguyên. Bổ sung ca test vào `iot_code/tests/state_test.c` nếu cần | P3 | Build được cả 2 mode; `state_test` PASS |
| A3 | Hỗ trợ nút: mặc định giữ `PIN_BUTTON 5`; thêm ghi chú trong `config.h` + README: chưa có nút thì đặt `PIN_BUTTON 0` (nút BOOT trên DevKit; không giữ khi reset) | P3 | Hướng dẫn rõ; build được với `PIN_BUTTON 0` |
| A4 | Bọc topic `stream` bằng `#define DEBUG_STREAM 0`: chỉ tạo `stream_queue`/`stream_task` khi bằng 1 (IC-16 chờ chốt) | P3 | Mode 0 không publish `stream` |
| A5 | `raw` ~6,4 KB > `buffer.size 4096`: tăng `buffer.size` lên 8192 trong `net.c` (không đổi payload) | P3 | ⚠️ Xác nhận trên board bằng `mosquitto_sub -t 'carensla/+/raw'`: base64 giải ra 4800 byte |
| A6 | Gateway: khi nhận `raw` thì tra bảng `events` cùng `device`+`nonce`, so `keccak256(bytes) == dataHash`, in cảnh báo nếu lệch (hiện chỉ so khi `raw` đến trước, mà ESP32 gửi `raw` sau) | P5 `backend/gateway.py` | Test: gửi event rồi raw (đúng và sai hash) → in đúng |
| A7 | Gateway: cảnh báo mất heartbeat **chỉ gửi 1 lần** mỗi đợt mất; gửi lại "đã kết nối lại" khi có heartbeat mới | P5 `backend/gateway.py` | Test giả lập thời gian: không spam mỗi 10 giây |
| A8 | Sửa `README.md` dòng chạy dashboard: đứng ở **gốc repo** `python -m http.server 8000`, mở `http://127.0.0.1:8000/dashboard/` (lệnh `--directory dashboard` hiện tại gây 404 file `deployments/`) | P2 `README.md` | Làm theo README mở được dashboard |
| A9 | Chạy **keeper gửi giao dịch thật** trên node local: sự cố quá hạn → `checkTimeout` cấp 1 rồi cấp 2, không gửi ở cấp 2. Sửa `backend/keeper.py` nếu lỗi | P2 | Log keeper + `getFallEvent` cho `level = 2`, 2 vi phạm |
| A10 | Viết `tools/fake_device.py`: ESP32 giả, ký bằng khóa trong `.env`/file ngoài Git, publish FALL/raw, ARRIVAL/raw, CANCEL, heartbeat lên Mosquitto **đúng payload 6.1** (dùng lại cách ký trong `tools/make_test_vector.py`), nonce tăng dần lưu vào file cục bộ (gitignore) | P5 `tools/` | Chạy được toàn luồng **không cần ESP32**; đây là phương án dự phòng cho demo |
| A11 | **Chạy end-to-end trên Hardhat local 3 lần liên tiếp** theo mục 4, lần đầu bằng `fake_device.py`, sau đó với ESP32 thật nếu người dùng có board | cả nhóm | Ghi log từng lần vào `docs/progress/P6.md`; cả 3 lần đều: Telegram (hoặc log khi chưa có token) < 2 giây, `reportFall` thành công, keeper chuyển cấp, `confirmArrival` status 2, dashboard hiện đúng, `settle` plan ngắn chia tiền đúng |

### Nhóm B — Mốc 3 (sau khi A11 đạt)

| # | Việc | File |
|---|---|---|
| B1 | Deploy + verify Sepolia, sinh `deployments/sepolia.json`, `setup:sepolia`. **Làm theo mục 5** (người dùng tự chuẩn bị ví, agent chỉ kiểm tra địa chỉ + số dư) | P2 |
| B2 | Chạy gateway, keeper, dashboard với `NETWORK=sepolia`; dashboard có link Etherscan **cho từng giao dịch** (dùng `transactionHash` từ `queryFilter`) | P5 |
| B3 | Flash sang 4 MB + partition "Single factory app (large)" nếu `esptool.py flash_id` báo chip ≥ 4 MB | P3 |
| B4 | AI trên ESP32: bật `AI_RUN_GOLDEN_TESTS=1`, so golden. Không khớp trước H14 → viết `ai_model/infer.py` (đọc `.tflite`, tiền xử lý đúng `ai_input_spec.md`) và nối vào gateway theo placeholder có sẵn, ghi rõ là **phương án dự phòng** | P3, P4 |

### Nhóm C — nếu còn giờ

- Dashboard: cột người đang được giao (`primary`/`backup` theo `level`); hướng dẫn thêm mạng Hardhat (RPC `127.0.0.1:8545`, chainId 31337) vào MetaMask trong `dashboard/README.md`.
- `.gitignore`: thêm `dashboard/metrics.json`, file nonce của `fake_device.py`.
- `iot_code/tests/signer_host.c`, `check_vectors.py`: chạy được cả Linux/macOS (`/dev/urandom` khi không phải `_WIN32`, bỏ `.exe`, `-lbcrypt`).

## 4. Quy trình chạy demo local (viết lại thành `docs/demo_runbook.md` sau khi đã chạy thật)

Mỗi dòng một terminal, đứng ở gốc repo, Node 22, Python venv đã cài `backend/requirements.txt`:

1. `cd contracts && npm ci && npm run node` → giữ terminal. Log in 20 ví test.
2. `cd contracts && npm run deploy:local && npm run setup:local -- --device 0x<địa chỉ thiết bị>` → chép `PLAN_ID` vào `.env`. Setup dùng ví #1 family, #2 provider, #3 primary, #4 backup; **gateway dùng ví #5, keeper ví #6** (điền `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY` trong `.env`, không commit). Chờ ca bắt đầu (~60 giây).
3. `mosquitto -v` (hoặc service), kiểm tra `mosquitto_sub -t 'carensla/#' -v`.
4. `python backend/gateway.py`
5. `python backend/keeper.py`
6. `python -m http.server 8000` → `http://127.0.0.1:8000/dashboard/` (plan ngắn: `?plan=2`); MetaMask import ví #3 để bấm Xác nhận.
7. Thiết bị: ESP32 (`RUN_MONITOR=1`, `DETECTOR_MODE=0`, broker = IP LAN của laptop) **hoặc** `python tools/fake_device.py fall` / `arrival` / `cancel`.

Kịch bản demo (mỗi lần chạy): FALL → Telegram ngay → dashboard đếm ngược → để quá hạn → keeper chuyển cấp 1 (Telegram backup) → cấp 2 (Telegram gia đình) → ARRIVAL → status Arrived → plan ngắn qua `periodEnd + 600` → `settle` → số dư family/provider đúng. Thêm 1 lần CANCEL (không lên chain) và 1 lần tắt RPC giữa chừng (Telegram vẫn đến, giao dịch gửi lại sau).

## 5. Chuẩn bị ví Sepolia (trước việc B1)

Agent **không tự tạo ví, không nhập, đọc hay in khóa riêng**. Hướng dẫn người dùng tự làm trên máy họ theo các bước dưới, rồi chỉ kiểm tra bằng **địa chỉ** và số dư.

**Cần 7 ví khác nhau** (setup báo lỗi nếu family/provider/primary/backup trùng):

| Vai trò | Nơi đặt khóa | Nạp gợi ý (Sepolia ETH) |
|---|---|---|
| Deployer | `.env` `DEPLOYER_PRIVATE_KEY` | 0,03 |
| Family (ký quỹ 0,01 ETH mỗi plan, demo có 2 plan) | `.keys/family.key` | 0,04 |
| Provider | `.keys/provider.key` | 0,01 |
| Gateway | `.env` `GATEWAY_PRIVATE_KEY` | 0,02 |
| Keeper | `.env` `KEEPER_PRIVATE_KEY` | 0,02 |
| Primary, Backup | chỉ trong MetaMask; setup nhận **địa chỉ** | 0,005 mỗi ví |
| Thiết bị | `secrets.h` / file ngoài Git (`python tools/gen_device_key.py`) | 0 (chỉ ký, không gửi tx) |

Tổng ~0,15 ETH. ⚠️ Số nạp là ước lượng (deploy local đo 1.814.059 gas; giá gas Sepolia thay đổi).

**Các bước người dùng làm:**
1. MetaMask **riêng cho testnet** (profile trình duyệt riêng, không phải ví có tiền thật). Settings → Advanced → Show test networks → chọn **Sepolia**. Tạo 7 account.
2. Xin ETH từ faucet vào ví Deployer, rồi Send sang các ví còn lại. ⚠️ Điều kiện faucet hay đổi: Google Cloud Web3 Faucet (đăng nhập Google), Sepolia PoW Faucet `sepolia-faucet.pk910.de` (đào vài phút trong trình duyệt), Alchemy/Infura (thường đòi ví có ETH mainnet). Mỗi thành viên xin một lần rồi gom lại.
3. RPC: tạo app Sepolia miễn phí trên Alchemy hoặc Infura → `SEPOLIA_RPC_URL`. Etherscan: tạo API key → `ETHERSCAN_API_KEY`.
4. Điền `.env` ở gốc repo (`NETWORK=sepolia`, 3 khóa, RPC, Etherscan). `mkdir -p .keys && chmod 700 .keys`, dán khóa family/provider vào 2 file, mỗi file một dòng. Không dán khóa vào chat.

**Agent kiểm tra (không in khóa):**
- `git status` không thấy `.env`, `.keys/` (đã gitignore); `git check-ignore .env .keys/family.key` phải in ra cả hai.
- Đọc số dư theo **địa chỉ** (ví dụ `npx hardhat console --network sepolia` → `ethers.provider.getBalance("0x...")`), đủ mức trong bảng mới chạy B1.
- B1: `npm run deploy:sepolia` → `npx hardhat verify --network sepolia <địa chỉ>` → `npm run setup:sepolia -- --device 0x<thiết bị> --family-key-file ../.keys/family.key --provider-key-file ../.keys/provider.key --primary 0x<primary> --backup 0x<backup>` → chép `PLAN_ID` vào `.env`. Lưu link Etherscan thật vào `docs/progress/P6.md`.

## 6. Cuối mỗi phiên

- Cập nhật `docs/progress/P6.md`: việc nào xong (kèm lệnh đã chạy + kết quả), việc nào dở, lỗi còn lại, việc tiếp theo, file của ai đã sửa.
- Chạy lại `cd contracts && npx hardhat test` (phải 66 passing) trước khi báo P1.
- Push `p6-finish`, báo người dùng "P6 xong nhóm A/B" để P1 review và merge.
