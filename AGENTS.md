# AGENTS.md — Bối cảnh chung dự án CareSLA

> **Dành cho mọi AI agent trong nhóm (Claude Code, Codex, Antigravity).**
> Đọc TOÀN BỘ file này trước khi làm bất cứ việc gì. Sau đó đọc file prompt riêng `prompts/Px_*.md` của người đang làm việc với bạn, và file tiến độ `docs/progress/Px.md` (nếu đã có).
> File này là **nguồn sự thật duy nhất** về phạm vi và giao diện giữa các tầng. Nếu prompt riêng mâu thuẫn với file này, file này thắng. Hãy báo lại cho người dùng.

---

## 1. Dự án là gì

Đồ án cuối kỳ môn **Cơ sở Blockchain và Ứng dụng**: hệ thống CPS tích hợp IoT + AI + Blockchain. Nhóm có 5 sinh viên, **chưa có kinh nghiệm smart contract**, và có tổng cộng **20 giờ** làm việc.

**Đề tài:** Hệ thống giám sát té ngã và hợp đồng chăm sóc có cam kết thời gian phản hồi (SLA) cho người cao tuổi.

**Bài toán thực tế:** Gia đình trả phí cho trung tâm chăm sóc (viện dưỡng lão hoặc điều dưỡng tại nhà). Trung tâm cam kết phản hồi sự cố té ngã trong X phút. Khi có tai nạn thường xảy ra tranh chấp: nhân viên có nhận được cảnh báo không, đến lúc nào, ai đang trực. Nhật ký hiện nằm trong hệ thống của chính trung tâm, tức bên bị đánh giá, nên có xung đột lợi ích.

**Các bên:** Gia đình (trả phí, ký quỹ), Trung tâm (bên cung cấp dịch vụ, cam kết lịch trực), Nhân viên chính và Nhân viên dự phòng của mỗi ca, Thiết bị IoT (có danh tính bằng khóa riêng).

## 2. Vì sao dùng blockchain — KHÔNG ĐƯỢC LÀM LỆCH

Giảng viên đã chê phiên bản cũ vì blockchain chỉ dùng để "lưu log". Vì vậy smart contract **bắt buộc phải làm trọng tài giữ tiền và tự thực thi luật SLA**, không chỉ ghi chép:
- Giữ tiền ký quỹ của gia đình.
- Xác thực chữ ký thiết bị, chống gửi lại gói cũ.
- Lịch trực phải cam kết **trước** giờ bắt đầu ca, sau đó không sửa được.
- Quá hạn SLA thì chuyển cấp và ghi vi phạm. Cuối kỳ tự chia tiền: trung tâm nhận phần còn lại, gia đình nhận lại tiền phạt.

Nếu bạn định đề xuất tính năng chỉ "ghi dữ liệu lên chain" mà không phục vụ các mục trên, **đừng làm**.

## 3. Kiến trúc: hai luồng tách biệt

| Luồng | Đường đi | Độ trễ mục tiêu | Mục đích |
|---|---|---|---|
| **Cảnh báo** | ESP32 (còi) → MQTT → Gateway (log `ALERT_DISPATCH`) | dưới 2 giây | Cứu người, không phụ thuộc blockchain. **Bỏ Telegram** (IC-17) |
| **Trách nhiệm** | Gateway → Smart Contract → Dashboard | vài giây đến vài phút | Bằng chứng, phạt, thanh toán |

Nếu chain lỗi hoặc chậm, **cảnh báo vẫn phải đến**. Gateway giữ hàng đợi và gửi giao dịch lên chain sau.

**Luồng trên thiết bị:**
IDLE → phát hiện va chạm (AI) → kiểm tra bất động N giây → **cửa sổ hủy 10 giây** (còi kêu; nhấn ngắn = hủy, gửi CANCEL, chỉ ghi off-chain) → gửi **FALL** đã ký → chờ nhân viên đến và **nhấn giữ 3 giây** → gửi **ARRIVAL** đã ký → IDLE.

