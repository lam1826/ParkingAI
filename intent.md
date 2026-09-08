# Intent — vòng nâng cấp 3

## Phạm vi hiện tại sau điều chỉnh của người dùng
Ngày08/09/2026, người dùng thu gọn mục tiêu còn **một bãi để nộp đồ án**. Website chọn sẵn bãi demo A với bốn vai trò; không tiếp tục mở rộng nhiều bãi. Giữ quyền server và dữ liệu hiện có, không reset database để đổi giao diện. Nghiệm thu điện thoại vật lý còn chờ kết quả iQOO Neo9/iPhone; số đo OCR Việt Nam có giới hạn được ghi trong docs/PHONE_VN_ACCEPTANCE.md. Những mục dưới đây là intent lịch sử của vòng3 trước điều chỉnh này.

## Problem / Opportunity
Release caaef39 đã lên website nhưng thiếu dữ liệu/tài khoản trình diễn, QR và OCR chưa bật. Vận hành nhiều bãi còn thiếu chốt ca theo bãi; audit v2 phân loại chung và chưa có request ID.

## Desired Outcome
Một modular monolith cho một đơn vị vận hành nhiều bãi, nghiệp vụ và phân quyền chính xác, demo online trên website hiện tại với QR mô phỏng và YOLO/OCR cần nhân viên xác nhận.

## Success Criteria
Kiểm thử hai bãi/bốn vai trò, SQLite và PostgreSQL thực; chứng từ/ca không lẫn bãi; giữ quote 120 giây, idempotency và quyền lịch sử. Phát hành sau backup/restore rehearsal, chạy UAT sau đăng nhập, báo cáo riêng những giới hạn OCR và thiết bị chưa kiểm chứng.

## Constraints / Non-goals
Không SaaS, microservices, ngân hàng thật, tự mở barrier; không tăng tài nguyên có phí. Gemini mặc định tắt. Giữ hồ sơ báo cáo, credentials, DB, model và ảnh ngoài Git. Không sửa/xóa dữ liệu đang có để seed demo.

## Risks / Assumptions
Website được chủ dự án chọn cho trình diễn đồ án. OCR CPU phải đo trên máy Fly 1GB; chưa có bộ đánh giá biển Việt Nam. Dữ liệu production phải kiểm tra lại trước thay đổi, không dựa vào thống kê cũ.

## References
Kế hoạch người dùng duyệt ngày 08/09/2026; plan.md; docs/REVIEW_ROUND2_RESOLUTION_2026-09-08.md. Nghiên cứu vòng 3 ghi riêng nguồn primary và giới hạn bằng chứng.
