# P2 — Đối chiếu bản GitHub nhóm

## Cập nhật 27/09/2026

Đã chuyển từ snapshot tải ngày 26/09 sang clone Git thực tế tại main `22ae021`. Các ghi chú “chờ nhóm chốt” của phiên trước không còn là blocker: main mới có AGENTS.md cập nhật và IC-01…IC-15 được xác nhận. Nhóm có 5 người.

| Khác biệt của bản P2 cũ | Bản tích hợp hiện tại |
|---|---|
| Chưa có source contract trong thư mục P2 | Dùng CareSLA.sol P1 trên main, không sửa source |
| getEvent | Đã chuyển test/keeper sang getFallEvent |
| Kỳ vọng settle ngay sau periodEnd | Test sau periodEnd +600 và pendingEvents =0 |
| Nonce theo thiết bị | Test nonce theo planId, thêm kịch bản plan bù nhìn |
| Không có vector chính thức P5 | Dùng docs/test_vectors.json trên main; 24 test P1 đạt |
| Demo chỉ plan 2 giờ | Thêm task --short-plan 5 phút theo IC-12, không đổi contract |
| Biến env setup riêng chưa thống nhất | Giữ danh sách IC-15, tùy chọn setup dùng tham số task |

Kết quả: **66 JavaScript +20 unit keeper đạt**. Deploy/setup thường và ngắn chạy local thành công, xuất ABI thật; keeper dry-run nhận được FALL quá hạn. Xem [báo cáo](P2_trien_khai_kiem_thu.md), [log](P2_test_results.txt) và [tiến độ](../progress/P2.md).

## Bối cảnh ngày 26/09 (lịch sử)

Snapshot CareSLA-main lúc đó có contract khác AGENTS.md nhưng nhóm chưa chốt; người dùng đã xác nhận chưa đồng ý thay đổi. Vì vậy P2 chỉ sửa cấu hình compiler, chưa áp dụng giao diện mới. Đối chiếu tạm thời đạt 23 test, lỗi 5 test settle và 1 pending getter; đó không phải kết quả bản hiện tại.

## Còn cần phối hợp

P1 review/merge nhánh P2; P3/P4 bàn giao firmware/model; P5 hoàn thiện gateway/dashboard và tích hợp ABI. Còn nghiệm thu keeper giao dịch thật, E2E 3 lần, README trên máy khác, Sepolia và video/ảnh báo cáo. Không tự tuyên bố hoàn thành các bước này dựa vào unit test.
