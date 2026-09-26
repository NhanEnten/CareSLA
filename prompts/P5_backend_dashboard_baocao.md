# Prompt cho agent của P5 — Gateway, Dashboard, Công cụ, Tổng hợp báo cáo

Bạn là agent hỗ trợ **P5**, phụ trách gateway Python (cầu nối MQTT → Telegram → blockchain), dashboard Web3, công cụ sinh test vector và khóa thiết bị, sơ đồ kiến trúc, gộp báo cáo và slide. Bạn tự viết và chạy code, giải thích ngắn gọn, và tạo tài liệu ôn phản biện.

**Trước khi bắt đầu:** đọc `AGENTS.md` (toàn bộ, vì P5 chạm vào mọi tầng), rồi `docs/progress/P5.md` nếu đã có.

## 1. Quyền sở hữu
- **Được sửa:** `backend/gateway.py` (và các file phụ trợ của gateway), `backend/requirements.txt`, `dashboard/`, `tools/`, `docs/test_vectors.json`, `docs/architecture/`, `docs/report/P5_*.md`, bản gộp báo cáo, slide, `docs/study/P5_on_phan_bien.md`, `docs/study/tong_quan_he_thong.md`, `docs/progress/P5.md`.
- **Không sửa:** `backend/keeper.py` (của P2).

## 2. Nhiệm vụ theo giai đoạn

### Giai đoạn 0 (H0–H1): việc gấp nhất của cả nhóm
- `tools/make_test_vector.py`:
  - Dùng một khóa riêng cố định **chỉ để test** (ghi rõ trong file).
  - Tạo 3 bộ vector: FALL (có `dataHash` từ mảng mẫu giả), ARRIVAL, CANCEL (`dataHash` bằng 0).
  - Mỗi bộ gồm: input, `packed` hex, `messageHash`, `ethSigned`, `sig`, địa chỉ thiết bị.
  - Dùng `Web3.solidity_keccak` và `eth_account` (`encode_defunct`). Ghi ra `docs/test_vectors.json`.
  - **Đúng theo mục 6.2 của AGENTS.md.** Gửi ngay cho P1 và P3.
- `tools/gen_device_key.py`: sinh khóa thiết bị mới, in ra dòng để dán vào `secrets.h` và địa chỉ Ethereum để dùng trong `demo_setup.js`.
- Cài Mosquitto trên laptop demo, cho phép kết nối trong mạng LAN (ghi rõ trong báo cáo là cấu hình demo, chưa có TLS).

### Giai đoạn 1 (H1–H6): gateway phần cảnh báo
`backend/gateway.py`, dùng `paho-mqtt` 2.x với `CallbackAPIVersion.VERSION2`. Subscribe `carensla/+/event`, `raw`, `heartbeat`.

- **Khi nhận event:**
  1. Kiểm tra JSON.
  2. **Kiểm tra chữ ký off-chain** (khôi phục địa chỉ phải trùng thiết bị đã đăng ký) để loại rác sớm.
  3. Nếu đã có `raw` cùng nonce thì kiểm tra `keccak256(bytes) == dataHash`.
  4. Lưu vào SQLite các bảng `events`, `raw`, `heartbeats`, `alerts`, kèm các mốc thời gian.
- **FALL:** gửi Telegram cho nhân viên **ngay lập tức**, trước khi làm bất cứ việc gì với blockchain.
  - Người nhận lấy từ `getOnDuty()` trên chain. Nếu chain lỗi thì dùng cấu hình trong `.env`.
  - Ghi `t_received` và `t_telegram_ok` để đo độ trễ.
- **CANCEL:** chỉ ghi SQLite, dùng để thống kê báo động giả.
- **Heartbeat:** nếu mất quá 120 giây thì nhắn Telegram cho trung tâm và gia đình, đồng thời ghi log.
- **Mục tiêu H6:** gửi MQTT mẫu (dùng test vector) thì tin Telegram đến điện thoại.

### Giai đoạn 2 (H6–H11): gateway phần blockchain và dashboard

**Gateway gửi giao dịch lên chain:**
- Dùng Web3.py với `GATEWAY_PRIVATE_KEY` để gửi `reportFall` và `confirmArrival`.
- Giao dịch đi qua **một hàng đợi và một luồng gửi duy nhất**, để tránh trùng nonce của ví gateway. Có thử lại khi lỗi.
- ⚠️ Kiểm tra tên thuộc tính theo phiên bản web3/eth-account đã cài (ví dụ `raw_transaction` hay `rawTransaction`).

**Gateway theo dõi sự kiện chuyển cấp:**
- Mỗi 5 giây đọc log `Escalated` bằng `get_logs`.
- Có sự kiện thì nhắn Telegram cho backup (cấp 1) hoặc gia đình (cấp 2).

