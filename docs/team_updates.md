# Cập nhật chung cho cả nhóm

> **Dành cho mọi AI agent trong nhóm.** Đọc file này ngay **sau** `AGENTS.md`, trước prompt riêng `prompts/Px_*.md`.
> Bản cập nhật mới nhất nằm trên cùng. Nếu nội dung ở đây mâu thuẫn với `AGENTS.md`, **`AGENTS.md` thắng**, trừ các mục ghi rõ "ĐÃ CHỐT". Khi đó hãy báo người dùng để P1 cập nhật `AGENTS.md`.
> Chi tiết họp và gợi ý sửa từng người: `docs/hop_chot_IC.md` (mục 6).
> Từ 2026-09-27, IC-01 → IC-15 đều **ĐÃ CHỐT** và đã nằm trong AGENTS.md. Mục IC mới (nếu có) còn CHỜ CHỐT thì không phải luật chính thức.

---

## [2026-09-27, lần 5] ✅ Đã merge `p5-backend` (commit `b307696`)
- **Có gì mới:** gateway gửi `reportFall`/`confirmArrival` qua hàng đợi có thử lại, theo dõi `Escalated` để báo Telegram cấp 1/2, dashboard (`dashboard/`), tài liệu ôn của P5. Mọi người `git pull`.
- **P1 đã chạy lại thật** 6 tiêu chí trong `docs/review/P5_review_2026-09-27.md` mục 4: **đạt cả 6** (chuyển cấp có báo, RPC lỗi 10 s vẫn gửi lại đúng thứ tự, gói rác không làm sập gateway, ARRIVAL mồ côi bỏ 1 lần).
- **Chạy dashboard:** đứng ở **gốc repo** `python -m http.server 8000`, mở `http://127.0.0.1:8000/dashboard/` (hợp đồng kỳ ngắn: `?plan=2`).
- **P5 còn việc (không chặn merge, sửa trước Mốc 2):** lỗi 10–13 ở mục 5 file review. Quan trọng nhất: **revert lạ làm kẹt cả hàng đợi** và gateway nhận chữ ký high-s mà contract từ chối.
- **P3 lưu ý:** chữ ký ESP32 **bắt buộc low-s** (IC-14). Hiện một chữ ký high-s sẽ làm gateway kẹt hàng đợi cho tới khi P5 sửa lỗi 10–11.

## [2026-09-27, lần 4] Review `p5-backend` (commit `7884436`): CHƯA MERGE
- **P5 đọc ngay `docs/review/P5_review_2026-09-27.md`.** P1 đã chạy thật gateway với Hardhat node local: luồng FALL → `reportFall` và ARRIVAL → `confirmArrival` **chạy đúng**, nhưng còn 3 lỗi 🔴:
  1. Theo dõi `Escalated` dùng `fromBlock`/`toBlock`, web3 v7 không nhận → **không bao giờ gửi Telegram chuyển cấp** (lỗi bị `except: pass` che).
  2. RPC lỗi tạm thời → **FALL bị bỏ, không thử lại** (vi phạm AGENTS.md mục 3).
  3. Gói MQTT thiếu trường → lỗi thoát khỏi callback → **paho 2.1 làm sập gateway**.
- Thêm 🟠: ARRIVAL không có FALL trên chain bị lặp mãi trong hàng đợi; dashboard chạy theo README (`--directory dashboard`) bị 404 file `deployments/localhost.json`, **không kết nối được**.
- Hướng sửa và tiêu chí merge nằm trong file review. P5 sửa xong, đẩy lên `p5-backend`, báo P1 kiểm tra lại.

## [2026-09-27, lần 3] Đã merge `p2-test` vào `main`
- **Có gì mới:** test nghiệp vụ của P2 (38 test), `scripts/deploy.js`, `demo_setup` (có hợp đồng kỳ ngắn `--short-plan`), `backend/keeper.py`, ABI trong `backend/abi/` và `dashboard/`, README, báo cáo P2. Chạy lệnh theo README.
- **P1 đã kiểm tra trước khi merge:** không động file của P1/P5; không lộ khóa; giữ cấu hình compiler IC-10 và tên biến IC-15; ABI khớp 100% contract. Kết quả tự chạy lại: **66/66 test JS** (gồm 24 test chữ ký) và **20/20 unit test keeper**.
- **Mọi người sau khi `git pull`:** chạy `cd contracts && npm ci`, vì `hardhat-toolbox` đã lên 6.1.0 (vẫn là Hardhat 2).
- ⚠️ **Node:** `package.json` yêu cầu Node ≥ 22, và bộ máy Hardhat (`edr`) cần Node ≥ 20. Node 18 vẫn chạy được nhưng có cảnh báo. **Nên cài Node 22 LTS** để tránh lỗi khó hiểu lúc demo.
- **P5:** ABI đã có sẵn ở `backend/abi/CareSLA.json` và `dashboard/CareSLA.json`, địa chỉ local ở `deployments/localhost.json` (tạm, restart node thì deploy lại).
- **Còn thiếu để đạt Mốc 2:** keeper gửi giao dịch thật trên node local; gateway gọi contract (P5); firmware (P3); `docs/ai_input_spec.md` (P4); chạy E2E 3 lần.

