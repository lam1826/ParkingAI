# Hoàn thiện báo cáo, Gemini và tra cứu ngày cho một bãi

Phạm vi: ba khoảng thiếu người dùng yêu cầu sửa sau lần đối chiếu đề gốc ngày 08/09/2026. Nghiệp vụ mở rộng không thuộc đợt này. Kết quả website sẽ được cập nhật sau khi CI/CD và UAT provider thật kết thúc; chưa dùng kết quả cục bộ để kết luận bản online đã đạt.

## Hành vi và quyền

- Quản lý/nhân viên có quyền bãi mở **Báo cáo** hoặc **AI báo cáo & hỏi đáp** từ menu. Khách hàng bị từ chối; API legacy toàn hệ thống giữ nguyên guard.
- Chọn một ngày hoặc 7 ngày kết thúc ở ngày đã chọn. Server lấy lưu lượng, chứng từ và chỗ trống của đúng bãi; không nhận số liệu tự khai từ frontend. Ngày tính theo giờ Việt Nam, gồm trọn ngày cuối.
- Báo cáo sinh ngày/tuần, hỏi đáp chỗ trống/cao điểm và gợi ý nhân sự dùng Gemini qua service hiện có. Chỗ trống hiện tại có `as_of` riêng; không diễn giải thành tỷ lệ lấp đầy lịch sử. Số người đề xuất phải nêu giả định vì chưa có năng suất đã đo.
- Thu thực trừ hoàn theo ngày chứng từ; khoản QR demo hiển thị riêng. Lịch sử chưa xác định bãi không được tự gán lại.
- Lưu lịch sử trong `site_ai_analyses`: nhân viên chỉ xem kết quả mình tạo; quản lý/admin xem lịch sử của bãi được cấp quyền. Thu hồi quyền trong lúc provider đang xử lý cũng được kiểm lại trước khi lưu/trả kết quả.
- Một request đang gọi provider trên mỗi tiến trình. Retry cùng UUID/nội dung trả bản đã lưu, đổi nội dung cùng UUID trả 409. Bấm lặp được khóa ở giao diện; request ID tra log độc lập với UUID chống lặp. Không cam kết provider chỉ bị gọi đúng một lần khi nhiều tiến trình tranh chấp hoặc process chết trước khi lưu.
- Tại **Vận hành bãi → Tra cứu lượt gửi và cho xe ra**, chọn **Ngày vào từ/đến**, biển và trạng thái rồi bấm **Tìm lượt gửi**. Lọc theo ngày vào, không phải khoảng xe từng chiếm chỗ. Khoảng đảo ngược bị từ chối. Xóa hai ngày và tìm lại để bỏ lọc.

## API

Các đường dẫn bắt đầu bằng `/api/v2/sites/{site_id}`:

| Endpoint | Hợp đồng |
|---|---|
| `GET /reports/summary` | `period=day|week`, `anchor_date=YYYY-MM-DD` |
| `GET /ai/status` | Trạng thái cấu hình, tên model; không trả key |
| `POST /ai/analyses` | `kind=report|question|staff`, `period`, `anchor_date`, `question`, `request_id` UUID; từ chối field thừa |
| `GET /ai/analyses` | Lịch sử có phân quyền, `limit/offset` |
| `GET /ai/analyses/{id}` | Một kết quả được phép xem |
| `GET /sessions` | Thêm `date_from/date_to`, kết hợp biển, trạng thái và phân trang |

Frontend chỉ bật menu mới và ô lọc ngày khi backend công bố `site_analytics_enabled`, giữ tương thích trong thời gian triển khai. Runtime của website vẫn chọn bãi ID 2, không tạo/xóa bãi hoặc sửa dữ liệu cũ.

## Bằng chứng trước phát hành

- 14 ca RED xác nhận lỗi trước thay đổi; 17 ca trong `tests/test_core_site_analytics.py` kiểm quyền, ngày, dữ liệu, provider lỗi, retry và thu hồi quyền.
- Backend Windows: 1064 pass, 19 skip (các test dành cho môi trường riêng); PostgreSQL17 Unicode: 18 pass. Lượt thử sai môi trường C-locale trước đó thất bại ở case tiếng Việt; không thay ràng buộc nghiệp vụ để vượt qua.
- Frontend 142 test, lint và build đạt. Browser cục bộ 31 kiểm tra, viewport 1440/390, provider mock. Không phải nghiệm thu điện thoại vật lý.
- Model đã xác minh bằng API Google: `gemini-3.6-flash`. Smoke thật với dữ liệu tổng hợp trả đúng 12 lượt/08:00. Chưa thay cho nghiệm thu cả ba nhóm chức năng sau deploy.
- Log và ảnh ở `backend/artifacts/core-completion/`, ngoài Git. Không đưa mật khẩu, key, JWT, ảnh khách hoặc backup vào tài liệu công khai.

## Backup, migration và rollback

Backup public schema ở release `3afc56cad9cd6a4d43f56eb96766c7006141dd0f`, revision 20260908_02, 1.894.958 bytes; SHA256 `a7f60f74c79af9a8331b1c5f2eae9cdea77bddb41b790a1d19b9c4662fa7fdad`. Đã phục hồi vào PostgreSQL 17.11 loopback riêng, 36 bảng khớp số dòng. Nâng 20260908_03 giữ nguyên hash của mọi bản ghi cũ (trừ marker Alembic). Downgrade 02/re-upgrade 03 và deep readiness đạt trên bản sao.

Public-only dump không chứa định nghĩa managed extension. Đích phục hồi cần `btree_gist` trước constraint overlap. Rehearsal tạo database mới, chuẩn bị extension và bỏ riêng mục CREATE SCHEMA public trong TOC vì schema đã có; giữ mọi bảng/dữ liệu/constraint. Không restore đè website, không xóa dữ liệu phát sinh. Recovery point Supabase vẫn được kiểm riêng trong CD.

Revision 20260908_03 chỉ thêm bảng lịch sử. Nếu phải quay về app trước, rollback frontend tương ứng, tắt AI nếu cần và đưa marker về 20260908_02 bằng migration downgrade 03; migration giữ bảng và mọi kết quả. Triển khai image/SHA trước rồi kiểm readiness. Re-upgrade xác minh bảng được giữ. Không dùng migration tài chính cũ để xóa cột hay chứng từ.

Theo yêu cầu mới, đã stage `AI_ENABLED=true`, model hiện có cho lần deploy kế tiếp; không in hoặc thay key qua chat. Defaults phát triển/test vẫn fail-closed khi AI tắt. QR mô phỏng, 1 GB Fly và model OCR giữ nguyên.
