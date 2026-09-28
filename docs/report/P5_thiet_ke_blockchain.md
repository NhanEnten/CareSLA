## Thiết kế tầng Blockchain

Tầng Blockchain đóng vai trò là "trọng tài điện tử" khách quan, tự động thực thi các điều khoản đã cam kết giữa gia đình người cao tuổi và trung tâm dưỡng lão. Đây là tầng xử lý luồng Trách nhiệm (Accountability Pipeline), tách biệt hoàn toàn với luồng Cảnh báo cấp cứu.

### 1. Vai trò và Lý do lựa chọn Blockchain
Trong mô hình quản lý truyền thống, nhật ký (log) sự cố và thời gian nhân viên y tế phản hồi thường được lưu trữ ở cơ sở dữ liệu tập trung (như MySQL) thuộc quyền kiểm soát của trung tâm dưỡng lão. Điều này tạo ra **xung đột lợi ích (conflict of interest)** vì trung tâm vừa là bên cung cấp dịch vụ, vừa là bên giữ bằng chứng để tự đánh giá mức độ vi phạm của chính mình.

Công nghệ Blockchain giải quyết vấn đề này bằng cách:
- **Tính bất biến (Immutability):** Mọi sự kiện té ngã và mốc thời gian nhân viên phản hồi đều được ghi nhận vĩnh viễn trên sổ cái (Ethereum network).
- **Thực thi tự động (Smart Contract):** Hợp đồng thông minh sẽ giữ tiền ký quỹ và tự động tính toán, trừ tiền phạt nếu nhân viên phản hồi trễ hơn thời gian SLA (Service Level Agreement) đã cam kết.

### 2. Thiết kế Smart Contract (CareSLA.sol)
Hợp đồng thông minh `CareSLA.sol` được triển khai trên mạng Sepolia Testnet, chịu trách nhiệm lưu trữ trạng thái của từng bệnh nhân. Các logic cốt lõi bao gồm:

- **Quản lý Vòng đời Hợp đồng:** Gia đình tạo hợp đồng (`createCarePlan`) và gửi tiền ký quỹ bằng đồng ETH gốc. Trung tâm dưỡng lão xem xét và chấp nhận (`acceptPlan`). Khi hết hạn, hợp đồng sẽ được thanh lý (`settle`) để hoàn trả phần tiền ký quỹ còn lại cho trung tâm và trả tiền phạt (nếu có) cho gia đình.
- **Cam kết ca trực (Shift Commitment):** Trước khi ca trực diễn ra, trung tâm phải gọi hàm `commitShift` để đăng ký Nhân viên chính (Primary) và Nhân viên dự phòng (Backup) cho từng khung giờ. Dữ liệu này không thể sửa đổi sau khi đã cam kết.
- **Tiếp nhận sự cố (reportFall):** Khi có té ngã, hợp đồng nhận thông tin kèm `dataHash` (mã băm của dữ liệu gia tốc kế) và `sig` (chữ ký số). Hợp đồng sử dụng thuật toán mã hóa đường cong elliptic để khôi phục địa chỉ (`ecrecover`) và đối chiếu xem gói tin có đúng do thiết bị của bệnh nhân đó sinh ra hay không. Nếu hợp lệ, hệ thống bắt đầu đếm ngược thời gian SLA.
- **Ghi nhận phản hồi (Acknowledge & Confirm Arrival):** Khi nhân viên y tế nhận được báo động, họ sử dụng ví MetaMask để gọi hàm `acknowledge`. Thời điểm gọi hàm này sẽ được lấy từ `block.timestamp` để làm mốc tính toán xem có vi phạm SLA hay không. Sau khi đến phòng bệnh nhân, nhân viên bấm nút trên thiết bị để gọi tiếp hàm `confirmArrival`.

### 3. Tích hợp Gateway (Cầu nối Off-chain và On-chain)
Vì thiết bị IoT (ESP32) không đủ tài nguyên và khả năng kết nối trực tiếp với mạng lưới Blockchain, hệ thống sử dụng một Gateway viết bằng Python để làm cầu nối. Gateway có các nhiệm vụ:
- **Lọc rác bằng Chữ ký số:** Gateway tự mình xác thực chữ ký off-chain trước khi gửi lên mạng để tránh tốn phí Gas cho các giao dịch rác.
- **Hàng đợi Giao dịch (Tx Queue) tuần tự:** Gateway sử dụng một Thread duy nhất để xây dựng giao dịch, ký bằng khóa riêng của Gateway (`GATEWAY_PRIVATE_KEY`) và gửi lên chain. Cơ chế hàng đợi này giúp ngăn chặn lỗi trùng lặp `nonce` khi có nhiều sự cố xảy ra cùng một lúc.
- **Lắng nghe sự kiện (Event Listener):** Gateway liên tục quét các log sự kiện `Escalated` từ Smart Contract mỗi 5 giây. Nếu phát hiện một sự cố bị hệ thống đánh dấu là quá hạn, Gateway sẽ lập tức báo cho người nhà (Cấp 2).

### 4. Cơ chế tự động hóa bằng Keeper
Bản chất của Smart Contract trên Ethereum là thụ động (chỉ chạy khi có người gọi hàm). Do đó, hợp đồng không thể tự động trừ tiền khi hết giờ SLA.
Để khắc phục, hệ thống thiết kế một module **Keeper (Cronjob)** chạy ngầm bằng Python. Keeper liên tục kiểm tra danh sách các sự cố đang "Mở". Nếu phát hiện sự cố đã vượt qua `deadline`, Keeper sẽ kích hoạt hàm `checkTimeout()` của contract. Lúc này, contract sẽ xác nhận vi phạm, trừ tiền ký quỹ và chuyển trách nhiệm sang ca dự phòng.
