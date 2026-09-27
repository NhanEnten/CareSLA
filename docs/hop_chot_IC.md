# Họp chốt giao diện — 4 mục ảnh hưởng nhiều người

> ✅ **ĐÃ CHỐT toàn bộ IC-01 → IC-14 theo đề xuất ngày 2026-09-27; AGENTS.md đã cập nhật.** Mục 6 bên dưới là việc cần làm của từng người.
> Người chủ trì: P1 · Thời lượng: **20 phút** · Tài liệu gốc: `docs/interface_changes.md`
> Cách họp: mỗi mục 4–5 phút. P1 đọc phần "Nói gọn". Người bị ảnh hưởng trả lời các câu hỏi. Chốt phương án và ghi vào ô **Quyết định**.
> 9 mục còn lại (IC-01 → IC-06, IC-08, IC-11, IC-13) chỉ cần cả nhóm gật đầu ở cuối buổi (xem mục 5).

---

## 1. IC-07 — Nonce dùng chung và thứ tự gửi (P3, P5) · 5 phút

**Nói gọn:** mỗi thiết bị có **một bộ đếm nonce duy nhất** cho cả FALL, ARRIVAL và CANCEL. Contract chỉ chấp nhận nonce **lớn hơn** nonce trước đó, được phép nhảy số. Hệ quả là gateway phải gửi lên chain **đúng thứ tự nonce**.

**Ví dụ:**
```
Thiết bị:  FALL(42) ──► CANCEL(43, chỉ off-chain) ──► FALL(44) ──► ARRIVAL(45)
Chain:     FALL(42) ✓                                  FALL(44) ✓   ARRIVAL(45) ✓   (43 bị bỏ qua: hợp lệ)
Nếu gateway gửi ARRIVAL(45) trước FALL(44) → FALL(44) bị từ chối "old nonce" → mất sự cố
```

**Đề xuất:** giữ nguyên như code hiện tại.

**P3 cần làm:** prompt của P3 đã ghi "tăng và lưu nonce trong NVS **trước** khi gửi", nên chỉ cần thêm:
- Dùng **một** bộ đếm cho cả 3 loại sự kiện.
- Chỉ gửi FALL sau khi SNTP đã đồng bộ, vì `ts` chỉ được lệch −600 / +60 giây so với giờ chain.

**P5 cần làm:** prompt của P5 đã có "một hàng đợi, một luồng gửi duy nhất", rất hợp. Cần thêm:
- Hàng đợi xếp theo nonce thiết bị; gửi xong giao dịch trước (có receipt) mới gửi giao dịch sau.
- Phân biệt lỗi: `"old nonce"` và `"ts too old"` thì **bỏ gói, ghi log, không thử lại**. Lỗi mạng hoặc RPC thì thử lại.
- ⚠️ **Điểm mới cần chốt:** gói ARRIVAL **không chứa `eventId`**. Gateway phải tự ghép ARRIVAL với sự cố đang mở. Đề xuất: lấy `eventId` từ event `FallReported` trong receipt của FALL gần nhất của thiết bị đó.
- Nếu FALL không lên chain được (ví dụ lỗi `"no shift"`), ARRIVAL đi sau nó cũng bỏ, chỉ ghi off-chain.

**Câu hỏi cho buổi họp:**
1. P3: firmware có đảm bảo ghi NVS xong rồi mới publish MQTT không? Mất điện giữa chừng thì sao?
2. P5: gateway có chờ receipt của từng giao dịch trước khi gửi giao dịch tiếp theo không?
3. P5: đồng ý cách ghép ARRIVAL → `eventId` ở trên không?

**Quyết định:** ĐÃ CHỐT theo đề xuất (2026-09-27).

---

## 2. IC-09 — Tên hàm `getEvent` trùng với ethers v6 (P2, P5) · 4 phút

**Nói gọn:** trong **ethers v6 (JavaScript)**, mọi đối tượng contract đã có sẵn hàm `getEvent` dùng để lấy event log. Gọi `contract.getEvent(1)` sẽ chạy nhầm hàm của ethers và báo lỗi `key.format is not a function`. P1 đã gặp lỗi này khi chạy thử. **Python (web3.py) không bị**, nên `keeper.py` và `gateway.py` không ảnh hưởng.

**Ai bị ảnh hưởng:** test của P2 (JS), dashboard của P5 (JS).

**Phương án:**
- **A (đề xuất): đổi tên thành `getFallEvent`.** Hiện chưa ai viết code gọi hàm này nên đổi gần như không tốn gì, và sau này không ai phải nhớ mẹo.
- **B:** giữ tên `getEvent`, và mọi code JS phải gọi `contract.getFunction("getEvent")(id)`. Quên một lần là lỗi khó hiểu, dễ mất thời gian lúc tích hợp.