**Quy tắc SLA:** báo động nào đã gửi FALL lên chain thì nhân viên **bắt buộc phản hồi**, kể cả khi sau đó xác định là báo giả. Trong thực tế nhân viên vẫn phải kiểm tra, nên không có hàm "đánh dấu báo giả" on-chain. Báo giả được lọc bởi cửa sổ hủy 10 giây trên thiết bị.

## 4. Phạm vi đã chốt (không tự ý thêm hoặc bớt)

**LÀM:**
- Contract `CareSLA.sol`: tạo và chấp nhận hợp đồng (kèm địa chỉ thiết bị), cam kết ca trực, báo té ngã có chữ ký, xác nhận đã nhận, xác nhận có mặt có chữ ký, kiểm tra quá hạn (2 cấp chuyển), chia tiền cuối kỳ.
- Ký quỹ bằng **ETH gốc** (Sepolia ETH hoặc ETH trên Hardhat).
- **Keeper bằng Python** gọi `checkTimeout()`.
- AI: mô hình nhẹ lấy cảm hứng từ TinyFallNet, lượng tử **INT8**, chạy trên ESP32 bằng TFLite Micro.
- Dashboard tối giản: danh sách sự cố, trạng thái SLA, nút xác nhận qua MetaMask, link Etherscan.
- Heartbeat thiết bị: chỉ giám sát off-chain ở gateway.

**KHÔNG LÀM (đã cắt có chủ đích):**
- Chainlink Automation.
- Vai trò bác sĩ và hàm `resolve()`.
- Token ERC-20.
- Hàm `markFalseAlarm()` on-chain.
- Mã hóa cơ sở dữ liệu off-chain (chỉ trình bày trong báo cáo).
- Dashboard nhiều biểu đồ.
- Heartbeat on-chain.
- Gateway kép.

## 5. Công nghệ và phiên bản

| Tầng | Công nghệ | Ghi chú |
|---|---|---|
| Contract | Solidity `^0.8.24`, **Hardhat 2.x** (không dùng Hardhat 3), `@nomicfoundation/hardhat-toolbox` bản tương thích Hardhat 2, **ethers v6**, **OpenZeppelin Contracts 5.x**. Bản đang dùng: `hardhat@2.29.1`, `hardhat-toolbox@5.0.0`, `ethers@6.17.0`, `@openzeppelin/contracts@5.6.1` | ⚠️ `npm` có thể cài Hardhat 3 mặc định, phải ghim `hardhat@^2`. **Compiler bắt buộc (IC-10):** `version: "0.8.24"`, `optimizer: { enabled: true, runs: 200 }`, `viaIR: true`, `evmVersion: "cancun"`; verify Etherscan cũng dùng đúng thiết lập này. Nên dùng Node 20/22 |
| Mạng | Hardhat local (chainId 31337) và **Sepolia** (chainId 11155111) | |
| Backend | Python 3.10+, `web3` (v7), `eth-account`, `paho-mqtt` 2.x, `requests`, `python-dotenv`, SQLite | paho-mqtt 2.x bắt buộc khai báo `CallbackAPIVersion.VERSION2` |
| Broker | Mosquitto chạy trên laptop demo | |
| Firmware | **ESP-IDF v5.x**, C cơ bản (C++ chỉ ở phần TFLite Micro), `esp-mqtt`, driver I2C của ESP-IDF, SNTP, NVS, component `espressif/esp-tflite-micro` | Viết đơn giản, ít file, ít trừu tượng |
| AI | Python, TensorFlow/Keras, TFLite converter (INT8 full-integer) | |
| Dashboard | HTML + JS thuần, ethers v6 bản UMD từ CDN (ghim phiên bản), chạy qua `python -m http.server` | Không dùng React, không mở bằng `file://` |
| Cảnh báo | Còi trên thiết bị + log gateway | Telegram đã bỏ (IC-17); code gửi Telegram còn lại chỉ là tùy chọn, demo không cấu hình |

Nếu không chắc cú pháp hoặc API của một thư viện, **kiểm tra phiên bản đã cài và tài liệu chính thức**, không được đoán.

