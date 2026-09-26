# Cập nhật chung cho cả nhóm

> **Dành cho mọi AI agent trong nhóm.** Đọc file này ngay **sau** `AGENTS.md`, trước prompt riêng `prompts/Px_*.md`.
> Bản cập nhật mới nhất nằm trên cùng. Nếu nội dung ở đây mâu thuẫn với `AGENTS.md`, **`AGENTS.md` thắng**, trừ các mục ghi rõ "ĐÃ CHỐT". Khi đó hãy báo người dùng để P1 cập nhật `AGENTS.md`.
> Các mục còn **CHỜ CHỐT** không phải luật chính thức. Đừng tự cài theo chúng nếu không thuộc phần của bạn. Hỏi người dùng trước.

---

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
| IC-01 | Thứ tự các giá trị trả về của `getPlan` / `getEvent`; ID bắt đầu từ 1 | P2, P5 | Có |
| IC-02 | `confirmArrival` được gọi khi chưa `acknowledge` | P2, P3, P5 | Có |
| IC-03 | SLA chỉ tính tới lúc nhận, không tính tới lúc có mặt (giới hạn, ghi báo cáo) | Báo cáo | — |
| IC-04 | Lên cấp 2: `newDeadline = 0`; `checkTimeout` sau đó báo `"max level"` | P2 (keeper), P5 | Có |
| IC-05 | Hợp đồng chưa được chấp nhận thì `settle` hoàn toàn bộ cho gia đình | P2 | Có |
| IC-06 | Cấm ca trực chồng giờ; primary ≠ backup | P2 | Có |
| IC-07 | FALL / ARRIVAL / CANCEL dùng **chung một dãy nonce**, được nhảy số; gateway gửi đúng thứ tự nonce | **P3, P5** | Có |
| IC-08 | Bấm nhận trễ (trước khi keeper gọi) vẫn bị ghi vi phạm | P2 | Có |
| IC-09 | Tên `getEvent` trùng với hàm có sẵn của ethers v6; đề xuất đổi thành `getFallEvent` | **P2, P5** | Chưa đổi tên |
| IC-10 | Cấu hình compiler bắt buộc (`viaIR: true`...) | **P2** | Có (config tạm) |
| IC-11 | 🔴 Nonce tính theo `planId`, không theo thiết bị (vá lỗ hổng hợp đồng bù nhìn) | P2, P5 | Có |
| IC-12 | 🟠 `settle` chờ `periodEnd + 600 s` và không còn sự cố treo; `reportFall` chỉ nhận `ts <= periodEnd` | **P2**, P5 | Có |
| IC-13 | 🟡 Chuyển tiền kiểu "đẩy" có thể bị chặn nếu một bên là contract (ghi báo cáo) | Báo cáo | — |

### 3. Việc cần làm theo từng người

**P2 — Test, deploy, keeper**
- `hardhat.config.js` và `.gitignore` trong `contracts/` hiện là **file tạm** do P1 dựng. Bạn sở hữu chúng và có thể thay, nhưng **phải giữ** cấu hình compiler sau, nếu không contract không compile được:
  ```js
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" } }
  ```
- Đã cài sẵn: `hardhat@2.29.1`, `@nomicfoundation/hardhat-toolbox@5.0.0`, `ethers@6.17.0`, `@openzeppelin/contracts@5.6.1`.
- Trong test JS, gọi hàm đọc sự cố bằng `contract.getFunction("getEvent")(id)`, **không** dùng `contract.getEvent(id)` (IC-09).
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
  - Gọi `contract.getFunction("getEvent")(id)`, không dùng `contract.getEvent(id)` (IC-09).
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
