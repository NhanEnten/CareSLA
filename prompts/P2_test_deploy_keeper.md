# Prompt cho agent của P2 — Test, Deploy, Keeper, README

Bạn là agent hỗ trợ **P2**, phụ trách kiểm thử và triển khai smart contract, keeper Python và README. P2 chưa có kinh nghiệm blockchain. Bạn tự viết và chạy code, giải thích ngắn gọn, và tạo tài liệu ôn phản biện.

**Trước khi bắt đầu:** đọc `AGENTS.md` (mục 4, 5, 6.3, 6.5, 7), rồi `docs/progress/P2.md` nếu đã có.

## 1. Quyền sở hữu
- **Được sửa:** `contracts/hardhat.config.js`, `contracts/package.json`, `contracts/test/*` (trừ `signature.vector.test.js` của P1), `contracts/scripts/*`, `deployments/`, `backend/keeper.py`, `.env.example`, `.gitignore`, `README.md`, `docs/report/P2_*.md`, `docs/study/P2_on_phan_bien.md`, `docs/progress/P2.md`.
- **Chỉ đọc:** `CareSLA.sol` (lỗi contract thì báo P1 kèm test tái hiện).

## 2. Việc làm TRƯỚC H0 (nhắc P2)
- Xin Sepolia ETH từ nhiều faucet 2–3 ngày trước, dồn về ví deployer.
- Không cần LINK, vì Chainlink đã bị cắt.

## 3. Nhiệm vụ theo giai đoạn

### Giai đoạn 0 (H0–H1)
- Khởi tạo dự án Hardhat **2.x** trong `contracts/`. ⚠️ Ghim `hardhat@^2`, cài toolbox bản tương thích, `@openzeppelin/contracts@^5`, `dotenv`, `hardhat-gas-reporter` (nếu toolbox chưa có). Chạy `npx hardhat --version` để xác nhận.
- `hardhat.config.js`: các mạng `hardhat`, `localhost`, `sepolia` (đọc `SEPOLIA_RPC_URL`, `DEPLOYER_PRIVATE_KEY` từ `.env`), cấu hình Etherscan verify, gas reporter.
- `.gitignore` phải có: `.env`, `node_modules`, `iot_code/main/secrets.h`, `iot_code/build`, `*.sqlite`.
- `.env.example` gồm: `SEPOLIA_RPC_URL`, `DEPLOYER_PRIVATE_KEY`, `ETHERSCAN_API_KEY`, `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY`, `NETWORK`, `MQTT_HOST`, `MQTT_PORT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_PRIMARY`, `TELEGRAM_CHAT_BACKUP`, `TELEGRAM_CHAT_FAMILY`, `TELEGRAM_CHAT_PROVIDER`, `PLAN_ID`.

### Giai đoạn 1 (H1–H6)
- **Helper ký trong test:** tạo ví thiết bị bằng `ethers.Wallet`, tính hash bằng `ethers.solidityPackedKeccak256(["address","uint8","uint64","uint64","bytes32"], [...])`, ký bằng `wallet.signMessage(ethers.getBytes(hash))`.
- Viết test bằng `loadFixture` và `time.increase` (hardhat-network-helpers), cú pháp ethers v6 (BigInt, không có `ethers.utils`). Viết song song với P1, test nào chưa có hàm tương ứng thì đánh dấu `it.skip`.
- `scripts/deploy.js`: deploy, ghi `deployments/<network>.json` (`address`, `chainId`, `deployBlock`), copy ABI sang `backend/abi/CareSLA.json` và `dashboard/CareSLA.json`.
- `scripts/demo_setup.js`, **rất quan trọng cho demo**:
  - Gia đình tạo hợp đồng: ký quỹ 0.01 ETH, SLA 60 giây, phạt 0.002 ETH, `periodEnd` = hiện tại + 2 giờ, kèm địa chỉ thiết bị.
  - Trung tâm chấp nhận.
  - Cam kết các ca liên tiếp phủ kín 2 giờ tới, bắt đầu sau hiện tại vài chục giây, mỗi ca có primary và backup là ví demo.
  - In ra `planId`.
  - Theo IC-12 đã chốt: chạy thêm task với `--short-plan` để tạo hợp đồng thứ 2 kỳ 5 phút, ký quỹ thêm 0.01 ETH, dùng thiết bị mẫu có khóa ngẫu nhiên trong RAM; cam kết 1 ca và gửi FALL sau khi ca bắt đầu. Chuẩn bị ít nhất 20 phút trước demo, để keeper xử lý hai cấp; không giảm thời gian chờ settle 600 giây.
- Viết khung `backend/keeper.py`.

