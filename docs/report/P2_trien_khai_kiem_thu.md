# P2 — Triển khai và kiểm thử

Ngày 27/09/2026; nhóm **5 người**. Nền: main `22ae021`, IC-01…IC-15 đã chốt. Không sửa source contract P1 hoặc vector P5.

## 1. Môi trường và cách tái tạo

Node 24.16, npm 11.13, Hardhat 2.29.1, ethers 6.17, OpenZeppelin 5.6.1, Python 3.13/web3 7.16. Compiler solc 0.8.24, optimizer 200, viaIR, Cancun. `npm ci` đã chạy thành công; lần compile đầu biên dịch 11 file Solidity, các lần thu log sau dùng cache.

Tại `contracts/`: `npm run test:required`, `npm run test:gas`. Tại gốc: `python -m unittest discover -s contracts/test -p "test_*.py" -v` với Python đã cài requirements. Thu log bằng `node scripts/collect_results.js` tại contracts khi có local node/deployment.

## 2. Kết quả thực tế

| Nhóm | Kết quả | Phạm vi |
|---|---:|---|
| Nghiệp vụ P2: caresla.test.js | 29/29 | Ký quỹ, quyền, ca trực, chữ ký/nonce/timestamp, ACK, ARRIVAL, 2 cấp, phạt/settle |
| Hồi quy giao diện P2 | 9/9 | Tuple/ID/pending, +600s, plan bù nhìn, ts sau kỳ, hoàn tiền chưa accept, ca chồng, ACK/ARRIVAL trễ |
| Chữ ký P1 với vector P5 | 24/24 | 69 byte, EIP-191, hash mẫu, khôi phục địa chỉ, FALL/ARRIVAL/CANCEL |
| Helper và toolchain P2 | 4/4 | ethers v6, byte order, API thư viện/compiler |
| Unit keeper | 20/20 | RPC giả: deadline, trạng thái, pending/retry, lỗi, reorg |
| Bộ thu kết quả | 6/6 exit 0 | Version, compile, test, required, unit keeper, dry-run local |

**Tổng JavaScript 66 passing, không failing/pending.** Bằng chứng đầy đủ trong [log text](P2_test_results.txt) và [JSON](P2_test_results.json). Dry-run chỉ chứng minh đọc chain, không gửi giao dịch. Chưa có ảnh chụp nghiệm thu; không thay ảnh bằng số liệu giả.

## 3. Triển khai local

Deploy script kiểm tra chainId/số dư, chờ receipt rồi sinh metadata và ABI thật cho backend/dashboard.

- Local chainId: 31337.
- Contract: `0x5FbDB2315678afecb367f032d93F642f64180aa3`, deployBlock 26.
- Deploy transaction: `0x67958080667af6c7f195a290bc61137c819f828918ab1c74e5e22e28a35e9534`.
- Gas deploy: **1.814.059**.
- Setup thường đã tạo planId 1: 0.01 ETH, SLA 60s, penalty 0.002 ETH, kỳ 2 giờ, 2 ca.
- Setup plan ngắn đã chạy: planId 2, kỳ 5 phút, thêm 0.01 ETH, thiết bị mẫu ngẫu nhiên; FALL eventId 1, tx `0xb2445ec3362e27e5fa34d5e7cc6618809dd3600e2a675da201beaadf26fa3c50`. Keeper dry-run nhận đúng sự cố level 0 quá hạn. Chưa thực hiện gửi timeout/settle bằng keeper/dashboard trong phiên này.

Địa chỉ/ID trên chỉ thuộc phiên local này; không có link Etherscan local. Restart node làm mất trạng thái. Người dùng phải deploy/setup lại, không dùng metadata trong Git như chứng nhận một dịch vụ luôn tồn tại.

## 4. Gas đo trên test local

Lệnh `npm run test:gas` ngày 27/09/2026, 66 test đạt. Số gọi là số reporter ghi nhận trong bộ test, không phải lưu lượng thiết bị thực. Kết quả có thể lệch nhẹ khi chữ ký/dữ liệu ngẫu nhiên thay đổi; không quy đổi USD hoặc giả định giá gas Sepolia.

| Hàm | Min | Max | Trung bình | Số gọi |
|---|---:|---:|---:|---:|
| acceptPlan | — | — | 51.703 | 22 |
| acknowledge | 55.728 | 87.426 | 59.974 | 19 |
| checkTimeout | 40.801 | 60.119 | 50.441 | 41 |
| commitShift | 108.930 | 158.916 | 128.732 | 37 |
| confirmArrival | 52.559 | 99.947 | 74.035 | 10 |
| createCarePlan | 163.682 | 180.782 | 179.797 | 35 |
| reportFall | 215.520 | 249.732 | 245.094 | 37 |
| settle | 53.312 | 66.047 | 60.765 | 28 |

Trong các hàm đo, reportFall có gas trung bình cao nhất. Giải thích từ code: kiểm tra chữ ký và ghi nhiều trường sự cố; bảng không phải phép phân rã chi phí từng opcode.

## 5. Keeper và an toàn vận hành

Keeper Python quét log theo batch, dựng lại state, đọc eventCount/getFallEvent tại cùng block; lấy thời gian chain thay cho giờ máy. Chỉ xử lý sự cố chưa đóng và level <2. Trước tx có eth_call, dùng pending nonce, theo receipt, thử lại cùng raw transaction khi kết quả gửi chưa rõ. Không có quyền quản trị đặc biệt; bất kỳ ví nào cũng gọi checkTimeout được.

Khóa/URL có thể chứa API key không được ghi ra log; dùng .env và .gitignore. Không tự nới luật SLA, không giảm 600s để làm demo nhanh. Các test unit RPC giả không thay thế nghiệm thu restart/reorg/mất mạng trên Sepolia.

## 6. Chưa hoàn thiện và giới hạn

- Chưa nghiệm thu keeper thật/E2E đủ ba lần, phần cứng ESP32, Telegram và dashboard.
- Chưa deploy/verify/setup Sepolia; **chưa có địa chỉ/link Sepolia để báo cáo**.
- Chưa có ảnh chụp/video nghiệm thu, đánh giá README trên máy thành viên khác hoặc số liệu độ trễ toàn hệ thống.
- Phụ thuộc P3/P4/P5 cho tích hợp; người dùng cấp ví/RPC/ETH testnet riêng. P1 merge sau review.
- SLA đo tới acknowledge; chữ ký không gắn chainId/contract; ví nhận là contract có thể từ chối ETH khi settle.
- Mục tiêu kế tiếp: keeper giao dịch local → baseline E2E → Sepolia → bằng chứng thực nghiệm/báo cáo. Không ghi hoàn tất những bước chưa chạy.
