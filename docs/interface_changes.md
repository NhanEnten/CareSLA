# Đề xuất thay đổi / làm rõ giao diện (AGENTS.md mục 6)

> Quy trình: ai thấy chỗ mơ hồ thì ghi vào đây. Cả nhóm chốt, rồi P1 cập nhật `AGENTS.md`.
> Trạng thái: `CHỜ CHỐT` → `ĐÃ CHỐT` (ghi phương án được chọn) hoặc `BỎ`.
> **Ngày 2026-09-27: IC-01 → IC-15 đều ĐÃ CHỐT và đã đưa vào AGENTS.md.**
> Mục tiêu: chốt hết trước **H1**.

---

## IC-01. `getPlan` / `getFallEvent` trả về những trường nào?
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 (test), P5 (gateway, dashboard) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** mục 6.3 chỉ ghi `returns (...)`. Dashboard và gateway cần biết đúng thứ tự trường để đọc.
- **Đề xuất:**
  ```solidity
  function getPlan(uint256 planId) external view returns (
      address family, address provider, address device,
      uint64 slaSeconds, uint256 penaltyWei, uint64 periodEnd,
      uint256 deposit, bool accepted, bool settled,
      uint256 violations, uint256 shiftCount, uint256 pendingEvents); // pendingEvents thêm theo IC-12

  function getFallEvent(uint256 eventId) external view returns (   // tên mới theo IC-09
      uint256 planId, uint64 ts, bytes32 dataHash,
      address primary, address backup,
      uint64 reportedAt, uint64 deadline, uint8 level, uint8 status,
      address ackBy, uint64 ackAt, uint64 arrivedAt);
  ```
  - `status`: 0 = Open, 1 = Acknowledged, 2 = Arrived.
  - `level`: 0 = primary, 1 = backup, 2 = đã báo gia đình.
  - Trường thời gian chưa xảy ra thì bằng 0.
  - `eventId` và `planId` **bắt đầu từ 1**, để giá trị 0 nghĩa là "không tồn tại".
- **Quyết định:** ĐÃ CHỐT theo đề xuất (thêm `pendingEvents` cuối `getPlan`; hàm đọc sự cố tên `getFallEvent`). Đã cập nhật AGENTS.md.

## IC-02. `confirmArrival` có bắt buộc phải `acknowledge` trước không?
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2, P3, P5 · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** nhân viên có thể chạy thẳng đến và nhấn giữ nút trên thiết bị mà không bấm nhận trên dashboard. Nếu contract bắt buộc phải nhận trước, giao dịch ARRIVAL sẽ revert và demo bị kẹt.
- **Phương án A (đề xuất):** cho phép `confirmArrival` khi trạng thái là `Open` hoặc `Acknowledged`, sau đó chuyển sang `Arrived`. Khi trạng thái khác `Open`, `checkTimeout` không ghi vi phạm nữa. Vi phạm đã ghi trước đó vẫn giữ nguyên.
- **Phương án B:** bắt buộc `Acknowledged` trước. Code chặt hơn nhưng dễ kẹt khi demo.
- **Quyết định:** ĐÃ CHỐT phương án A. Đã cập nhật AGENTS.md.

## IC-03. SLA chỉ tính đến lúc "nhận", không tính đến lúc "có mặt"
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, báo cáo · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** theo mục 6.3, nhân viên chỉ cần bấm `acknowledge` là hết hạn SLA, kể cả khi không đến. Đây cũng là một dòng trong mô hình đe dọa ("bấm nhận mà không đến").
- **Phương án A (đề xuất):** giữ nguyên, không mở rộng phạm vi. On-chain vẫn lưu `ackAt` và `arrivedAt` có chữ ký thiết bị, nên gia đình có bằng chứng khoảng cách giữa nhận và có mặt. Ghi rõ đây là giới hạn trong báo cáo.
- **Phương án B:** thêm một hạn thứ hai cho ARRIVAL. Cách này thêm trạng thái và thêm test, rủi ro trễ Mốc 2.
- **Quyết định:** ĐÃ CHỐT phương án A (ghi vào báo cáo là giới hạn). Đã cập nhật AGENTS.md.

## IC-04. `Escalated` ở lần chuyển cấp 1 → 2 ghi `newDeadline` bằng gì?
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P5 (dashboard), P2 (keeper) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Đề xuất:** `newDeadline = 0`, `to = family`. Sau cấp 2, `checkTimeout` revert với thông báo `"max level"`, và keeper coi đây là tín hiệu ngừng gọi cho sự cố này. Mỗi sự cố tối đa **2 vi phạm**.
- **Quyết định:** ĐÃ CHỐT theo đề xuất. Đã cập nhật AGENTS.md.