**Danh sách test tối thiểu (mục tiêu ≥ 12 test đạt ở H11):**
1. Tạo và chấp nhận hợp đồng; contract giữ đúng tiền ký quỹ.
2. `commitShift` từ chối ca có `start` đã qua.
3. `commitShift` từ chối người không phải provider.
4. `reportFall` hợp lệ: phát `FallReported`, giao cho đúng primary.
5. `reportFall` với chữ ký sai → revert.
6. `reportFall` gửi lại nonce cũ → revert.
7. `reportFall` với `ts` quá cũ → revert.
8. `acknowledge` đúng hạn → không có vi phạm.
9. Quá hạn lần 1 → `Escalated` cấp 1 và 1 vi phạm; quá hạn lần 2 → cấp 2, gửi tới gia đình, 2 vi phạm.
10. `checkTimeout` trước hạn → revert; gọi lặp ở cùng cấp → không ghi thêm vi phạm.
11. Người lạ gọi `acknowledge` → revert.
12. `confirmArrival` hợp lệ → `Arrived`.
13. `settle` khi giờ chain chưa lớn hơn `periodEnd + 600` → revert `"period not ended"`; còn sự cố treo → revert `"pending events"`; đủ điều kiện thì chia đúng số tiền; gọi lần 2 → revert `"already settled"`.
14. Tiền phạt không vượt quá tiền ký quỹ.
15. Hợp đồng bù nhìn dùng chung thiết bị không làm hợp đồng thật bị `"old nonce"` (nonce theo planId, IC-11).
16. `reportFall` với `ts > periodEnd` → revert `"ts after period"`.

### Giai đoạn 2 (H6–H11)
- Chạy toàn bộ test với contract thật của P1. Báo lỗi cho P1 kèm tên test.
- `keeper.py` bản thật:
  - Mỗi 5 giây đọc `eventCount()` và `getFallEvent(i)` (IC-09).
  - Chỉ gửi `checkTimeout(i)` khi `status == 0`, `level < 2` và giờ block mới nhất lớn hơn `deadline`, bằng `KEEPER_PRIVATE_KEY`. Không dùng giờ máy; cấp 2 có deadline bằng 0 nhưng không được gửi tiếp.
  - Bắt lỗi revert, không được crash. Log ra màn hình có giờ.
  - Chạy được với `NETWORK=localhost` và `NETWORK=sepolia`.
- Hướng dẫn cả nhóm quy trình chạy local: `npx hardhat node` → `deploy.js --network localhost` → `demo_setup.js`. ⚠️ Mỗi lần khởi động lại node là mất toàn bộ trạng thái, phải chạy lại cả hai script. Trong MetaMask cần xóa dữ liệu hoạt động của tài khoản để tránh lỗi nonce.

### Giai đoạn 3 (H12–H15)
- Deploy lên Sepolia, verify trên Etherscan (⚠️ kiểm tra plugin verify có dùng được với API key Etherscan hiện tại không), chạy `demo_setup.js` trên Sepolia.
- Chạy keeper với Sepolia.
- Xuất bảng gas bằng gas reporter.

### Giai đoạn 4–5 (H15–H20)
- **README.md** gồm: giới thiệu 3 dòng, sơ đồ thư mục, yêu cầu cài đặt, cấu hình `.env`, các bước chạy local, các bước chạy Sepolia (kèm link contract), cách nạp firmware (xin P3), cách chạy gateway, keeper và dashboard, kịch bản demo. Nhờ một thành viên khác làm theo README trên máy của họ để kiểm tra.
- Báo cáo `docs/report/P2_trien_khai_kiem_thu.md`: danh sách test và kết quả (ảnh chụp), bảng gas, quy trình triển khai, địa chỉ contract.

## 4. Bẫy thường gặp
- Hardhat 3 và Hardhat 2 có cấu hình khác nhau, không trộn tài liệu của hai bản.
- Trên Sepolia phải chờ receipt (`await tx.wait()`) trước khi đọc trạng thái.
- Hết Sepolia ETH giữa chừng: kiểm tra số dư các ví deployer, gateway, keeper trước mỗi lần demo.
- Không commit `.env`. Chạy `git status` trước mỗi commit.

## 5. Tài liệu ôn phản biện riêng cho P2
Trong `docs/study/P2_on_phan_bien.md`, phần câu hỏi phải có ít nhất:
- Testnet khác mainnet ở điểm nào? Vì sao chạy local vẫn đạt yêu cầu?
- Test nào chứng minh không thể gửi lại gói cũ? Test nào chứng minh không sửa được lịch?
- `time.increase` dùng để làm gì trong test?
- Keeper có quyền gì đặc biệt không? Keeper gian lận được không?
- Gas là gì? Hàm nào tốn nhất, vì sao?
- Verify contract trên Etherscan để làm gì?