**Nếu chọn A:** P1 sửa contract và AGENTS.md mục 6.3. P2 cập nhật prompt dòng keeper ("đọc `getEvent(i)`" → `getFallEvent(i)`).

**Câu hỏi:** P2, P5 có phản đối đổi tên không?

**Quyết định:** ĐÃ CHỐT theo đề xuất (2026-09-27).

---

## 3. IC-10 — Cấu hình compiler bắt buộc (P2) · 3 phút

**Nói gọn:** contract **chỉ compile được** khi `hardhat.config.js` có đúng các thiết lập sau:
```js
solidity: {
  version: "0.8.24",
  settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" },
},
```
- `0.8.24` + `cancun`: OpenZeppelin 5.6.1 (`MessageHashUtils`) yêu cầu phiên bản này.
- `viaIR: true`: `getPlan` và `getEvent` trả về 12 giá trị. Thiếu dòng này thì báo lỗi "stack too deep".

**P2 cần làm:** file `contracts/hardhat.config.js` hiện là bản tạm của P1. P2 viết lại (thêm mạng `sepolia`, Etherscan verify, gas reporter) nhưng **giữ nguyên khối `solidity` trên**. Khi verify trên Etherscan cũng phải dùng đúng các thiết lập này, nếu không verify sẽ thất bại.

**Phương án khác (không đề xuất):** bỏ `viaIR` bằng cách cho `getPlan`/`getEvent` trả về struct. Cách này làm đổi IC-01 và cách đọc dữ liệu ở dashboard.

**Câu hỏi:** P2 thấy ổn không? Máy P2 dùng Node bản mấy? Hardhat cảnh báo Node 18, nên dùng Node 20 hoặc 22.

**Quyết định:** ĐÃ CHỐT theo đề xuất (2026-09-27).

---

## 4. IC-12 — Luật mới cho `settle` (P2, P5) · 6 phút

**Nói gọn:** để chặn trung tâm chia tiền sớm nhằm né phạt, `settle` giờ có 2 điều kiện mới:
1. Phải qua `periodEnd` **+ 600 giây**, để sự cố còn trong hàng đợi của gateway kịp lên chain.
2. Không còn sự cố treo (`pendingEvents == 0`). Sự cố treo là sự cố chưa ai nhận và chưa lên cấp 2. Ai cũng đẩy được sự cố treo bằng `checkTimeout`.

Ngoài ra, `reportFall` từ chối té ngã có `ts` sau `periodEnd`.

**⚠️ Mâu thuẫn với prompt hiện tại, cần sửa:**

| Ở đâu | Đang ghi | Phải sửa thành |
|---|---|---|
| Prompt P2, test số 13 | "`settle` trước `periodEnd` → revert" | Trước `periodEnd + 600` → `"period not ended"`; còn sự cố treo → `"pending events"` |
| Prompt P2, keeper | "chưa xác nhận mà quá `deadline` thì gửi `checkTimeout`" | Chỉ gửi khi `status == 0` **và `level < 2`**. Sự cố ở cấp 2 có `deadline = 0`; không kiểm `level` thì keeper sẽ gọi mãi và revert `"max level"` mãi, tốn gas |
| Prompt P5, dashboard | "Nút Settle hiện khi đã qua `periodEnd`" | Hiện khi đã qua `periodEnd + 600` **và** `pendingEvents == 0` (giá trị cuối của `getPlan`) |

**Vấn đề demo:** `demo_setup.js` của P2 đặt `periodEnd` = hiện tại + 2 giờ, nên không thể settle trong buổi demo trực tiếp. Phương án:
- **A (đề xuất, không sửa code):** `demo_setup.js` tạo thêm **hợp đồng thứ 2 có kỳ ngắn**, chạy khoảng 20–30 phút trước giờ demo (có vài sự cố đã quá hạn). Đến lúc demo, hợp đồng này đã hết kỳ, và bấm Settle trực tiếp cho giảng viên xem tiền được chia.
- **B:** đổi `SETTLE_DELAY` thành tham số truyền vào lúc deploy (local 60 giây, Sepolia 600 giây). Phải sửa contract và script deploy.
- **C:** phần settle chỉ chiếu trong video quay sẵn.

**Câu hỏi:**
1. P2: đồng ý phương án demo A không? Có thêm được hợp đồng thứ 2 vào `demo_setup.js` không?
2. P5: dashboard hiển thị được lý do chưa settle được không, ví dụ "còn 2 sự cố treo"?

**Quyết định:** ĐÃ CHỐT theo đề xuất (2026-09-27).

---

## 5. Các mục còn lại: chỉ cần gật đầu (2 phút)