## IC-05. `settle` khi hợp đồng chưa bao giờ được chấp nhận
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** mục 6.3 không nói. Nếu không xử lý, tiền của gia đình bị khóa vĩnh viễn trong contract.
- **Đề xuất:** sau `periodEnd`, nếu plan chưa được chấp nhận thì `settle` hoàn **toàn bộ** tiền cho gia đình (`toProvider = 0`). Ngoài ra, `createCarePlan` phải kiểm tra `periodEnd > block.timestamp`, `slaSeconds > 0`, `msg.value > 0`, và `device` khác 0.
- **Lưu ý:** vi phạm chỉ được ghi khi có người gọi `checkTimeout`. Keeper cần chạy đến sau `periodEnd`, nếu không thì sự cố còn `Open` lúc `settle` sẽ không bị tính phạt.
- **Quyết định:** ĐÃ CHỐT theo đề xuất. Đã cập nhật AGENTS.md.

## IC-06. Các ca trực chồng giờ nhau
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** nếu hai ca cùng chứa `ts` thì không rõ ai là người trực chính.
- **Đề xuất:** `commitShift` revert với `"overlap"` nếu khoảng `[start, end)` giao với một ca đã có (vòng lặp tối đa 20 ca). Ngoài ra `primary != backup` và cả hai khác 0. Nếu không có ca nào chứa `ts`, `getOnDuty` trả `(0x0, 0x0)`.
- **Quyết định:** ĐÃ CHỐT theo đề xuất. Đã cập nhật AGENTS.md.

## IC-07. Luật kiểm tra của `confirmArrival` (nonce, cửa sổ thời gian)
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P3 (firmware), P5 (gateway) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Đề xuất:**
  - FALL, ARRIVAL và CANCEL dùng **chung một dãy nonce** của thiết bị. CANCEL cũng tiêu một nonce dù chỉ ghi off-chain, nên nonce trên chain có thể nhảy cóc. Điều đó hợp lệ vì luật là `nonce > lastNonce`, không bắt buộc liên tiếp.
  - ARRIVAL dùng cùng cửa sổ `ts ∈ [block.timestamp − 600, block.timestamp + 60]` như FALL, và phải có `ts ≥ ts của FALL`.
  - Chữ ký phải khôi phục ra đúng `device` của plan chứa sự cố, với `eventType = 2`.
  - Ghi `arrivedAt = block.timestamp`, không dùng `ts`, để thời điểm tính trách nhiệm luôn là thời gian chain thống nhất.
- **Hệ quả cho P5:** gateway phải gửi giao dịch **theo đúng thứ tự nonce**. Nếu gửi ARRIVAL (nonce 43) trước FALL (nonce 42) thì FALL sẽ bị revert.
- **Quyết định:** ĐÃ CHỐT theo đề xuất (nonce chung, gửi đúng thứ tự, ARRIVAL lấy eventId từ receipt của FALL). Đã cập nhật AGENTS.md.

## IC-08. Xác nhận trễ trước khi keeper kịp gọi `checkTimeout`
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 (test) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề:** theo đúng chữ của mục 6.3, `checkTimeout` chỉ chạy khi sự cố chưa được xác nhận. Nếu hạn đã qua mà keeper chưa kịp gọi, nhân viên bấm `acknowledge` ngay lúc đó sẽ **thoát vi phạm**. Đây là lỗ hổng gian lận.
- **Đề xuất (đã cài):** trong `acknowledge` và `confirmArrival` (khi sự cố còn `Open`), nếu `block.timestamp > deadline` và `level < 2` thì contract tự ghi vi phạm và chuyển cấp **trước**, sau đó mới xác nhận. Contract phát đúng các event `Escalated` + `SlaViolation` như khi keeper gọi. Giao diện hàm không đổi.
- **Quyết định:** ĐÃ CHỐT theo đề xuất. Đã cập nhật AGENTS.md.

