# Ôn phản biện — P5 (Backend Gateway & Dashboard)

### Cập nhật giao diện 2026-09-28
Lựa chọn màu mới nhất: nền xám rất nhạt, thẻ trắng, chữ navy, thao tác chính xanh dương; thanh lý dùng đỏ, còn các nhãn Mở/Đã nhận/Đã đến nơi dùng đỏ/vàng cam/xanh lá. Màu chữ trạng thái dùng sắc đậm để dễ đọc; nút vô hiệu hóa dùng xám. Màu chỉ phản ánh trạng thái có sẵn, không thay đổi luật hợp đồng.

Bảng màu được gom trong các biến CSS để dễ thay đổi đồng bộ. Hai thẻ độ trễ và hai dòng mô tả được bỏ theo yêu cầu; `loadMetrics` chỉ cập nhật hai thẻ còn lại để tránh truy cập phần tử DOM đã xóa. Việc bỏ mô tả thanh lý không thay đổi điều kiện xử lý: nút vẫn chỉ bật sau `periodEnd + 600`, khi không còn pending và hợp đồng chưa thanh lý. Đã kiểm tra bằng trình duyệt với dữ liệu mô phỏng; đây không phải kiểm thử giao dịch blockchain thật.

## 1. Tôi đã làm gì
Tôi phụ trách xây dựng Gateway (cầu nối) và Dashboard Web3. Gateway nhận dữ liệu từ thiết bị qua MQTT, kiểm tra chữ ký off-chain, gửi cảnh báo khẩn cấp qua Telegram, và đẩy bằng chứng trách nhiệm (reportFall, confirmArrival) lên blockchain qua một hàng đợi an toàn. Dashboard là giao diện để nhân viên bấm nút xác nhận sự cố, theo dõi đếm ngược SLA và quản lý việc thanh lý hợp đồng. Ngoài ra, tôi còn làm script sinh test vector chuẩn và file cấu hình cho cả nhóm.

## 2. Luồng xử lý phần của tôi
1. **MQTT -> Telegram:** Thiết bị gửi `FALL` -> Gateway đọc MQTT -> Khôi phục chữ ký để lọc rác -> Gửi ngay Telegram cho người đang trực.
2. **MQTT -> Blockchain:** Đẩy thông tin `FALL` vào hàng đợi -> Thread phụ lấy ra và gửi hàm `reportFall()` lên chain -> Lấy `eventId` lưu lại.
3. **Blockchain -> Dashboard:** Dashboard frontend mỗi 4s đọc Web3 -> Hiển thị sự cố ra bảng -> Nhân viên bấm xác nhận qua MetaMask -> Gateway đọc log `Escalated` nếu quá hạn để gửi báo động leo thang.

## 3. Các đoạn code quan trọng nhất
```python
# 1. Hàng đợi đẩy giao dịch an toàn
def tx_worker():
    while True:
        task_type, kwargs = tx_queue.get()
        nonce = w3.eth.get_transaction_count(account.address)
        # ... gọi contract.functions.reportFall() ...
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
# Giải thích: Đảm bảo các giao dịch không bị lỗi trùng nonce khi có 2 sự cố đến sát nhau.
```

## 4. Quyết định thiết kế và lý do
- **Tách luồng cảnh báo và trách nhiệm:** Cảnh báo qua Telegram chạy thẳng ngay khi nhận MQTT, không chờ giao dịch Blockchain. Lý do: Cứu người là ưu tiên cao nhất, Blockchain có thể chậm hoặc nghẽn.
- **Hàng đợi tuần tự:** Vì thiết bị gửi ARRIVAL sau FALL, mà contract yêu cầu sự cố phải được tạo (FALL) trước khi có thể confirmArrival. Hàng đợi đảm bảo thứ tự này.
- **Dashboard không dùng WebSocket:** Chuyển sang đọc polling 4s một lần bằng `getFallEvent`. Lý do: Ổn định hơn trên môi trường testnet và dễ code frontend hơn.

## 5. Câu hỏi giảng viên có thể hỏi (và trả lời)
- **Hỏi: Gateway có quyền gì? Kẻ tấn công chiếm được gateway thì làm được gì và không làm được gì?**
  *Trả lời:* Kẻ tấn công chỉ có thể "làm ngơ" (từ chối gửi dữ liệu lên chain) hoặc gửi trễ. Chúng **không thể** tự tạo báo cáo giả vì không có khóa riêng của thiết bị (chữ ký hợp lệ sinh từ ESP32).
- **Hỏi: Vì sao gateway vẫn kiểm tra chữ ký dù contract cũng kiểm tra?**
  *Trả lời:* Để loại bỏ rác từ sớm (tránh tốn tiền phí gas) và tránh spam tin nhắn Telegram.
- **Hỏi: Độ trễ cảnh báo đo thế nào, kết quả bao nhiêu?**
  *Trả lời:* Gateway ghi nhận `t_received` lúc nhận MQTT và `t_telegram_ok` lúc gửi xong HTTP Request. Độ trễ thường dao động khoảng 300ms - 800ms.
- **Hỏi: Gateway bỏ không gửi sự kiện lên chain thì sao?**
  *Trả lời:* Đây là điểm yếu (Single Point of Failure) hiện tại. Cách giải quyết thực tế là chạy Gateway kép (Decentralized Gateway) nhưng do giới hạn thời gian nhóm chưa cài đặt.
- **Hỏi: MetaMask làm gì trong hệ thống?**
  *Trả lời:* Nhân viên dùng MetaMask chứa ví cá nhân để ký giao dịch xác nhận (Acknowledge) trên bảng điều khiển. Bằng chứng này lưu vĩnh viễn trên chain.
- **Hỏi: Dữ liệu thô lưu ở đâu, làm sao chứng minh nó không bị sửa?**
  *Trả lời:* Lưu off-chain trong SQLite của Gateway. Chứng minh tính toàn vẹn bằng cách băm dữ liệu thô ra `dataHash` và đưa `dataHash` lên on-chain kèm chữ ký.

## 6. Giới hạn và điều chưa chắc chắn
- Việc map từ địa chỉ Ethereum `0x...` ra ID Telegram đang dùng file cấu hình cứng `.env` thay vì on-chain.
- Gateway là Single Point of Failure (Nếu tắt máy, cả hệ thống ngắt).

## 7. Liên hệ với phần của người khác
- **Nhận từ P3 (Thiết bị):** MQTT topic `event`, `raw`, `heartbeat` định dạng JSON.
- **Nhận từ P1, P2 (Contract):** File ABI `CareSLA.json`, địa chỉ contract từ `deployments`, `getOnDuty()`.
- **Đưa cho P4 (AI):** Cung cấp base64 raw data để P4 có phương án dự phòng.

## 8. Ba câu tự kiểm tra
1. Gateway có đợi Tx đào xong mới gửi Telegram không? (Không)
2. Để giải quyết trùng Nonce, Gateway làm gì? (Dùng Thread Queue tuần tự)
3. Hợp đồng thanh lý (Settle) khi nào? (Sau khi quá hạn periodEnd + 600s và hết pendingEvents)
