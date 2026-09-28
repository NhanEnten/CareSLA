# Prompt — Trang thiết lập hợp đồng trên dashboard, demo trọn quy trình trong 10 phút

Bạn là agent hỗ trợ **P6** (người hoàn thiện demo, do trưởng nhóm P1 giao). Nhiệm vụ: thêm **trang thiết lập** vào dashboard để người xem thấy từng bước blockchain làm trọng tài (gia đình khóa tiền → trung tâm chấp nhận → cam kết ca trực trước → giám sát), rồi chạy **toàn bộ demo trong ≤ 10 phút** trên **Hardhat local**. Tự viết code, chạy thử, chỉ báo xong khi đã chạy được.

## 0. Đọc gì trước (đọc đủ thì dừng)

1. `AGENTS.md`: toàn bộ (đặc biệt mục 2, 4, 6.3, 6.4).
2. `docs/team_updates.md`: 3 mục trên cùng.
3. `dashboard/index.html`, `dashboard/app.js`, `dashboard/style.css`: toàn bộ (giao diện và cách đọc chain hiện tại).
4. `contracts/contracts/CareSLA.sol`: chỉ `createCarePlan`, `acceptPlan`, `commitShift`, `settle`, các hằng số đầu file, các `event`.
5. `docs/demo_runbook.md`, `tools/fake_device.py` (chỉ phần `main`, cách gọi).
6. `docs/progress/P6.md`: mục "BÀN GIAO HIỆN TẠI".

Không đọc `iot_code/`, `ai_model/`, `node_modules/`.

## 1. Ràng buộc (không được vi phạm)

- **Không sửa** `CareSLA.sol`, ABI, `backend/gateway.py`, `backend/keeper.py`, firmware, giao diện mục 6 AGENTS.md.
- **Giữ nguyên giao diện trang giám sát** (`index.html`, `app.js`, `style.css` màu ngày 28/09). Chỉ được: thêm **một link** "Thiết lập hợp đồng" ở header `index.html`, và **thêm** CSS mới ở cuối `style.css` dùng lại các biến màu có sẵn. Không đổi màu, không đổi bố cục cũ.
- Dashboard HTML + JS thuần, ethers **6.13.4** UMD cùng link CDN đang dùng. Không React, **không biểu đồ**.
- **Chỉ chạy trên Hardhat local (chainId 31337).** Mạng khác: hiện thông báo "Trang thiết lập chỉ dùng cho demo local" và khóa mọi nút.
- Đọc chain bằng `new ethers.JsonRpcProvider('http://127.0.0.1:8545', 31337, { staticNetwork: true })` (giống `app.js`, tránh cache MetaMask). MetaMask **chỉ để ký**. Nghe `accountsChanged` để lấy lại signer và cập nhật vai trò ngay khi đổi ví.
- Không đưa khóa riêng vào code. Chỉ được dùng **địa chỉ công khai** của ví Hardhat mặc định để điền sẵn.
- **Quyền:** trưởng nhóm cho P6 sửa `dashboard/` (file của P5) **chỉ cho việc này**; ghi mỗi file đã sửa vào `docs/progress/P6.md`.
- Làm trên nhánh `p6` (nhánh P6 đang dùng), `git pull origin main` trước khi bắt đầu. Commit nhỏ. **Không push `main`**; push `p6` rồi báo P1 review và merge.

## 2. Thời gian demo (mặc định điền sẵn, người dùng sửa được)

| Tham số | Mặc định | Lý do |
|---|---|---|
| SLA | **30 giây** | 2 cấp chuyển trong 60 giây (AGENTS 6.4 ghi 60 s; ghi rõ khác biệt này trong IC-18) |
| Mức phạt | **20 ETH** | Số tròn, dễ nhìn khi chia tiền (chốt 2026-09-28, giống `demo_setup.js`) |
| Ký quỹ | **100 ETH** | Ví Hardhat có 10.000 ETH; chỉ dùng local |
| Ngày kết thúc kỳ | giờ chain + **15 phút** | Đủ cho mọi sự cố trong demo |
| Ca trực | bắt đầu giờ chain + **20 giây**, kết thúc = ngày kết thúc kỳ | `commitShift` bắt buộc `start > block.timestamp` |
| Nhân viên chính / dự phòng | ví Hardhat #3 / #4 | |
| Trung tâm | ví Hardhat #2 | Gia đình là ví #1 |

"Giờ chain" = `timestamp` của block mới nhất. Node của dự án tự đào block mỗi 1 giây (`hardhat.config.js`), nên giờ chain chạy theo giờ thật. Luôn lấy giờ chain, **không** lấy `Date.now()`.

## 3. Trang cần làm: `dashboard/setup.html` + `dashboard/setup.js`