## IC-09. Tên hàm `getEvent` trùng với hàm có sẵn của ethers v6
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 (test, script), P5 (dashboard) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề (đã chạy thử):** trong ethers v6, mọi object `Contract` đã có sẵn `getEvent(key)` để lấy event log. Gọi `contract.getEvent(1)` sẽ chạy nhầm hàm của ethers và báo lỗi `TypeError: key.format is not a function`. web3.py không bị ảnh hưởng.
- **Phương án A (đề xuất):** đổi tên hàm trong contract thành `getFallEvent(uint256)`. Cách này đơn giản, không ai phải nhớ mẹo.
- **Phương án B:** giữ tên `getEvent`, và mọi code JS phải gọi `contract.getFunction("getEvent")(id)`.
- **Quyết định:** ĐÃ CHỐT phương án A — tên `getFallEvent`. Đã cập nhật AGENTS.md.

## IC-10. Cấu hình compiler bắt buộc cho `hardhat.config.js` (P2)
- **Người đề xuất:** P1 · **Ảnh hưởng:** P2 · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Nội dung:** contract chỉ compile được với cấu hình sau:
  ```js
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" } }
  ```
  - `0.8.24` + `cancun`: OpenZeppelin 5.6.1 (`MessageHashUtils`) yêu cầu `^0.8.24`.
  - `viaIR: true`: `getPlan` / `getFallEvent` trả về 12 giá trị, không có dòng này sẽ báo "stack too deep".
  - Khi verify trên Etherscan cũng phải dùng đúng các thiết lập này.
- **Quyết định:** ĐÃ CHỐT theo cấu hình đề xuất. Đã cập nhật AGENTS.md.

## IC-11. 🔴 Nonce theo thiết bị bị "cướp" qua hợp đồng bù nhìn (lỗ hổng NGHIÊM TRỌNG)
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 (test) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề (đã chạy thử, `contracts/p1_tmp/attacks.js`):** địa chỉ thiết bị là công khai, và chữ ký không chứa `planId`. Trung tâm (hoặc bất kỳ ai) tạo một hợp đồng bù nhìn dùng **cùng địa chỉ thiết bị**, tự chấp nhận, tự cam kết ca. Khi chữ ký FALL thật xuất hiện (MQTT, hoặc mempool trên Sepolia), họ nộp nó vào hợp đồng bù nhìn trước. Nonce của thiết bị bị tiêu, nên gateway nộp vào hợp đồng thật thì bị revert `"old nonce"`. Kết quả chạy: **hợp đồng thật 0 vi phạm, lẽ ra là 2**. ARRIVAL cũng bị cướp được theo cách này.
- **Phương án A (đề xuất):** đổi `lastNonce[device]` thành `lastNonce[planId]` (mỗi plan có đúng 1 thiết bị). Hợp đồng bù nhìn vẫn nhận được bản sao sự kiện, nhưng không làm hỏng hợp đồng thật. Chỉ sửa contract; ESP32, gateway và test vector **không đổi**. Luật trong mục 6.3 đổi từ "`nonce > lastNonce[device]`" thành "`nonce > lastNonce[planId]`".
- **Phương án B:** thêm `planId` vào nội dung được ký. Chặt hơn nhưng phải sửa ESP32, gateway và test vector, rủi ro cao ở giai đoạn này.
- **Quyết định:** ĐÃ CHỐT phương án A — nonce theo `planId`. Đã cập nhật AGENTS.md.

## IC-12. 🟠 Trung tâm gọi `settle` trước khi vi phạm kịp được ghi
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P2 (test, keeper, script demo), P5 (dashboard nếu có nút settle) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề (đã chạy thử):** té ngã lúc `periodEnd − 20 s`, không ai phản hồi. Lúc `periodEnd + 1 s`, hạn chót chưa tới, trung tâm gọi `settle` và nhận trọn 1 ETH. Vi phạm ghi sau đó không còn tác dụng. Tương tự, gateway đang giữ hàng đợi (chain chậm) thì sự cố cuối kỳ chưa kịp lên chain đã bị settle.
- **Phương án A (đề xuất):**
  1. Thêm `pendingEvents` vào `Plan`: +1 khi `reportFall`, −1 khi sự cố rời trạng thái "còn có thể bị phạt" (được nhận / có mặt khi đang `Open`, hoặc lên cấp 2).
  2. `settle` bắt buộc `pendingEvents == 0`. Ai cũng đẩy được bằng `checkTimeout` sau hạn, nên settle không bị khóa vĩnh viễn.
  3. `reportFall` bắt buộc `ts <= periodEnd` (té ngã trong kỳ hợp đồng).
  4. `settle` chỉ chạy sau `periodEnd + TS_PAST_WINDOW` (600 giây) để sự cố trong hàng đợi của gateway kịp lên chain.
  - **Đã cài:** hằng số `SETTLE_DELAY = 600`; `settle` báo `"period not ended"` khi chưa qua `periodEnd + 600`, báo `"pending events"` khi còn sự cố chưa ngã ngũ; `reportFall` báo `"ts after period"`; `getPlan` trả thêm `pendingEvents` ở cuối để dashboard hiển thị lý do chưa settle được.
  - **Hệ quả cho P2 (keeper, script demo):** muốn settle thì phải gọi `checkTimeout` cho các sự cố còn treo cho tới khi `pendingEvents == 0`.
  - **Hệ quả demo:** phải chờ 10 phút sau `periodEnd` mới settle được. Có thể đặt `periodEnd` sớm, hoặc giảm thời gian chờ này cho demo.
