# Ôn phản biện — P2 (kiểm thử, triển khai, keeper)

Cập nhật 27/09/2026; theo AGENTS.md mới và IC-01…IC-15. Nhóm có 5 người.

## 1. Tôi đã làm gì

Tôi chuẩn bị môi trường Hardhat 2 để biên dịch và kiểm tra contract của P1. Tôi viết test cho ký quỹ, lịch trực, chữ ký thiết bị, các cấp quá hạn và chia tiền. Bộ JavaScript toàn dự án đạt 66 test, trong đó có 24 test chữ ký do P1 viết với vector P5. Tôi viết keeper Python và 20 unit test bằng RPC giả. Script deploy xuất địa chỉ, block triển khai và ABI cho gateway/dashboard. Tôi chạy deploy/setup local, đo gas và ghi kết quả thật vào báo cáo. Phần này chưa đồng nghĩa cả hệ thống đã chạy được trên ESP32 hoặc Sepolia.

## 2. Luồng xử lý phần của tôi

1. Cài dependency theo lockfile, compile source P1 với cấu hình đã chốt.
2. Chạy test luật SLA/chữ ký và unit keeper.
3. Mở node local, deploy, xuất metadata và ABI.
4. Setup plan, provider chấp nhận và cam kết ca trước khi ca bắt đầu.
5. Gateway gửi FALL; keeper đọc giờ chain, kiểm tra trạng thái và gửi checkTimeout khi cần.
6. Đủ điều kiện cuối kỳ thì người dùng/dashboard gọi settle; keeper không tự settle.

## 3. Các đoạn code quan trọng nhất

Helper ký (rút gọn từ contracts/test/helpers/events.js):

```js
const messageHash = ethers.solidityPackedKeccak256(
  ["address", "uint8", "uint64", "uint64", "bytes32"],
  [device, eventType, timestamp, nonce, dataHash],
);
const sig = await wallet.signMessage(ethers.getBytes(messageHash));
```

Phải ký **32 byte hash**, không ký chuỗi chữ “0x...”. Thứ tự và kiểu dữ liệu quyết định đúng 69 byte trước khi băm.

Điều kiện keeper (backend/keeper.py):

```python
def is_due(state, chain_timestamp):
    return not state["closed"] and state["level"] < 2 and chain_timestamp > state["deadline"]
```

Cấp 2 có deadline bằng 0 nhưng không được gọi tiếp. So sánh > chứ không phải >=; giờ lấy từ block.

Chờ deploy có xác nhận (contracts/scripts/deploy.js):

```js
const contract = await hre.ethers.deployContract("CareSLA");
await contract.waitForDeployment();
const receipt = await contract.deploymentTransaction().wait();
const deployment = {
  address: await contract.getAddress(),
  chainId,
  deployBlock: receipt.blockNumber,
};
```

Không xuất địa chỉ/ABI giả khi chưa deploy thành công.

## 4. Quyết định thiết kế và lý do

- Hardhat 2/ethers v6, compiler npm khóa 0.8.24: đồng nhất với nhóm; không nâng Hardhat 3.
- Keeper mỗi 5 giây, permissionless: không dùng Chainlink vì ngoài phạm vi. Keeper chỉ đề nghị giao dịch; contract quyết định có hợp lệ không.
- Lưu pending transaction và theo receipt để hạn chế gửi trùng khi RPC lỗi. State pending mới ở RAM, chưa phải hàng đợi bền vững.
- Dựng trạng thái từ log rồi đọc getter cùng block; kiểm tra eventCount để phát hiện thiếu lịch sử. Không bỏ qua lỗi thiếu dữ liệu.
- Plan ngắn riêng để demo settle; giữ nguyên SETTLE_DELAY 600 giây, không sửa luật contract phục vụ trình diễn.
- Không đổi tên biến môi trường chung ngoài IC-15; địa chỉ/ví setup thêm dùng tùy chọn task riêng.