Header giống trang giám sát (tên ứng dụng, huy hiệu mạng, nút kết nối ví) và thêm dòng **"Ví đang dùng: Gia đình / Trung tâm / Nhân viên / Khác"**. Vai trò xác định bằng cách so địa chỉ ví với `family`, `provider` của hợp đồng (`getPlan`), hoặc với ô "Địa chỉ trung tâm" khi chưa có hợp đồng.

**Thanh tiến trình 4 bước**: ① Gia đình tạo hợp đồng → ② Trung tâm chấp nhận → ③ Cam kết ca trực → ④ Bắt đầu giám sát. Bước xong: màu xanh, hiện mã giao dịch rút gọn và block. Bước chưa tới lượt: mờ, nút khóa. Mỗi bước là một thẻ trắng như trang giám sát.

Ô "**Mở hợp đồng có sẵn** (planId)": tải lại trạng thái các bước từ chain, để làm tiếp sau khi tải lại trang. Lưu planId vào URL `?plan=` và `localStorage` (bọc try/catch).

### ① Gia đình tạo hợp đồng (ví #1)
- Ô: địa chỉ trung tâm, địa chỉ thiết bị (nhớ giá trị gần nhất trong `localStorage`), SLA, mức phạt (ETH), ngày kết thúc kỳ (hiện cả giờ đọc được và "còn X phút"), ký quỹ (ETH).
- Gọi `createCarePlan(provider, device, sla, parseEther(phạt), periodEnd, { value: parseEther(ký quỹ) })`.
- Lấy `planId` từ event `PlanCreated` trong receipt.
- Hiện **số dư ví gia đình trước/sau** và **số dư contract** để thấy tiền đã bị khóa.

### ② Trung tâm chấp nhận (ví #2)
- Hiện tóm tắt hợp đồng đọc từ `getPlan` (gia đình, thiết bị, SLA, phạt, ký quỹ, kết thúc kỳ) rồi nút **Chấp nhận** → `acceptPlan(planId)`.
- Chỉ bật khi ví = `provider` của hợp đồng.

### ③ Cam kết ca trực (ví #2)
- Ô: giờ bắt đầu, giờ kết thúc, nhân viên chính, dự phòng. Nút "Điền mặc định" (giờ chain + 20 s → ngày kết thúc kỳ). → `commitShift(...)`.
- **Bảng các ca đã cam kết** từ `queryFilter(ShiftCommitted(planId), deployBlock)`: bắt đầu, kết thúc, chính, dự phòng, trạng thái (Chưa bắt đầu / Đang trực / Đã hết, tính theo giờ chain), mã giao dịch.
- Nút phụ "**Thử sửa ca đã qua**": gửi ca có `start` = giờ chain − 60 để người xem thấy contract từ chối `start in past`. Gọi `staticCall` trước để không tốn giao dịch hỏng; hiện lỗi đã dịch.

### ④ Bắt đầu giám sát
- Checklist tự cập nhật mỗi 1 giây: ✅ đã chấp nhận; ✅ có ca / "ca bắt đầu sau N giây"; ⚠️ **gateway phải dùng đúng planId**.
- Ô nhắc: "`PLAN_ID` trong `.env` phải bằng **N**. Nếu khác: sửa `.env` rồi chạy lại gateway". Có nút copy. Nếu planId = 1 thì hiện "✅ khớp mặc định `.env`".
- Nút **Mở giám sát** → `index.html?plan=N`.

### Khu "Kết thúc demo" (dưới cùng, chỉ hiện ở 31337)
- Hiện: "Được chia tiền khi giờ chain > kết thúc kỳ + 600 giây (hằng số contract `SETTLE_DELAY`), còn X phút".
- Nút **⏩ Tua giờ tới lúc được chia tiền (chỉ Hardhat local)**: gửi `evm_increaseTime` (đủ để qua `periodEnd + 600`) rồi `evm_mine` qua `JsonRpcProvider.send`. Hộp xác nhận ghi rõ: *sau khi tua, thiết bị không gửi được sự kiện mới cho chain này (bị từ chối "ts too old"), chỉ bấm ở bước cuối*.
- Sau khi tua: nhắc qua trang giám sát bấm **Settle**, hoặc có nút Settle ngay tại đây. Hiện **số dư gia đình và trung tâm trước/sau** cùng số vi phạm, để người xem đối chiếu công thức `phạt = min(vi phạm × mức phạt, ký quỹ)`.