## 6. Giao diện giữa các tầng (HỢP ĐỒNG GIAO TIẾP)

Mọi thay đổi ở mục này phải được **cả nhóm đồng ý**. Agent không được tự sửa: hãy ghi đề xuất vào `docs/interface_changes.md` rồi dừng lại hỏi người dùng.

### 6.1 MQTT

| Topic | Hướng | Nội dung |
|---|---|---|
| `carensla/<deviceAddr>/event` | ESP32 → Gateway | Sự kiện đã ký: FALL, ARRIVAL, CANCEL |
| `carensla/<deviceAddr>/raw` | ESP32 → Gateway | Dữ liệu thô của cửa sổ quanh sự kiện (base64) |
| `carensla/<deviceAddr>/heartbeat` | ESP32 → Gateway | `{"device","timestamp","battery":null}` mỗi 60 giây |

`<deviceAddr>` là địa chỉ Ethereum của thiết bị, viết thường, có tiền tố `0x`.

Payload của `event`:
```json
{
  "device": "0x...",
  "eventType": 1,
  "timestamp": 1760000000,
  "nonce": 42,
  "dataHash": "0x<32 byte hex>",
  "sig": "0x<65 byte hex: r(32) s(32) v(1), v = 27 hoặc 28>"
}
```
`eventType`: **1 = FALL**, **2 = ARRIVAL**, **3 = CANCEL** (CANCEL chỉ ghi off-chain).

Payload của `raw`: `{"device","nonce","samples_b64"}`. Trong đó `samples_b64` là base64 của mảng mẫu, mỗi mẫu gồm 6 số `int16` **little-endian** theo thứ tự `ax, ay, az, gx, gy, gz` (giá trị thô của MPU6050 ở dải đo đã chốt).

### 6.2 Cách băm và ký (rủi ro cao nhất, phải khớp tuyệt đối)

```
packed      = abi.encodePacked(address device, uint8 eventType, uint64 timestamp, uint64 nonce, bytes32 dataHash)
              // 20 + 1 + 8 + 8 + 32 = 69 byte; các số uint64 theo BIG-ENDIAN
messageHash = keccak256(packed)
ethSigned   = keccak256("\x19Ethereum Signed Message:\n32" || messageHash)   // EIP-191
sig         = secp256k1_sign(ethSigned) → r || s || v   (v = recoveryId + 27)
```
- `dataHash` của FALL và ARRIVAL = `keccak256(bytes thô của samples)`. Với CANCEL, `dataHash = 0x00…00`.
- `nonce` của mỗi thiết bị **tăng dần, lưu trong NVS** (tăng và lưu **trước** khi gửi), không được dùng lại kể cả sau khi khởi động lại. **FALL, ARRIVAL và CANCEL dùng chung một bộ đếm**; CANCEL cũng tiêu một nonce nên nonce trên chain có thể nhảy số, điều này hợp lệ (IC-07).
- Chữ ký phải là **low-s** (`s ≤ N/2` của secp256k1). OpenZeppelin `ECDSA.recover` từ chối `s` cao (IC-14).
- `ts` chỉ được lệch **−600 / +60 giây** so với giờ chain, nên ESP32 phải đồng bộ SNTP xong mới gửi sự kiện.
- **Bộ test vector chuẩn:** `docs/test_vectors.json`, do P5 tạo bằng `tools/make_test_vector.py` với một khóa **chỉ dùng để test**. ESP32, gateway và contract đều phải cho ra cùng `packed`, `messageHash`, `ethSigned`, `sig` với bộ này. Định dạng file: `docs/interface_changes.md` IC-14 (`timestamp` ở tương lai, ví dụ `2000000000`; có cả `v = 27` và `v = 28`). Kiểm tra: `cd contracts && npx hardhat test test/signature.vector.test.js`.

### 6.3 Smart contract `CareSLA.sol`