| Mã | Nội dung | Đồng ý? |
|---|---|---|
| IC-01 | Thứ tự giá trị trả về của `getPlan` (12 giá trị) / `getFallEvent` (12 giá trị); ID bắt đầu từ 1 | ✅ |
| IC-02 | Được xác nhận có mặt khi chưa bấm nhận | ✅ |
| IC-03 | SLA chỉ tính tới lúc nhận (ghi vào báo cáo là giới hạn) | ✅ |
| IC-04 | Cấp 2: `newDeadline = 0`, sau đó `checkTimeout` báo `"max level"` | ✅ |
| IC-05 | Hợp đồng chưa được chấp nhận thì `settle` hoàn toàn bộ tiền cho gia đình | ✅ |
| IC-06 | Cấm ca chồng giờ; primary ≠ backup | ✅ |
| IC-08 | Bấm nhận trễ vẫn bị ghi vi phạm | ✅ |
| IC-11 | Nonce tính theo hợp đồng (vá lỗ hổng hợp đồng bù nhìn) | ✅ |
| IC-13 | Chuyển tiền kiểu "đẩy": ghi vào báo cáo là giới hạn | ✅ |

## 6. Gợi ý sửa cụ thể (áp dụng **sau khi** chốt theo phương án đề xuất)

> Mỗi người tự sửa prompt và code của mình (theo quyền sở hữu ở AGENTS.md mục 7). Có thể dán nguyên mục của mình cho agent.
> Code JS đã được P1 chạy thử trên Hardhat (`contracts/p1_tmp/short_plan_check.js`). Code Python **⚠️ chưa chạy thử**, nên kiểm tra lại với web3.py v7 đã cài.

### 6.1 P2 — `prompts/P2_test_deploy_keeper.md` và code

**a) Test số 13.** Thay dòng:
> 13. `settle` trước `periodEnd` → revert; sau đó chia đúng số tiền; gọi lần 2 → revert.

bằng:
> 13. `settle` trước `periodEnd + 600` → revert `"period not ended"`; còn sự cố treo → revert `"pending events"`; sau khi `checkTimeout` đưa hết sự cố lên cấp 2 (hoặc đã được nhận) thì chia đúng số tiền; gọi lần 2 → revert `"already settled"`.
> 15. Hợp đồng bù nhìn dùng chung địa chỉ thiết bị không làm hợp đồng thật bị `"old nonce"` (IC-11).
> 16. `reportFall` với `ts > periodEnd` → revert `"ts after period"`.

**b) Keeper.** Thay dòng:
> Sự cố nào chưa xác nhận mà đã quá `deadline` thì gửi `checkTimeout(i)`

bằng:
> Chỉ gửi `checkTimeout(i)` khi `status == 0` **và** `level < 2` **và** giờ chain > `deadline`. Lấy giờ từ block mới nhất, không dùng giờ máy. Revert `"not expired"` / `"not open"` / `"max level"` là bình thường: ghi log rồi bỏ qua.

Code mẫu ⚠️ chưa chạy thử:
```python
now = w3.eth.get_block("latest")["timestamp"]          # giờ chain, không dùng time.time()
for i in range(1, contract.functions.eventCount().call() + 1):
    e = contract.functions.getFallEvent(i).call()      # tên mới theo IC-09
    deadline, level, status = e[6], e[7], e[8]         # thứ tự theo IC-01
    if status == 0 and level < 2 and now > deadline:
        send_tx(contract.functions.checkTimeout(i))    # hàm gửi giao dịch của keeper
```

**c) `demo_setup.js`: thêm hợp đồng kỳ ngắn để settle trực tiếp khi demo.** Thêm vào prompt:
> - Tạo thêm **hợp đồng thứ 2 kỳ 5 phút** dùng một thiết bị mẫu (khóa sinh ngẫu nhiên trong script), cam kết 1 ca, chờ ca bắt đầu rồi báo 1 sự cố đã ký. Chạy script **≥ 20 phút trước giờ demo** và để keeper chạy. Đến giờ demo, hợp đồng này đã qua `periodEnd + 600`, sự cố đã lên cấp 2 (2 vi phạm), bấm Settle trực tiếp.

Code mẫu đã chạy thử (trên Sepolia, thay `time.increase` bằng chờ thật khoảng 40 giây):
```js
async function setupShortPlan(c, family, provider, primary, backup) {
  const now = (await ethers.provider.getBlock("latest")).timestamp;
  const periodEnd = now + 5 * 60;                                  // kỳ 5 phút
  const demoDevice = ethers.Wallet.createRandom();                 // thiết bị mẫu cho hợp đồng này
  const tx = await c.connect(family).createCarePlan(provider.address, demoDevice.address, 60,
    ethers.parseEther("0.002"), periodEnd, { value: ethers.parseEther("0.01") });
  const planId = (await tx.wait()).logs.map((l) => c.interface.parseLog(l))
    .find((l) => l?.name === "PlanCreated").args.planId;
  await (await c.connect(provider).acceptPlan(planId)).wait();
  await (await c.connect(provider).commitShift(planId, now + 30, periodEnd, primary.address, backup.address)).wait();
  return { planId, periodEnd, demoDevice };
}
```
Hàm `reportDemoFall` (ký bằng `demoDevice.signMessage`) nằm trong `contracts/p1_tmp/short_plan_check.js`.