## [2026-09-27, lần 2] ✅ ĐÃ CHỐT IC-01 → IC-14, AGENTS.md đã cập nhật
- Trưởng nhóm chốt **toàn bộ IC-01 → IC-14 theo đề xuất** (IC-15 đã chốt trước đó). Contract hiện tại **chính là** bản đã chốt, không có gì phải sửa thêm.
- **AGENTS.md đã được cập nhật** cho khớp code (đã đối chiếu tự động với ABI): mục 5 (phiên bản + cấu hình compiler), 6.2 (nonce chung, low-s, test vector), 6.3 (chữ ký hàm đầy đủ, `getFallEvent`, `lastNonce(planId)`, luật `settle` mới, mọi luật chi tiết), 6.5 (tên biến môi trường).
- **Mọi agent:** `git pull` rồi đọc lại AGENTS.md mục 6. Nếu prompt riêng mâu thuẫn với AGENTS.md thì **AGENTS.md thắng**.
- **Việc cụ thể từng người phải làm theo:** `docs/hop_chot_IC.md` mục 6 (P2: test 13, keeper `level < 2`, `demo_setup.js` hợp đồng kỳ ngắn; P5: nút Settle, thứ tự nonce, ghép ARRIVAL → eventId; P3: bộ đếm nonce chung, low-s).

## [2026-09-27] P1 — Đã merge `p5-backend`, chữ ký gateway ↔ contract khớp, thống nhất tên biến môi trường
- **Merge:** nhánh `p5-backend` đã vào `main`. Mọi người `git pull`.
- ✅ **Test vector:** `docs/test_vectors.json` của P5 giống từng byte với file mẫu của P1. `npx hardhat test test/signature.vector.test.js`: **24/24 đạt**. Còn chờ ESP32 (P3) so khớp.
- **IC-15 — tên biến môi trường đã chốt** (chi tiết trong `docs/interface_changes.md`). 3 tên đổi:
  - `RPC_URL` → **`SEPOLIA_RPC_URL`** (localhost cố định `127.0.0.1:8545`, chọn theo `NETWORK`)
  - `MQTT_BROKER` → **`MQTT_HOST`**
  - `TELEGRAM_CHAT_CENTER` → **`TELEGRAM_CHAT_PROVIDER`**
  - **P5:** P1 đã sửa sẵn 3 dòng `os.getenv` trong `backend/gateway.py` (không đổi logic). Ai đã có file `.env` thì đổi tên 3 biến trên.
  - **P2:** `.env.example` (file của bạn) đã được viết lại đủ danh sách trong prompt P2 cộng biến riêng của P5. `hardhat.config.js` và `keeper.py` dùng đúng các tên này.

## [2026-09-26, lần 2] P1 chọn phương án A cho IC-07, IC-09, IC-12
- **IC-09:** hàm `getEvent` đã **đổi tên thành `getFallEvent`**, tham số và giá trị trả về giữ nguyên. Ai viết code đọc sự cố (test P2, keeper P2, gateway/dashboard P5) dùng tên mới.
- **IC-07, IC-12:** giữ như code hiện tại. Việc cụ thể của từng người nằm ở `docs/hop_chot_IC.md` mục 6.
- Vẫn chờ cả nhóm xác nhận. AGENTS.md mục 6.3 **chưa** được sửa.
- **Mới — IC-14 (định dạng `docs/test_vectors.json`):** xem `docs/interface_changes.md`. Test của P1 đã sẵn sàng: `contracts/test/signature.vector.test.js` (24 test đạt với file mẫu `contracts/p1_tmp/sample_test_vectors.json`).
  - **P5:** sinh file theo IC-14. Lưu ý `timestamp` ở tương lai (đề xuất `2000000000`). Chạy thử `cd contracts && npx hardhat test test/signature.vector.test.js`. Dùng cùng khóa và input với file mẫu thì chữ ký phải giống hệt từng byte.
  - **P3:** chữ ký ESP32 phải là **low-s**, nếu không contract từ chối (đã chạy thử). So từng tầng `packed` → `messageHash` → `ethSigned` → `sig` với file vector.