```solidity
// ---- Ghi ----
function createCarePlan(address provider, address device, uint64 slaSeconds, uint256 penaltyWei, uint64 periodEnd)
    external payable returns (uint256 planId);                 // gia đình gọi, msg.value = tiền ký quỹ
function acceptPlan(uint256 planId) external;                  // chỉ provider
function commitShift(uint256 planId, uint64 start, uint64 end, address primary, address backup) external;
                                                               // chỉ provider; start > block.timestamp; tối đa 20 ca; không chồng giờ; primary ≠ backup
function reportFall(uint256 planId, uint64 ts, uint64 nonce, bytes32 dataHash, bytes calldata sig)
    external returns (uint256 eventId);                        // ai gọi cũng được; hợp lệ nhờ chữ ký thiết bị
function acknowledge(uint256 eventId) external;                // primary hoặc backup đã chụp lại lúc reportFall
function confirmArrival(uint256 eventId, uint64 ts, uint64 nonce, bytes32 dataHash, bytes calldata sig) external;
                                                               // chữ ký thiết bị, eventType = 2; được gọi cả khi chưa acknowledge
function checkTimeout(uint256 eventId) external;               // ai gọi cũng được (keeper, gia đình...)
function settle(uint256 planId) external;                      // sau periodEnd + 600 s, không còn sự cố treo; ai gọi cũng được, chỉ một lần

// ---- Đọc ----
function hashEvent(address device, uint8 eventType, uint64 ts, uint64 nonce, bytes32 dataHash)
    external pure returns (bytes32);                           // trả về messageHash, dùng để đối chiếu khi debug
function getPlan(uint256 planId) external view returns (
    address family, address provider, address device,
    uint64 slaSeconds, uint256 penaltyWei, uint64 periodEnd,
    uint256 deposit, bool accepted, bool settled,
    uint256 violations, uint256 shiftCount, uint256 pendingEvents);
function getFallEvent(uint256 eventId) external view returns (  // KHÔNG đặt tên getEvent: trùng Contract.getEvent của ethers v6 (IC-09)
    uint256 planId, uint64 ts, bytes32 dataHash,
    address primary, address backup,
    uint64 reportedAt, uint64 deadline, uint8 level, uint8 status,
    address ackBy, uint64 ackAt, uint64 arrivedAt);
    // status: 0 = Open, 1 = Acknowledged, 2 = Arrived. level: 0 = primary, 1 = backup, 2 = đã báo gia đình.
    // Trường thời gian chưa xảy ra = 0.
function getOnDuty(uint256 planId, uint64 ts) external view returns (address primary, address backup); // không có ca → (0x0, 0x0)
function eventCount() external view returns (uint256);
function planCount() external view returns (uint256);
function lastNonce(uint256 planId) external view returns (uint64);  // nonce theo planId, KHÔNG theo thiết bị (IC-11)
// planId và eventId bắt đầu từ 1; giá trị 0 nghĩa là "không tồn tại".

// ---- Event ----
event PlanCreated(uint256 indexed planId, address indexed family, address indexed provider, address device, uint256 deposit);
event PlanAccepted(uint256 indexed planId);
event ShiftCommitted(uint256 indexed planId, uint64 start, uint64 end, address primary, address backup);
event FallReported(uint256 indexed eventId, uint256 indexed planId, bytes32 dataHash, address primary, uint64 deadline);
event Acknowledged(uint256 indexed eventId, address indexed caregiver, uint64 at);
event Escalated(uint256 indexed eventId, uint8 level, address to, uint64 newDeadline);
event SlaViolation(uint256 indexed eventId, uint256 indexed planId, uint256 totalViolations);
event Arrived(uint256 indexed eventId, uint64 at);
event Settled(uint256 indexed planId, uint256 toProvider, uint256 refundFamily);
```