**d) Test JS và keeper:** dùng `getFallEvent(id)` (IC-09 đã chọn A). Sửa dòng keeper trong prompt: "đọc `getEvent(i)`" → "đọc `getFallEvent(i)`".

### 6.2 P5 — `prompts/P5_backend_dashboard_baocao.md` và code

**a) Nút Settle.** Thay:
> Nút "Settle" hiện khi đã qua `periodEnd`.

bằng:
> Nút "Settle" chỉ hiện khi chưa settle, giờ chain > `periodEnd + 600` và `pendingEvents == 0`. Nếu chưa đủ điều kiện thì hiện lý do (còn bao lâu / còn mấy sự cố treo).

Code mẫu (điều kiện đã chạy thử):
```js
const plan = await contract.getPlan(planId);               // có tên trường nhờ ABI
const now = (await provider.getBlock("latest")).timestamp; // giờ chain
const settleAt = Number(plan.periodEnd) + 600;
if (plan.settled)                  showStatus("Đã chia tiền");
else if (now <= settleAt)          showStatus(`Chia tiền được sau ${settleAt - now} giây`);
else if (plan.pendingEvents > 0n)  showStatus(`Còn ${plan.pendingEvents} sự cố chưa ngã ngũ`);
else                               showSettleButton();
```

**b) Gateway: thứ tự và phân loại lỗi.** Thêm vào mục "Gateway gửi giao dịch lên chain":
> - Hàng đợi giữ đúng thứ tự nonce thiết bị. Chờ receipt của giao dịch trước rồi mới gửi giao dịch sau.
> - Lỗi `"old nonce"`, `"ts too old"`, `"ts in future"`, `"ts after period"`, `"no shift"`, `"bad sig"`, `"settled"`, `"already arrived"`: **bỏ gói**, ghi SQLite, không thử lại. Lỗi mạng hoặc RPC thì thử lại.

**c) Gateway: ghép ARRIVAL với `eventId`.** Thêm:
> - Sau khi `reportFall` thành công, đọc `eventId` từ event `FallReported` trong receipt và nhớ theo thiết bị. ARRIVAL của thiết bị đó dùng `eventId` này. Không có FALL nào đang mở trên chain thì ARRIVAL chỉ ghi off-chain.

Code mẫu ⚠️ chưa chạy thử:
```python
open_event = {}   # địa chỉ thiết bị (viết thường) -> eventId của FALL đang mở trên chain

# sau khi reportFall thành công
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
open_event[device] = contract.events.FallReported().process_receipt(receipt)[0]["args"]["eventId"]

# khi nhận ARRIVAL
event_id = open_event.get(device)
if event_id is None:
    log_offchain(msg, note="ARRIVAL không có FALL trên chain")   # không gửi giao dịch
else:
    queue.put(("confirmArrival", event_id, msg))                 # xóa khỏi open_event khi gửi thành công
```

**d) Dashboard:** gọi `contract.getFallEvent(id)` (IC-09 đã chọn A).

### 6.3 P3 — `prompts/P3_iot_esp32.md`
Thêm vào dòng "Nonce lưu trong NVS":
> Dùng **một bộ đếm duy nhất** cho FALL, ARRIVAL và CANCEL. CANCEL cũng tăng nonce.

Không cần sửa gì khác: prompt P3 đã có "chờ SNTP đồng bộ xong mới gửi sự kiện" và "tăng, lưu nonce trước khi gửi".

### 6.4 P1 — sau khi chốt
- ✅ IC-09: đã đổi `getEvent` → `getFallEvent` trong contract, script tạm và `team_updates.md`. Còn AGENTS.md mục 6.3 (chờ nhóm xác nhận).
- AGENTS.md mục 6.3: `lastNonce[device]` → `lastNonce[planId]`; thêm luật `settle` (`periodEnd + 600`, `pendingEvents == 0`); thêm `ts <= periodEnd` cho `reportFall`; ghi rõ các giá trị trả về của `getPlan` / `getEvent`.

## 7. Sau buổi họp
- **P1:** cập nhật AGENTS.md mục 6.3, đổi trạng thái các mục trong `interface_changes.md`, sửa contract nếu cần, và cập nhật `docs/team_updates.md`.
- **P2, P5:** sửa các dòng mâu thuẫn trong prompt của mình (bảng ở mục 4).
- **Cả nhóm:** `git pull` bản mới trước khi làm tiếp.