- **Phương án B:** chỉ thêm thời gian chờ `periodEnd + 600 + 2 × slaSeconds` và dựa vào keeper gọi `checkTimeout` trong lúc chờ. Code ít hơn nhưng keeper chết thì vẫn lọt.
- **Quyết định:** ĐÃ CHỐT phương án A — `pendingEvents` + `SETTLE_DELAY = 600` + `ts <= periodEnd`; demo dùng hợp đồng kỳ ngắn tạo trước. Đã cập nhật AGENTS.md.

## IC-13. 🟡 Chuyển tiền kiểu "đẩy" có thể bị chặn
- **Người đề xuất:** P1 · **Ảnh hưởng:** P1, P5 (dashboard thêm nút rút) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vấn đề (phân tích code, chưa chạy thử):** `settle` gửi ETH cho cả hai bên trong cùng một giao dịch, và `require(ok)`. Nếu địa chỉ trung tâm hoặc gia đình là một **contract từ chối nhận ETH**, `settle` luôn revert và **tiền của bên kia cũng bị kẹt vĩnh viễn**. Trong demo, cả hai bên đều là ví thường nên không xảy ra.
- **Phương án A (đề xuất):** giữ nguyên, ghi vào báo cáo là giới hạn đã biết. Ưu tiên thấp.
- **Phương án B:** kiểu "rút" (pull): `settle` chỉ ghi `pendingWithdrawal[addr]`, thêm hàm `withdraw()`. Thêm 1 hàm vào giao diện.
- **Quyết định:** ĐÃ CHỐT phương án A (ghi vào báo cáo là giới hạn). Đã cập nhật AGENTS.md.

## IC-14. Định dạng `docs/test_vectors.json`
- **Người đề xuất:** P1 · **Ảnh hưởng:** P5 (sinh file), P3 (so khớp trên ESP32), P1 (test) · **Trạng thái:** **ĐÃ CHỐT** (2026-09-27)
- **Vì sao cần:** AGENTS.md mục 6.2 bắt ESP32, gateway và contract cùng khớp một bộ vector, nhưng chưa quy định định dạng file. Nếu P5 và P1 hiểu khác nhau, test sẽ không đọc được file.
- **Đề xuất:**
  ```json
  {
    "note": "Khóa CHỈ ĐỂ TEST, không dùng cho thiết bị thật",
    "generator": "tools/make_test_vector.py",
    "privateKey": "0x<32 byte hex>",
    "device": "0x<địa chỉ, viết thường>",
    "vectors": [
      {
        "name": "fall_basic",
        "eventType": 1,
        "timestamp": 2000000000,
        "nonce": 42,
        "dataHash": "0x<32 byte>",
        "samples_b64": "<base64 của mẫu int16 LE; chỉ có ở vector có dữ liệu thô>",
        "packed": "0x<69 byte>",
        "messageHash": "0x<32 byte>",
        "ethSigned": "0x<32 byte>",
        "sig": "0x<65 byte: r s v>",
        "v": 28
      }
    ]
  }
  ```