**Luật cần cài đặt** (đã chốt IC-01 → IC-14, chi tiết và lý do trong `docs/interface_changes.md`):
- `createCarePlan`: `msg.value > 0`; `provider`, `device` khác 0; `provider ≠ msg.sender`; `slaSeconds > 0`; `penaltyWei ≤ msg.value`; `periodEnd > block.timestamp`.
- `commitShift`: chỉ provider, hợp đồng đã chấp nhận; `start > block.timestamp`; `end > start`; `end ≤ periodEnd`; không chồng giờ với ca đã có (`[start, end)`); `primary ≠ backup`, cả hai khác 0; tối đa 20 ca (IC-06).
- `reportFall`: hợp đồng đã được chấp nhận và chưa settle; `ts ≤ periodEnd`; chữ ký khôi phục ra đúng `device`; **`nonce > lastNonce[planId]`** (IC-11); `ts` nằm trong khoảng `[block.timestamp − 600, block.timestamp + 60]`; phải có ca trực chứa `ts`; `deadline = block.timestamp + slaSeconds`; cấp chuyển ban đầu = 0 (primary); `pendingEvents += 1`.
- `checkTimeout`: chỉ khi sự cố `Open`, `level < 2` và `block.timestamp > deadline`.
  - Cấp 0 → cấp 1: ghi vi phạm, chuyển cho backup, đặt hạn mới `block.timestamp + slaSeconds`.
  - Cấp 1 → cấp 2: ghi vi phạm, `Escalated` tới địa chỉ gia đình với `newDeadline = 0`, không chuyển tiếp nữa; sau đó `checkTimeout` revert `"max level"` (IC-04).
- `acknowledge`: primary hoặc backup đều được gọi ở mọi cấp. Nếu đã quá hạn mà chưa ai gọi `checkTimeout` thì **tự ghi vi phạm trước** rồi mới xác nhận (IC-08). Vi phạm đã ghi thì **không bị xóa**.
- `confirmArrival`: `eventType = 2`, cùng luật chữ ký, nonce và cửa sổ `ts` như FALL, thêm `ts ≥ ts của FALL`. Được gọi khi sự cố `Open` hoặc `Acknowledged` (IC-02); nếu còn `Open` mà đã quá hạn thì cũng tự ghi vi phạm trước. `arrivedAt = block.timestamp` (IC-07).
- **Mỗi sự cố tối đa 2 vi phạm.** `pendingEvents` = số sự cố còn `Open` và `level < 2`; giảm khi sự cố được nhận/có mặt hoặc lên cấp 2.
- `settle`: chỉ khi `block.timestamp > periodEnd + 600` **và** `pendingEvents == 0`, chỉ một lần (IC-12). Hợp đồng chưa được chấp nhận thì hoàn toàn bộ cho gia đình (IC-05). Còn lại `penalty = min(violations × penaltyWei, deposit)`; trung tâm nhận `deposit − penalty`, gia đình nhận `penalty`. Dùng `ReentrancyGuard` và nguyên tắc checks-effects-interactions, gửi ETH bằng `call`.
- Thông báo lỗi (`require`) và ý nghĩa: bảng trong `docs/team_updates.md` mục 4.
- **Giới hạn đã biết** (ghi vào báo cáo, không sửa):
  - Chữ ký không gắn với địa chỉ contract hay chainId, nên về lý thuyết có thể dùng lại chữ ký ở contract khác.
  - SLA chỉ tính tới lúc `acknowledge`, không tính tới lúc có mặt; on-chain vẫn lưu `ackAt` và `arrivedAt` làm bằng chứng (IC-03).
  - `settle` chuyển tiền kiểu "đẩy": nếu một bên là contract từ chối nhận ETH thì `settle` bị chặn (IC-13).

### 6.4 Tham số demo

| Tham số | Giá trị demo |
|---|---|
| SLA | 60 giây |
| Heartbeat | 60 giây, cảnh báo nếu mất quá 120 giây |
| Firmware demo (IC-17) | `DETECTOR_MODE 1` (AI), `DEBUG_STREAM 1`, giữ theo quyết định trưởng nhóm 2026-09-28 |
| Cửa sổ hủy | 10 giây |
| Tần số lấy mẫu | 100 Hz (⚠️ P4 xác nhận lại với KFall ở Giai đoạn 0) |
| Thời gian bất động, độ dài cửa sổ AI, chuẩn hóa đầu vào | P4 chốt, ghi vào `docs/ai_input_spec.md` |

