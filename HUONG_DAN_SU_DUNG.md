# Hướng dẫn sử dụng bộ prompt cho AI agent

## 1. Đặt file vào repo
```
carensla/
├── AGENTS.md            ← bối cảnh chung (Codex tự đọc file này)
├── CLAUDE.md            ← Claude Code tự đọc, file này import AGENTS.md
└── prompts/
    ├── P1_truong_nhom_contract.md
    ├── P2_test_deploy_keeper.md
    ├── P3_iot_esp32.md
    ├── P4_ai.md
    └── P5_backend_dashboard_baocao.md
```
Commit các file này lên `main` **trước H0**, để mọi người cùng kéo về một phiên bản.

## 2. Cài đặt theo từng loại agent
- **Codex:** tự đọc `AGENTS.md` ở thư mục gốc repo.
- **Claude Code:** tự đọc `CLAUDE.md`, file này import `AGENTS.md` bằng dòng `@AGENTS.md`.
- **Antigravity:** ⚠️ chưa chắc Antigravity có tự đọc `AGENTS.md` hay không. Cách an toàn: đầu mỗi cuộc hội thoại, yêu cầu agent đọc cả hai file theo câu mở đầu ở mục 3. Hoặc dán nội dung `AGENTS.md` vào phần rules hoặc custom instructions của Antigravity, nếu công cụ có mục này.

Bộ prompt không phụ thuộc vào công cụ, nên ai dùng agent nào cũng được.

## 3. Câu mở đầu cho MỖI phiên làm việc
Thay `Px` và tên file cho đúng người:
```
Bạn là agent của P3 trong dự án CareSLA.
Hãy đọc AGENTS.md, prompts/P3_iot_esp32.md và docs/progress/P3.md (nếu có).
Sau đó tóm tắt trong 5 dòng: tôi đang ở giai đoạn nào, việc tiếp theo là gì,
và đang phụ thuộc vào ai. Chờ tôi xác nhận rồi mới bắt đầu.
```
Agent không nhớ giữa các phiên. File `docs/progress/Px.md` là "trí nhớ" của agent, nên cuối mỗi phiên luôn nhắc:
```
Cập nhật docs/progress/P3.md và docs/study/P3_on_phan_bien.md trước khi kết thúc.
```

## 4. Quy tắc cho người dùng agent
1. **Đọc hiểu code agent viết.** Mỗi mốc dành 15 phút đọc `docs/study/Px_on_phan_bien.md` và tự trả lời 3 câu tự kiểm tra. GV hỏi từng người, agent không trả lời thay được.
2. Agent muốn đổi giao diện chung (MQTT, cách băm, hàm contract) thì **dừng lại** và báo cả nhóm trước.
3. Không dán khóa riêng hay token vào khung chat nếu không cần. Dùng `.env` và `secrets.h`.
4. Agent đưa ra con số (độ chính xác, độ trễ, gas) thì hỏi lại "số này từ lần chạy nào?". Chỉ đưa vào báo cáo số đã thực sự chạy ra.

## 5. Các điểm đã chỉnh so với kế hoạch trước (cần cả nhóm biết)
- **Bỏ hàm `markFalseAlarm` on-chain.** Báo giả được lọc bằng cửa sổ hủy 10 giây trên thiết bị. Báo động nào đã lên chain thì nhân viên vẫn phải phản hồi (lập luận: ngoài đời nhân viên cũng phải kiểm tra).
- **Gộp `registerDevice` vào `createCarePlan`.** Gia đình ghi địa chỉ thiết bị, trung tâm chấp nhận, như vậy là hai bên cùng đồng ý.
- **Thêm hàm `hashEvent()` (pure)** để so hash khi debug chữ ký giữa ESP32, gateway và contract.
- **Mỗi ca có sẵn primary và backup**, dùng cho cơ chế chuyển cấp 2 tầng.