## 5. Câu hỏi giảng viên và gợi ý trả lời

1. **Testnet khác mainnet?** Cùng mô hình giao dịch/contract nhưng ETH test không phải tiền thật và môi trường thử nghiệm khác sản xuất. Local chứng minh logic có thể tái lập; không chứng minh vận hành mạng công khai.
2. **Test nào chống gửi lại gói?** Test nonce FALL/ARRIVAL cũ bị revert, test IC-11 hai plan cùng thiết bị không lấy mất nonce của nhau.
3. **Test nào bảo vệ lịch trực?** Test cấm ca đã bắt đầu, người không phải provider, ca chồng và đổi người trực hồi tố.
4. **time.increase làm gì?** Đẩy thời gian blockchain thử nghiệm để kiểm tra deadline nhanh; không dùng được để đổi giờ Sepolia.
5. **Keeper có quyền đặc biệt không?** Không. Gia đình hay người khác cũng gọi được checkTimeout; contract tự kiểm tra deadline/trạng thái.
6. **Keeper gian lận hoặc tắt thì sao?** Không ghi phạt trước hạn được. Nếu tắt thì cần bên khác gọi; blockchain không tự chạy hàm theo đồng hồ.
7. **Gas là gì, hàm nào tốn nhất?** Đơn vị chi phí thực thi. Trong bảng local hiện tại reportFall có trung bình cao nhất, khoảng 245 nghìn gas; deploy khoảng 1,814 triệu gas. Không đồng nhất gas với giá ETH.
8. **Verify Etherscan để làm gì?** Đối chiếu source/cấu hình với bytecode triển khai, giúp người khác kiểm tra. Chưa thực hiện verify Sepolia trong phiên này.
9. **Vì sao không settle ngay hết kỳ?** Chờ hơn 600 giây để xử lý gói sự cố hợp lệ đang trễ, và phải hết pendingEvents; cấm rút tiền né phạt.
10. **Acknowledge trễ có xóa phạt không?** Không. Contract ghi chuyển cấp/vi phạm trước khi đóng sự cố khi cần; test đã kiểm tra.
11. **Tại sao không dùng MySQL thay blockchain?** Bên giữ database là bên có thể bị phạt; contract giữ tiền và thực thi luật, không chỉ ghi log.
12. **Chain chậm hoặc sức khỏe lộ công khai?** Cảnh báo đi MQTT/Telegram độc lập; on-chain chỉ có hash, dữ liệu thô ở off-chain. Luồng thực tế vẫn cần cả nhóm nghiệm thu.

## 6. Giới hạn và điều chưa chắc chắn

Chưa đạt E2E ba lần, chưa chạy Sepolia hoặc xác nhận lệnh flash ESP32. Unit keeper dùng RPC giả; dry-run đọc chain không chứng minh giao dịch thành công. SLA tính tới acknowledge, không tới hiện trường. Chữ ký thiếu miền chainId/contract. Chuyển ETH kiểu đẩy có thể thất bại với ví nhận từ chối ETH. Không dùng số gas local làm giá tiền hoặc tuyên bố hệ thống an toàn tuyệt đối.

## 7. Liên hệ với phần của người khác

P1 cung cấp contract và test chữ ký, review/merge main; P2 gửi lỗi kèm test, không tự sửa contract. P5 cung cấp vector/requirements/gateway/dashboard, nhận ABI và deployment P2 xuất. P3 cung cấp địa chỉ thiết bị, firmware và lệnh flash; P4 cung cấp model INT8/thông số đầu vào. Cả nhóm phối hợp baseline và video; P5 gộp báo cáo.

## 8. Ba câu tự kiểm tra

1. Một sự cố cấp 2 chưa acknowledge có deadline bằng 0: keeper làm gì và vì sao?
2. Plan hết kỳ nhưng còn pendingEvents: có settle được không, ai có thể giúp xử lý?
3. Số “66 test đạt” chứng minh điều gì và chưa chứng minh điều gì?