### 6.5 File dùng chung do script sinh ra
- `deployments/<network>.json`: `{ "address", "chainId", "deployBlock" }` (P2 sinh).
- `backend/abi/CareSLA.json` và `dashboard/CareSLA.json`: ABI (script deploy của P2 tự copy).
- `.env.example`: danh sách biến môi trường (P2 quản lý). Tên đã chốt (IC-15): `NETWORK`, `SEPOLIA_RPC_URL` (localhost cố định `http://127.0.0.1:8545`), `DEPLOYER_PRIVATE_KEY`, `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY`, `ETHERSCAN_API_KEY`, `CONTRACT_ADDRESS` (tùy chọn), `PLAN_ID`, `MQTT_HOST`, `MQTT_PORT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_PRIMARY`, `TELEGRAM_CHAT_BACKUP`, `TELEGRAM_CHAT_FAMILY`, `TELEGRAM_CHAT_PROVIDER`, `REGISTERED_DEVICES`.
- `docs/team_updates.md`: thông báo mới nhất của P1 cho cả nhóm. **Đọc phần trên cùng** sau file này.

## 7. Cấu trúc repo và quyền sở hữu

```
carensla/
├── AGENTS.md / CLAUDE.md        # bối cảnh chung (P1 quản lý)
├── README.md                    # P2
├── Report_NhomXX.pdf            # P5 gộp
├── contracts/                   # dự án Hardhat
│   ├── contracts/CareSLA.sol    # P1
│   ├── test/                    # P2 (riêng test/signature.vector.test.js: P1)
│   ├── scripts/                 # P2 (deploy.js, demo_setup.js)
│   └── hardhat.config.js        # P2
├── deployments/                 # sinh tự động
├── iot_code/                    # dự án ESP-IDF — P3
├── ai_model/                    # P4
├── backend/                     # gateway.py (P5), keeper.py (P2), abi/, requirements.txt (P5)
├── dashboard/                   # P5
├── tools/                       # make_test_vector.py, gen_device_key.py — P5
└── docs/
    ├── test_vectors.json        # P5
    ├── ai_input_spec.md         # P4
    ├── interface_changes.md     # đề xuất thay đổi giao diện
    ├── progress/Px.md           # nhật ký tiến độ của từng người
    ├── study/Px_on_phan_bien.md # tài liệu ôn phản biện của từng người
    └── report/Px_*.md           # bản nháp phần báo cáo của từng người
```

**P6 (từ 2026-09-27, do P1 giao):** hoàn thiện code còn thiếu để chạy demo, làm trên nhánh `p6-finish`. P6 **được sửa** file của P2–P5 **chỉ cho các việc** trong `prompts/P6_hoan_thien_demo.md`, ghi lại trong `docs/progress/P6.md`; không sửa `CareSLA.sol`, test chữ ký của P1, mục 6 của file này.

**Không sửa file thuộc quyền người khác.** Cần thay đổi thì ghi vào `docs/interface_changes.md`, hoặc nhắn cho người dùng để họ trao đổi với người phụ trách.

**Git:** mỗi người làm trên nhánh riêng (`p1-contract`, `p2-test`, `p3-iot`, `p4-ai`, `p5-backend`), commit nhỏ, ít nhất mỗi giờ một lần. P1 merge vào `main` ở mỗi mốc.

## 8. Dòng thời gian (giờ H tính từ lúc cả nhóm bắt đầu)

| Giờ | Giai đoạn | Mốc bắt buộc |
|---|---|---|
| H0–H1 | 0: Chốt giao diện, dựng khung repo | `test_vectors.json` + `ai_input_spec.md` đã có |
| H1–H6 | 1: Xây từng tầng độc lập | **Mốc 1**: mỗi tầng chạy riêng được |
| H6–H11 | 2: Tích hợp end-to-end trên Hardhat local | **Mốc 2 ★ BASELINE**: chạy thông 3 lần liên tiếp, quay video dự phòng |
| H11–H12 | Nghỉ | |
| H12–H15 | 3: Sepolia + INT8 trên ESP32 + dashboard | **Mốc 3: ĐÓNG BĂNG TÍNH NĂNG** |
| H15–H18 | 4: Thực nghiệm, báo cáo, slide, video | |
| H18–H20 | 5: Tổng dượt 3 lần + luyện phản biện chéo | |