- **Luật cho các vector:**
  1. **Tối thiểu 3 vector** FALL, ARRIVAL, CANCEL (đúng như prompt P5). Nên thêm: một FALL có **nonce > 2^32** (bắt lỗi big-endian `uint64` ghi thiếu byte) và đảm bảo có **cả `v = 27` và `v = 28`** (lỗi xử lý `v` thường chỉ lộ ra ở một nửa số chữ ký).
  2. **`timestamp` phải ở tương lai**, đề xuất `2000000000` (năm 2033). Lý do: test phải tua giờ Hardhat tới đúng `ts` để gọi `reportFall`, mà Hardhat chỉ tua tới được chứ không lùi về quá khứ. Ví dụ `1760000000` trong AGENTS.md (năm 2025) là quá khứ, contract sẽ báo `"ts too old"`.
  3. `nonce >= 1`. ARRIVAL phải có `nonce` **lớn hơn** và `timestamp` **không sớm hơn** một vector FALL, để test gọi được FALL rồi ARRIVAL theo thứ tự.
  4. CANCEL có `dataHash = 0x00…00`. Vector FALL có `samples_b64` thì `dataHash = keccak256(bytes thô)`.
  5. Mọi chuỗi hex viết thường, có tiền tố `0x`. Chữ ký phải là **low-s** (`s <= N/2`), vì OpenZeppelin `ECDSA.recover` từ chối `s` cao. `eth_account` tự làm điều này. **P3 phải kiểm tra thư viện ký trên ESP32** (⚠️ chưa kiểm chứng `trezor-crypto` có tự chuẩn hóa không; test sẽ báo nếu sai).
- **Đối chiếu chéo:** P1 đã có file mẫu `contracts/p1_tmp/sample_test_vectors.json`, sinh bằng ethers (JS) với khóa test `keccak256("carensla test key - DO NOT USE")`. Chữ ký ECDSA ở Ethereum là tất định (RFC 6979). Nên nếu P5 dùng **cùng khóa và cùng input**, file Python của P5 phải ra **từng byte giống hệt** file mẫu. Đây là cách kiểm tra chéo rẻ nhất giữa hai cách cài đặt độc lập.
- **Kiểm tra file:** `cd contracts && npx hardhat test test/signature.vector.test.js`. Test kiểm từng tầng: `packed` → `messageHash` (so với `hashEvent()` của contract) → `ethSigned` → `sig` (low-s, khôi phục ra đúng device) → contract chấp nhận `reportFall` / `confirmArrival` → sửa 1 byte thì bị từ chối.
- **Quyết định:** ĐÃ CHỐT theo đề xuất. Đã cập nhật AGENTS.md.

## IC-15. Thống nhất tên biến môi trường (`.env.example`)
- **Người đề xuất:** P1 (theo yêu cầu trưởng nhóm, 2026-09-27) · **Ảnh hưởng:** P2, P5 · **Trạng thái:** **ĐÃ CHỐT** (P1) — báo P2, P5
- **Vấn đề:** prompt P2 và code P5 dùng tên khác nhau cho cùng một biến, nên gateway và keeper sẽ đọc hai tên khác nhau từ cùng một file `.env`.
- **Quyết định:** lấy danh sách trong prompt P2 làm chuẩn (có trước), giữ thêm các biến riêng của P5.

  | Mục | Prompt P2 | P5 đã dùng | **Tên chốt** |
  |---|---|---|---|
  | RPC | `SEPOLIA_RPC_URL` | `RPC_URL` | **`SEPOLIA_RPC_URL`**; localhost cố định `http://127.0.0.1:8545`, chọn theo `NETWORK` |
  | MQTT | `MQTT_HOST` | `MQTT_BROKER` | **`MQTT_HOST`** |
  | Telegram trung tâm | `TELEGRAM_CHAT_PROVIDER` | `TELEGRAM_CHAT_CENTER` | **`TELEGRAM_CHAT_PROVIDER`** (khớp chữ "provider" trong contract) |

  Danh sách đầy đủ: `NETWORK`, `SEPOLIA_RPC_URL`, `DEPLOYER_PRIVATE_KEY`, `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY`, `ETHERSCAN_API_KEY`, `CONTRACT_ADDRESS` (tùy chọn), `PLAN_ID`, `MQTT_HOST`, `MQTT_PORT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_PRIMARY`, `TELEGRAM_CHAT_BACKUP`, `TELEGRAM_CHAT_FAMILY`, `TELEGRAM_CHAT_PROVIDER`, `REGISTERED_DEVICES`.
- **Đã sửa:** `.env.example` (viết lại theo danh sách trên) và 3 dòng `os.getenv` trong `backend/gateway.py` (chỉ đổi tên biến môi trường, không đổi logic).
- **Code mới từ nay:** Python dùng `os.getenv("<tên chốt>")`, JS dùng `process.env.<tên chốt>`. Cần biến mới thì thêm vào `.env.example` và ghi vào đây.