## [2026-09-26] P1 — Contract đã chạy được, 13 điểm giao diện cần chốt

### 1. Trạng thái hiện tại
- `contracts/contracts/CareSLA.sol` đã có **đủ mọi hàm** trong AGENTS.md mục 6.3. `npx hardhat compile` không lỗi.
- Luồng chạy thử trên Hardhat local đã thông: tạo hợp đồng → chấp nhận → cam kết ca → báo té → quá hạn/chuyển cấp → nhận → có mặt → chia tiền.
- Đã rà checklist bảo mật và vá 2 lỗ hổng (IC-11, IC-12).
- Chưa kiểm chứng: chữ ký từ ESP32 thật (chờ `docs/test_vectors.json` của P5), số gas (chờ P2).

Chạy thử:
```bash
cd contracts
npm install
npx hardhat compile
npx hardhat run p1_tmp/smoke.js     # luồng chính
npx hardhat run p1_tmp/attacks.js   # các kịch bản tấn công
```

### 2. Các điểm giao diện cần cả nhóm chốt
Chi tiết từng mục (vấn đề, phương án, lý do) nằm trong `docs/interface_changes.md`. Contract **đang cài theo phương án đề xuất** của mọi mục có ghi "Có" ở cột Code.

| Mã | Nội dung đề xuất | Ảnh hưởng | Code |
|---|---|---|---|
| IC-01 | Thứ tự các giá trị trả về của `getPlan` / `getFallEvent`; ID bắt đầu từ 1 | P2, P5 | Có |
| IC-02 | `confirmArrival` được gọi khi chưa `acknowledge` | P2, P3, P5 | Có |
| IC-03 | SLA chỉ tính tới lúc nhận, không tính tới lúc có mặt (giới hạn, ghi báo cáo) | Báo cáo | — |
| IC-04 | Lên cấp 2: `newDeadline = 0`; `checkTimeout` sau đó báo `"max level"` | P2 (keeper), P5 | Có |
| IC-05 | Hợp đồng chưa được chấp nhận thì `settle` hoàn toàn bộ cho gia đình | P2 | Có |
| IC-06 | Cấm ca trực chồng giờ; primary ≠ backup | P2 | Có |
| IC-07 | FALL / ARRIVAL / CANCEL dùng **chung một dãy nonce**, được nhảy số; gateway gửi đúng thứ tự nonce | **P3, P5** | Có |
| IC-08 | Bấm nhận trễ (trước khi keeper gọi) vẫn bị ghi vi phạm | P2 | Có |
| IC-09 | Tên `getEvent` trùng với hàm có sẵn của ethers v6 → **đã đổi thành `getFallEvent`** | **P2, P5** | Có |
| IC-10 | Cấu hình compiler bắt buộc (`viaIR: true`...) | **P2** | Có (config tạm) |
| IC-11 | 🔴 Nonce tính theo `planId`, không theo thiết bị (vá lỗ hổng hợp đồng bù nhìn) | P2, P5 | Có |
| IC-12 | 🟠 `settle` chờ `periodEnd + 600 s` và không còn sự cố treo; `reportFall` chỉ nhận `ts <= periodEnd` | **P2**, P5 | Có |
| IC-13 | 🟡 Chuyển tiền kiểu "đẩy" có thể bị chặn nếu một bên là contract (ghi báo cáo) | Báo cáo | — |
| IC-14 | Định dạng `docs/test_vectors.json` (timestamp ở tương lai, có cả v = 27/28, low-s) | **P5, P3** | Test sẵn sàng |

### 3. Việc cần làm theo từng người

**P2 — Test, deploy, keeper**
- `hardhat.config.js` và `.gitignore` trong `contracts/` hiện là **file tạm** do P1 dựng. Bạn sở hữu chúng và có thể thay, nhưng **phải giữ** cấu hình compiler sau, nếu không contract không compile được:
  ```js
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" } }
  ```
