# Ôn phản biện — P6 (tích hợp)

## 1. Tôi đã làm gì

Tôi lấy main đã chứa công việc các thành viên và tạo nhánh tích hợp riêng.
Tôi giữ nguyên bản firmware cục bộ và sao lưu cấu hình riêng của P3.
Tôi bổ sung mẫu cấu hình để máy khác có thể build khi chưa có bí mật.
Tôi thêm chế độ ngưỡng tạm để demo không phụ thuộc AI đang sai golden.
Tôi sửa gateway để kiểm tra dữ liệu thô theo cả hai thứ tự nhận gói.
Tôi tạo thiết bị giả và các kiểm thử cho toàn luồng trách nhiệm.
Kết quả phần mềm được tách khỏi những việc cần thử trên board hoặc Telegram.

Bổ sung 28/09: tôi làm trang thiết lập cho gia đình khóa ETH, trung tâm nhận
điều khoản và cam kết ca. Trang đọc chain trực tiếp để tránh cache ví. Tôi cho
người xem thử một ca quá khứ và thấy contract từ chối. Cuối demo, node local
được tua giờ để minh họa chia tiền. Tôi chạy toàn luồng với thiết bị giả và
keeper thật trong 169.43 giây; thao tác MetaMask thủ công chưa được kiểm chứng.

## 2. Luồng xử lý

1. Thiết bị ký FALL và gửi event, sau đó raw qua MQTT.
2. Gateway kiểm tra chữ ký, cảnh báo ngay qua Telegram hoặc log dự phòng.
3. Worker riêng gửi giao dịch; RPC lỗi thì chờ và thử lại.
4. Keeper gọi checkTimeout khi quá hạn, contract ghi phạt và chuyển cấp.
5. ARRIVAL có chữ ký được ghi nhận; cuối kỳ contract chia tiền theo vi phạm.

Luồng dashboard mới: tạo plan → đổi sang ví trung tâm → accept → cam kết ca
bắt đầu sau giờ chain → chờ ca → mở giám sát → xử lý hai sự cố → ARRIVAL cuối
cùng → xác nhận tua giờ local → settle. IC-17 đã bỏ Telegram khỏi demo hiện tại;
cảnh báo quan sát ở còi thiết bị và `ALERT_DISPATCH` gateway.

## 3. Đoạn code quan trọng

```python
valid = bytes(Web3.keccak(raw)) == bytes.fromhex(data_hash.removeprefix('0x'))
```

So toàn bộ 32 byte hash. Không cắt hai ký tự đầu một chuỗi hex khi chưa
chắc nó có tiền tố 0x, vì có thể bỏ mất byte đầu.

```c
if (DETECTOR_MODE == 0 && !gap) impact = sqrtf(a2) >= IMPACT_G;
```

Ngưỡng chỉ tạo candidate; vẫn phải đi qua bất động và cửa sổ hủy.

```javascript
await reader.commitShift.staticCall(...shiftArgs(chainTime - 60), {
    from: signer.address,
});
```

Mô phỏng bằng RPC với đúng địa chỉ trung tâm; contract trả `start in past`.
Không gửi giao dịch hỏng và không sửa ca cũ: contract không có hàm sửa ca.

```javascript
const delta = Math.max(0, Number(latest.periodEnd) + 601 - chainTime);
if (delta) await rpc.send('evm_increaseTime', [delta]);
await rpc.send('evm_mine', []);
```

Phải lớn hơn, không chỉ bằng `periodEnd + 600`. Chỉ chạy sau kiểm tra chainId
31337, xác nhận người dùng và không còn sự cố chờ; đây là tiện ích Hardhat.

## 4. Quyết định thiết kế và lý do

- Clone riêng giữ được bản build và secrets cũ; không ghi đè thư mục ZIP.
- Lấy main vì đã merge cả nhóm và có các sửa P1 sau merge.
- Cờ ngưỡng tạm giúp kiểm tra hệ thống khi AI chưa đạt, không thay đáp án golden.
- SQLite lưu nonce trước publish; publish lỗi được phép bỏ qua một số nonce,
  nhưng không được tái sử dụng. Không dùng chung khóa giả với ESP32.