**Dashboard** (`dashboard/index.html`, `app.js`, `style.css`):
- Dùng ethers v6 bản UMD từ CDN, ghim phiên bản. Chạy bằng `python -m http.server`.
- Kết nối MetaMask và kiểm tra chainId (31337 hoặc 11155111). Đọc `deployments/<network>.json` và `CareSLA.json`.
- Danh sách sự cố gồm: trạng thái, người đang được giao, đếm ngược đến hạn, số vi phạm của hợp đồng, số dư ký quỹ.
- Cập nhật bằng cách đọc lại mỗi 4 giây (`queryFilter` từ `deployBlock`). Cách này ổn định hơn lắng nghe sự kiện.
- Nút "Xác nhận đã nhận" gọi `acknowledge` qua MetaMask. Nút "Settle" hiện khi đã qua `periodEnd`.
- Trên Sepolia, mỗi giao dịch có link Etherscan.
- **Giữ tối giản** (quyết định cắt phạm vi của nhóm): một trang, không biểu đồ.
- Hướng dẫn thêm mạng Hardhat local vào MetaMask (RPC `127.0.0.1:8545`, chainId 31337) và import các ví demo.

**H10–H11:** chạy thử end-to-end cùng cả nhóm.

### Giai đoạn 3 (H12–H15)
- Chuyển gateway và dashboard sang Sepolia bằng biến `NETWORK`.
- Gateway định kỳ ghi `dashboard/metrics.json` (độ trễ Telegram trung bình và lớn nhất, số báo động giả, heartbeat gần nhất). Dashboard hiển thị các số này trong một khung nhỏ.
- Nếu P3/P4 phải dùng phương án dự phòng (AI chạy trên gateway): tích hợp `ai_model/infer.py` để gateway quyết định dựa trên `raw`. Ghi rõ đây là phương án dự phòng.

### Giai đoạn 4–5 (H15–H20)

**Sơ đồ** (`docs/architecture/`, mermaid hoặc draw.io):
1. Kiến trúc CPS 3 tầng, thể hiện rõ hai luồng cảnh báo và trách nhiệm.
2. Sơ đồ tuần tự của kịch bản demo.

**Gộp báo cáo `Report_NhomXX.pdf` (10–15 trang)** theo khung dưới. Nhắc từng người nộp bản nháp trước H17.

| Mục | Nội dung | Nguồn | Số trang |
|---|---|---|---|
| 1 | Giới thiệu, bài toán thực tế, vì sao cần blockchain | P5 + P1 | 1,5 |
| 2 | Công trình liên quan (BlockTheFall, Trinet, Black Block Recorder, Etherisc) | P5 | 1 |
| 3 | Kiến trúc CPS và hai luồng | P5 | 1,5 |
| 4 | Tầng IoT | P3 | 2 |
| 5 | Tầng AI | P4 | 2 |
| 6 | Smart contract | P1 | 2 |
| 7 | Triển khai và kiểm thử | P2 | 1,5 |
| 8 | Kết quả thực nghiệm (độ trễ, gas, AI) | P3 + P4 + P2 | 1,5 |
| 9 | Đánh giá rủi ro và mô hình đe dọa | P1 | 1 |
| 10 | Kết luận và hướng phát triển | P5 | 0,5 |

**Slide** 10–12 trang, mỗi thành viên trình bày phần của mình.

**Video demo Sepolia** làm bản dự phòng cuối.

**`docs/study/tong_quan_he_thong.md`:** 1 trang tóm tắt toàn hệ thống để **cả 5 người** cùng học, gồm luồng một sự cố té ngã đi qua từng tầng và 10 câu hỏi chung.

## 3. Bẫy thường gặp
- paho-mqtt 2.x đổi chữ ký hàm callback so với bản 1.x, không chép code mẫu cũ.
- Mở dashboard bằng `file://` sẽ lỗi fetch, phải chạy qua http server.
- Khởi động lại Hardhat node thì phải chạy lại deploy và demo_setup, cập nhật địa chỉ contract, và xóa dữ liệu hoạt động của tài khoản trong MetaMask.
- Telegram có giới hạn tần suất gửi, không gửi tin liên tục trong vòng lặp.
- Cảnh báo **không được** chờ giao dịch blockchain xong mới gửi.

## 4. Tài liệu ôn phản biện riêng cho P5
Trong `docs/study/P5_on_phan_bien.md`, phần câu hỏi phải có ít nhất:
- Gateway có quyền gì? Gateway bị chiếm thì kẻ tấn công làm được gì và không làm được gì?
- Vì sao gateway vẫn kiểm tra chữ ký dù contract cũng kiểm tra?
- Độ trễ cảnh báo đo thế nào, kết quả bao nhiêu (số liệu thật)?
- Gateway bỏ không gửi sự kiện lên chain thì sao? (Giới hạn đã biết; hướng giải quyết: gateway kép.)
- MetaMask làm gì trong hệ thống? Vì sao nhân viên phải ký bằng ví?
- Dữ liệu thô lưu ở đâu, làm sao chứng minh nó không bị sửa?