**Quy tắc vàng:** chưa qua Mốc 2 thì không làm tính năng nâng cao. Sau Mốc 3 chỉ sửa lỗi.

## 9. Quy tắc làm việc cho mọi agent

1. **Chế độ làm việc:** tự viết code, chạy thử, sửa lỗi. Sau mỗi phần, giải thích ngắn (3–6 câu tiếng Việt): đã làm gì, vì sao, chạy thử bằng lệnh nào.
2. **Code cho người mới:** đơn giản, dễ đọc, comment ngắn bằng tiếng Việt ở chỗ quan trọng. Tên biến và hàm bằng tiếng Anh. Không trừu tượng hóa quá mức.
3. **Chỉ báo xong khi đã chạy được.** Không nói "đã xong" nếu chưa build hoặc test. Không chạy được thì nói rõ lỗi gì.
4. **Trung thực:** điều gì không chắc (API, thông số, số liệu), đánh dấu **⚠️ Chưa kiểm chứng**. Không bịa số liệu thực nghiệm, không bịa trích dẫn.
5. **Tôn trọng time-box** trong prompt riêng. Hết giờ mà chưa xong thì chuyển sang phương án dự phòng và báo người dùng.
6. **Không mở rộng phạm vi** ngoài mục 4.
7. **Bảo mật:** không bao giờ đưa khóa riêng, token Telegram hay API key vào code hoặc commit. Dùng `.env` (Python/JS) và `secrets.h` (ESP32), cả hai phải có trong `.gitignore`. Chỉ dùng ví testnet.
8. **Nhật ký tiến độ:** cuối mỗi phiên làm việc, cập nhật `docs/progress/Px.md`: đã xong gì, đang dở gì, lỗi còn tồn tại, việc tiếp theo. Phiên sau đọc file này trước tiên, vì agent không nhớ giữa các phiên.

## 10. Tài liệu ôn phản biện (bắt buộc)

Rubric chấm 30% cho thuyết trình và phản biện, trong đó có "mức độ hiểu sâu của **tất cả** thành viên". Sau mỗi mốc, agent phải tạo hoặc cập nhật `docs/study/Px_on_phan_bien.md` theo mẫu:

```markdown
# Ôn phản biện — Px (<vai trò>)
## 1. Tôi đã làm gì (5–7 câu, lời lẽ đơn giản)
## 2. Luồng xử lý phần của tôi (sơ đồ mermaid hoặc các bước đánh số)
## 3. Các đoạn code quan trọng nhất (mỗi đoạn ≤ 15 dòng, giải thích dòng quan trọng)
## 4. Quyết định thiết kế và lý do (kèm phương án đã cân nhắc nhưng bỏ)
## 5. Câu hỏi giảng viên có thể hỏi (8–12 câu) và gợi ý trả lời ngắn
## 6. Giới hạn và điều chưa chắc chắn
## 7. Liên hệ với phần của người khác (nhận gì từ ai, đưa gì cho ai)
## 8. Ba câu tự kiểm tra (người học tự trả lời không nhìn tài liệu)
```
Viết bằng tiếng Việt, cho người mới học. Không chép lại cả file code.

## 11. Câu trả lời chung cả nhóm phải thống nhất
- **Tại sao không dùng MySQL?** Bên giữ database là bên bị phạt, nên có xung đột lợi ích. Contract giữ tiền và tự thực thi luật, không bên nào sửa được.
- **Contract tự chạy khi quá hạn bằng cách nào?** Contract không tự chạy. Keeper Python gọi `checkTimeout()`; ai cũng gọi được hàm này, kể cả gia đình.
- **Blockchain chậm thì sao?** Cảnh báo đi qua còi thiết bị và MQTT tới gateway, không chờ blockchain; blockchain chỉ ghi trách nhiệm.
- **Dữ liệu sức khỏe có bị công khai không?** Không. On-chain chỉ có hash; dữ liệu thô nằm off-chain.