### Dịch lỗi `require` sang tiếng Việt (bảng trong `setup.js`)
`no deposit`, `zero address`, `provider is family`, `sla is 0`, `penalty > deposit`, `period ended`, `not provider`, `already accepted`, `not accepted`, `start in past`, `end <= start`, `end > periodEnd`, `primary == backup`, `too many shifts`, `overlap`, `period not ended`, `pending events`, `already settled`. Lỗi lạ thì hiện nguyên văn. Người dùng hủy ký trong MetaMask thì hiện "Đã hủy ký", không báo lỗi đỏ.

## 4. Kịch bản demo 10 phút (viết vào `docs/demo_runbook.md`, mục mới "Demo 10 phút")

**Chuẩn bị trước giờ demo (không tính vào 10 phút):**
- `npm run node` → `npm run deploy:local`. **Không** chạy `demo-setup`, để hợp đồng tạo trên web là **planId = 1**, khớp `.env` mặc định.
- Chạy Mosquitto, gateway, keeper.
- `python -m http.server 8000` ở gốc repo.
- MetaMask: import ví #1–#4, xóa lịch sử giao dịch cũ nếu node vừa khởi động lại.
- Thiết bị: ESP32 đã kết nối, hoặc `fake_device.py` với file khóa sẵn.

| Phút | Việc | Người xem thấy |
|---|---|---|
| 0:00 | ① Ví #1 tạo hợp đồng | Tiền rời ví gia đình, nằm trong contract |
| 1:00 | ② Đổi sang ví #2, chấp nhận | Trung tâm đồng ý điều khoản trên chain |
| 1:30 | ③ Cam kết ca (bắt đầu +20 s); bấm "Thử sửa ca đã qua" | Contract từ chối sửa lịch về quá khứ |
| 2:30 | ④ Ca bắt đầu → Mở giám sát | |
| 3:00 | CANCEL | Chỉ ghi ở gateway, không lên chain |
| 3:30 | FALL #1 → ví #3 bấm Xác nhận trong 30 s → ARRIVAL | Không vi phạm |
| 5:00 | FALL #2 → không bấm: 30 s chuyển dự phòng, 60 s báo gia đình → ARRIVAL | 2 vi phạm, ghi tự động |
| 7:00 | ⏩ Tua giờ → Settle | Gia đình nhận 40 ETH, trung tâm 60 ETH |
| 8:00 | Dự phòng / hỏi đáp | |

Ghi chú:
- ESP32 thật: FALL đến sau ~12 s (bất động 2 s + cửa sổ hủy 10 s). ARRIVAL cần giữ nút 3 s.
- `DETECTOR_MODE 1` (AI) chưa khớp golden, nên luôn có `fake_device.py` sẵn làm dự phòng.

## 5. Kiểm thử bắt buộc trước khi báo xong

1. `node --check dashboard/setup.js dashboard/app.js`. Không có `id` nào JS gọi mà HTML thiếu.
2. **Test tự động không cần trình duyệt**: script trong `tools/` (hoặc scratchpad nếu không muốn commit) chạy `setup.js` trong Node `vm` với DOM giả và `window.ethereum` giả chuyển tiếp tới `127.0.0.1:8545` bằng ví #1/#2. Đi hết ①→④, kiểm tra planId, trạng thái `accepted`, bảng ca, lỗi `start in past` được dịch đúng. Sau đó chạy `fake_device.py` FALL/ARRIVAL để trang giám sát nhận sự cố, tua giờ, settle và kiểm tra chia tiền 40 / 60 ETH với 2 vi phạm.
3. **Tổng dượt thật 1 lần theo mục 4, bấm giờ**, dùng `fake_device.py`. Ghi thời gian từng mốc vào `docs/progress/P6.md`. Vượt 10 phút thì rút gọn các bước chậm nhất và ghi lại.
4. `cd contracts && npx hardhat test` vẫn 66 passing (không được ảnh hưởng).
5. Mở trang giám sát: màu, bố cục, nút giữ nguyên như trước (chỉ thêm link).

## 6. Tài liệu kèm theo

- `docs/interface_changes.md`: **IC-18**, trạng thái **CHỜ CHỐT**: mở rộng dashboard (AGENTS.md mục 4) thêm trang thiết lập; SLA demo 30 s; nút tua giờ chỉ ở Hardhat local. Không đổi contract hay giao diện mục 6.
- Không sửa `docs/team_updates.md` (P1 ghi khi merge). Tóm tắt cách dùng trang và kịch bản 10 phút trong `docs/progress/P6.md`.
- `docs/progress/P6.md`: việc đã làm, lệnh đã chạy, kết quả tổng dượt, file của người khác đã sửa.
- Sau khi xong: giải thích ngắn (3–6 câu) đã làm gì, chạy thử bằng lệnh nào. Push nhánh `p6` và báo P1 "kiểm tra dashboard P6"; P1 review rồi merge vào `main`.
