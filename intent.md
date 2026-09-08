# Intent — ParkingAI theo đề bài gốc

## Phạm vi hiện tại — đề bài gốc là căn cứ ưu tiên

Ngày 08/09/2026, người dùng yêu cầu bám sát đề **Hệ thống quản lý bãi đỗ xe có tích hợp AI**, mức cơ bản, một bãi có nhiều khu/vị trí. Hai vai trò nghiệp vụ chính là quản lý và nhân viên. Không phát triển tiếp nhiều bãi.

**Kết quả bắt buộc:** quản lý khu/vị trí/loại xe, phương tiện, vào/ra và thời gian gửi, tính phí, chỗ trống theo khu, tra cứu biển số/thời gian, vé tháng hoặc khách quen, thống kê lưu lượng/doanh thu/cao điểm. Ba chức năng AI chính là báo cáo ngày/tuần, hỏi đáp dữ liệu bãi xe và gợi ý nhân sự; có minh chứng sử dụng AI ở KT1/KT2/KT3/cuối kỳ và test tương ứng.

**Điều kiện thành công:** từng yêu cầu có đường thao tác đúng quyền trên bản nộp; dữ liệu AI do backend tổng hợp đúng bãi/kỳ, không tự tạo số liệu; nghiệm thu AI Engine thật phải ghi riêng với test mock. Camera nhận diện biển không thay phần AI báo cáo. Không lấy tổng số test hoặc số tính năng mở rộng để công bố phần trăm hoàn thành đề bài.

**Ràng buộc:** giữ FastAPI/React, SQLite/PostgreSQL, một bãi và dữ liệu hiện có; không nới guard, không tăng gói có phí. QR mô phỏng; credentials/model/ảnh/hồ sơ Word ngoài Git. Người dùng đã cho phép bật Gemini, gửi thống kê tổng hợp demo và lưu kết quả. Bộ duyệt tự động vẫn yêu cầu xác nhận cụ thể cho các lượt UAT tiếp theo; không chạy vòng qua chặn.

**Không phải trọng tâm:** camera, portal khách, QR, đặt chỗ, waitlist và quản lý đội xe là phần bổ sung; giữ phần đã chạy nhưng không mở rộng trước khi hoàn tất yêu cầu bắt buộc. Điện thoại thật còn chờ người dùng; không để hạng mục tùy chọn này thay thế ưu tiên AI phân tích.

**Trạng thái sau sửa:** bản `0b8c54c` đã phát hành, menu Báo cáo/AI và lọc ngày đạt. Nhân sự/kỳ rỗng đã gọi Gemini thật sau xác nhận; phát hiện lỗi diễn giải đơn vị giờ, sửa prompt và preflight lại đạt. Còn nghiệm thu tạo kết quả sau chỉnh prompt và nút AI trên website vì auto-review chặn. Chi tiết [CORE_AI_COMPLETION.md](docs/CORE_AI_COMPLETION.md). Loại xe/bảng giá manager và minh chứng toàn đề còn theo dõi riêng.

**Căn cứ và công việc:** [docs/ORIGINAL_REQUIREMENTS.md](docs/ORIGINAL_REQUIREMENTS.md), PARK-217/218/219 và đầu `plan.md`. Những mục dưới đây là intent lịch sử vòng 3, không phải yêu cầu mở rộng hiện tại.

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