- Không gọi RPC trong đường cảnh báo vì chain chậm không được chặn cứu người.
- Tách trang thiết lập giữ giao diện giám sát P5. Không dùng React hoặc sửa ABI.
- Đọc bằng JsonRpcProvider; BrowserProvider chỉ để ký và nhận thay đổi ví.
- IC-18 đã chốt sau merge P1: SLA 60 giây, ký quỹ 100 ETH, phạt 20 ETH trên local.

## 5. Câu hỏi phản biện

1. Vì sao không xóa NVS? Nonce phải tăng qua reboot/nạp chương trình.
2. Fake device có thay thế board không? Chỉ kiểm tra giao diện/phần mềm, không đo phần cứng.
3. Vì sao raw có thể tới sau? ESP32 gửi event trước; kiểm tra hash phải xử lý cả hai thứ tự.
4. Heartbeat khôi phục có xóa sự cố không? Không; heartbeat chỉ là giám sát kết nối off-chain.
5. RPC chết thì gì còn chạy? MQTT và cảnh báo, giao dịch chờ worker thử lại.
6. Ai thực hiện chuyển cấp? Keeper gửi giao dịch, contract kiểm tra điều kiện và ghi phạt.
7. Vì sao ví gia đình giảm hơn 100 ETH? 100 ETH ký quỹ cộng gas tạo hợp đồng.
8. Tua giờ có dùng trên Sepolia không? Không; đây là RPC riêng của node Hardhat.
9. Tại sao phải chờ thêm 600 giây? Cho gói sự cố trễ trong cửa sổ timestamp được xử lý.
10. Vì sao không gửi FALL sau tua giờ? Thiết bị ký giờ thật, chain đã đi trước quá cửa sổ 600 giây.
11. Hai vi phạm với 20 ETH/lần và 100 ETH ký quỹ chia thế nào? Gia đình 40, trung tâm 60 ETH.
12. Trang ghi PLAN_ID=1 có chứng minh gateway cấu hình đúng không? Không; đó chỉ là mặc định, phải kiểm tra tiến trình thực tế.

## 6. Giới hạn và điều chưa chắc chắn

Golden AI trên board còn sai; chưa có số liệu accuracy/độ trễ thực nghiệm
mới. Hàng đợi gateway và trạng thái firmware chưa bền qua mất điện.
Mô phỏng tăng thời gian Hardhat không đại diện tốc độ chain thật.
Không tuyên bố Sepolia, giao diện MetaMask hay thao tác nút/còi đã đạt
nếu chưa có bằng chứng trong nhật ký P6.

Dashboard đã được kiểm thử ethers 6.13.4 bằng VM với ví giả chuyển tiếp RPC thật;
Chrome headless đã render trang. Đây chưa phải tổng dượt bấm ví MetaMask thật.
SLA chờ theo giờ thực, nhưng bước chia tiền dùng tua giờ; không suy ra độ trễ
Sepolia. Nút tua ảnh hưởng toàn bộ node local, nên dùng node riêng cho demo.

## 7. Liên hệ với thành viên khác

Nhận contract/giao diện từ P1; deploy/test/keeper từ P2; firmware/cấu hình
máy từ P3; model/spec từ P4; gateway/dashboard/vector từ P5. Bàn giao lại
nhánh p6-finish, test, log và runbook để P1 review.

Phiên dashboard dùng nhánh `p6`, nhận contract/ABI hiện tại, không thay giao diện
giữa các tầng; đưa planId cho gateway và URL `index.html?plan=N` cho dashboard.

## 8. Ba câu tự kiểm tra

1. Khi event tới trước raw, gateway kiểm tra hash ở đâu?
2. Nếu xóa file nonce rồi dùng lại cùng khóa, contract sẽ xử lý thế nào?
3. Cần thêm bằng chứng gì để từ kiểm thử PC chuyển sang nghiệm thu Mốc 2?

Tự kiểm tra phần dashboard: vì sao ca phải cam kết trước giờ bắt đầu; tại sao
acknowledge sau chuyển cấp không xóa phạt; khi nào được bấm tua giờ và settle?
