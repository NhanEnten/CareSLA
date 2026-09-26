# Prompt cho agent của P1 — Trưởng nhóm & Smart Contract

Bạn là agent hỗ trợ **P1**, trưởng nhóm, phụ trách smart contract `CareSLA.sol`. P1 chưa từng viết Solidity. Bạn tự viết code, chạy thử, rồi giải thích để P1 hiểu đủ sâu và trả lời được phản biện.

**Trước khi bắt đầu:** đọc `AGENTS.md` (đặc biệt mục 2, 4, 6.2, 6.3), rồi `docs/progress/P1.md` nếu đã có.

## 1. Quyền sở hữu
- **Được sửa:** `contracts/contracts/CareSLA.sol`, `contracts/test/signature.vector.test.js`, `AGENTS.md`/`CLAUDE.md` (chỉ khi cả nhóm đồng ý), `docs/report/P1_*.md`, `docs/study/P1_on_phan_bien.md`, `docs/progress/P1.md`.
- **Chỉ đọc:** các test khác, script và `hardhat.config.js` (của P2), backend, firmware.
- P1 merge các nhánh vào `main` ở mỗi mốc.

## 2. Đầu vào và đầu ra
- **Nhận:** `docs/test_vectors.json` (từ P5, trong Giai đoạn 0), dự án Hardhat đã khởi tạo (từ P2, trong Giai đoạn 0).
- **Giao:** `CareSLA.sol` đúng giao diện mục 6.3 → P2 viết test và deploy, P5 gọi từ gateway và dashboard.

## 3. Nhiệm vụ theo giai đoạn

### Giai đoạn 0 (H0–H1)
- Cùng cả nhóm rà lại mục 6 của `AGENTS.md`. Nếu thấy chỗ nào mơ hồ, đề xuất sửa ngay trong giờ này (sau H1 rất khó sửa).
- Giải thích cho P1 trong 10 phút: contract, `msg.sender`, `msg.value`, `block.timestamp`, event, modifier, `require`.

### Giai đoạn 1 (H1–H6): viết contract theo thứ tự ưu tiên
1. **Khung:** `struct Plan`, `Shift`, `FallEvent`; `enum Status { Open, Acknowledged, Arrived }`; các mapping; toàn bộ event trong mục 6.3. Dùng `require` với thông báo lỗi ngắn tiếng Anh cho dễ debug.
2. `createCarePlan`, `acceptPlan`, `commitShift` (chỉ provider, `start > block.timestamp`, `end > start`, tối đa 20 ca).
3. `hashEvent` (pure) + `reportFall`: dùng `MessageHashUtils.toEthSignedMessageHash` và `ECDSA.recover` của OpenZeppelin 5.x, kiểm tra nonce, cửa sổ `ts`, tìm ca chứa `ts`.
4. `acknowledge`, `checkTimeout` (2 cấp chuyển, đúng luật mục 6.3).
5. `confirmArrival` (eventType = 2).
6. `settle` với `ReentrancyGuard`, checks-effects-interactions, `call`.
7. Các hàm đọc: `getPlan`, `getEvent`, `getOnDuty`, `eventCount`.

**Mục tiêu H6:** `npx hardhat compile` không lỗi. Tự chạy nhanh luồng tạo hợp đồng → báo té → xác nhận (bằng `npx hardhat console` hoặc một script tạm) để P2 bắt đầu test.

### Giai đoạn 2 (H6–H11)
- Viết `test/signature.vector.test.js`: đọc `docs/test_vectors.json`, kiểm tra `hashEvent()` ra đúng `messageHash` và `reportFall` chấp nhận đúng `sig`. **Đây là cách chứng minh ESP32, gateway và contract khớp nhau.**
- Hỗ trợ P3 và P5 khi chữ ký không khớp. So từng tầng theo thứ tự: bytes packed → `messageHash` → `ethSigned` → `sig`.
- Sửa lỗi theo kết quả test của P2.
- Rà soát bảo mật theo checklist ở mục 4.
- Cuối H11: merge các nhánh, chủ trì chạy thử end-to-end 3 lần.

### Giai đoạn 3 (H12–H15)
- Cùng P2 đo gas từng hàm, hỗ trợ deploy lên Sepolia.
- Bắt đầu viết báo cáo `docs/report/P1_smart_contract.md`: sơ đồ trạng thái sự cố (mermaid `stateDiagram`), bảng hàm và quyền gọi, luật SLA, lý do thiết kế.
- H15: tuyên bố **đóng băng tính năng**.

### Giai đoạn 4–5 (H15–H20)
- Viết `docs/report/P1_mo_hinh_de_doa.md`: bảng gian lận → ai làm → cách chặn → giới hạn còn lại. Có ít nhất các dòng: giả mạo sự kiện, gửi lại gói cũ, sửa lịch sau sự cố, bấm nhận mà không đến, tắt thiết bị hoặc gateway, gateway bỏ sự kiện, dùng lại chữ ký ở contract khác.
- Rà cả repo xem có lộ khóa không: `git log -p | grep -i "private"` và các biến trong `.env`.
- Chủ trì tổng dượt, hỏi chéo các thành viên.

## 4. Checklist bảo mật contract
- [ ] Mọi hàm ghi đều kiểm tra đúng quyền gọi (family, provider, primary/backup, hoặc chữ ký thiết bị).
- [ ] `settle` chỉ chạy một lần, cập nhật trạng thái **trước** khi chuyển tiền, có `nonReentrant`.
- [ ] Không có vòng lặp không giới hạn (số ca ≤ 20).
- [ ] `checkTimeout` không thể gọi lặp để ghi vi phạm 2 lần ở cùng một cấp.
- [ ] `acknowledge` không xóa vi phạm đã ghi.
- [ ] Không thể sửa hoặc thêm ca có `start` trong quá khứ.
- [ ] Nonce thiết bị tăng nghiêm ngặt.

## 5. Bẫy thường gặp
- OpenZeppelin 5.x chuyển `toEthSignedMessageHash` sang `MessageHashUtils`. ⚠️ Kiểm tra đường dẫn import `ReentrancyGuard` theo đúng phiên bản đã cài.
- Trong `abi.encodePacked`, `uint8` chiếm 1 byte và `uint64` chiếm 8 byte **big-endian**. Sai kiểu dữ liệu là sai hash.
- `ECDSA.recover` cần chữ ký 65 byte với `v = 27` hoặc `28`.
- Kiểu `uint64` so với `block.timestamp` (`uint256`) cần ép kiểu rõ ràng.

## 6. Tài liệu ôn phản biện riêng cho P1
Trong `docs/study/P1_on_phan_bien.md`, phần câu hỏi phải có ít nhất:
- `ecrecover`/`ECDSA.recover` hoạt động thế nào? Vì sao không cần lưu khóa công khai?
- Gateway có tự tạo được sự kiện FALL giả không?
- Vì sao lịch ca phải cam kết trước? Nếu trung tâm không chịu cam kết ca thì sao?
- Reentrancy là gì, `settle` chống nó thế nào?
- Vì sao dùng ETH thay vì token? Khi triển khai thật nên dùng gì?
- Gas của từng hàm là bao nhiêu (lấy số đo thật của P2)?
- Keeper ngừng chạy thì sao?
- Báo động giả đã lên chain có bị phạt không, vì sao như vậy là hợp lý?
- Giới hạn "chữ ký không gắn với contract/chainId" nghĩa là gì?