- Đã cài sẵn: `hardhat@2.29.1`, `@nomicfoundation/hardhat-toolbox@5.0.0`, `ethers@6.17.0`, `@openzeppelin/contracts@5.6.1`.
- Hàm đọc sự cố giờ tên là **`getFallEvent(id)`** (IC-09). Test JS gọi `contract.getFallEvent(id)`. Keeper Python: `contract.functions.getFallEvent(i).call()`. Prompt P2 đang ghi `getEvent(i)` ở phần keeper, hãy đổi theo.
- Keeper:
  - `checkTimeout` báo `"not expired"`: chưa tới hạn, thử lại sau.
  - Báo `"not open"` hoặc `"max level"`: sự cố đã xong, **ngừng gọi** cho sự cố đó.
- Script demo và `settle`:
  - `settle` chỉ chạy sau `periodEnd + 600` giây, nên đặt `periodEnd` sớm trong demo.
  - Nếu `settle` báo `"pending events"`: gọi `checkTimeout` cho các sự cố còn treo cho tới khi `getPlan(...).pendingEvents == 0`.
- `contracts/p1_tmp/` là script tạm của P1. Có thể tham khảo khi viết test, xóa được khi đã có test chính thức.

**P3 — ESP32**
- Mọi loại sự kiện (FALL, ARRIVAL, CANCEL) dùng **chung một bộ đếm nonce** lưu trong NVS. CANCEL cũng tiêu một nonce (IC-07).
- `ts` gửi lên phải lệch không quá **−600 / +60 giây** so với giờ chain, nên SNTP phải đồng bộ trước khi gửi FALL.
- Cách băm và ký trong AGENTS.md mục 6.2 **không đổi**.

**P4 — AI**
- Không có thay đổi ảnh hưởng tới bạn.

**P5 — Gateway, dashboard, test vector**
- Gateway phải gửi giao dịch lên chain **đúng thứ tự nonce**. Gửi ARRIVAL (nonce 43) trước FALL (nonce 42) thì FALL sẽ bị từ chối.
- Hàng đợi của gateway phải gửi xong sự cố trong vòng **10 phút** kể từ `ts`, nếu không contract báo `"ts too old"`.
- Dashboard (ethers v6):
  - Hàm đọc sự cố tên là **`getFallEvent(id)`** (IC-09). Gọi `contract.getFallEvent(id)`.
  - `getPlan` trả về 12 giá trị, giá trị cuối là `pendingEvents`.
  - `status`: 0 = Open, 1 = Acknowledged, 2 = Arrived. `level`: 0 = primary, 1 = backup, 2 = đã báo gia đình.
- `lastNonce` giờ tra theo **planId** (`lastNonce(uint256)`), không theo địa chỉ thiết bị.
- P1 đang chờ `docs/test_vectors.json` để viết `test/signature.vector.test.js`.

### 4. Các thông báo lỗi của contract
Để debug nhanh khi giao dịch bị từ chối:

| Thông báo | Hàm | Nghĩa |
|---|---|---|
| `no plan` / `no event` | nhiều hàm | ID không tồn tại (ID bắt đầu từ 1) |
| `not provider` | `acceptPlan`, `commitShift` | Người gọi không phải trung tâm của hợp đồng |
| `not accepted` | `commitShift`, `reportFall` | Trung tâm chưa chấp nhận hợp đồng |
| `start in past` | `commitShift` | Ca phải bắt đầu sau thời điểm hiện tại |
| `overlap` / `too many shifts` | `commitShift` | Ca chồng giờ / đã đủ 20 ca |
| `ts too old` / `ts in future` | `reportFall`, `confirmArrival` | `ts` lệch quá −600 / +60 giây so với giờ chain |
| `ts after period` | `reportFall` | Té ngã sau khi hết kỳ hợp đồng |
| `old nonce` | `reportFall`, `confirmArrival` | Nonce không lớn hơn nonce đã dùng của hợp đồng này |
| `bad sig` | `reportFall`, `confirmArrival` | Chữ ký không khôi phục ra địa chỉ thiết bị. So từng tầng: bytes packed → `messageHash` (dùng `hashEvent`) → `ethSigned` → `sig` |
| `no shift` | `reportFall` | Không có ca nào chứa `ts` |
| `not on duty` | `acknowledge` | Người gọi không phải primary/backup của sự cố |
| `not open` / `max level` / `not expired` | `checkTimeout` | Sự cố đã xong / đã lên cấp 2 / chưa tới hạn |
| `period not ended` / `pending events` / `already settled` | `settle` | Chưa qua `periodEnd + 600` / còn sự cố treo / đã chia tiền |
