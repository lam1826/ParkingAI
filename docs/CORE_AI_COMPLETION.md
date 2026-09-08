# Hoàn thiện báo cáo, Gemini và tra cứu ngày cho một bãi

Phạm vi: ba khoảng thiếu người dùng yêu cầu sửa sau lần đối chiếu đề gốc ngày 08/09/2026. Nghiệp vụ mở rộng không thuộc đợt này. Đã phát hành ứng dụng `038d6c9eba6b45fbb29b23b54d13fb2947bbd028` lên website ngày 09/09/2026. **Release gate nghiệm thu trọn ba mục: BLOCKED**, còn xác nhận gửi thống kê demo tới Gemini để thử lại nhánh nhân sự và hoàn tất các ca provider bên dưới. Phát hành kỹ thuật đã thành công; không coi CI xanh là nghiệm thu đủ AI.

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


## Kết quả online và phần còn chờ — ngày 09/09/2026

CI [34253340017](https://github.com/lam1826/ParkingAI/actions/runs/34253340017) và CD [34255366293](https://github.com/lam1826/ParkingAI/actions/runs/34255366293) thành công. Linux: 1253 pass/22 skip; PostgreSQL 16: 18 pass; frontend 142 pass/lint/build; Windows 191 pass/1 skip; Docker/OCR memory gate đạt. Supabase recovery gate xác nhận backup hoàn tất `2026-09-08T16:54:37.981000+00:00`. API đúng SHA, `/ready` 200, CORS và checksum bundle `index-DFzXDObx.js` khớp.

API online chỉ đọc đã đạt62 kiểm tra: đăng nhập, menu capability, quyền của quản lý/nhân viên/khách, cách ly bãi, báo cáo ngày/tuần, lọc ngày và từ chối khoảng đảo ngược. Lượt vào và histogram giờ được so với danh sách session có phân trang; doanh thu so với sổ thu. Giao diện online đạt 18 kiểm tra; đã đăng nhập ba vai trò, xem báo cáo, lịch sử AI thật và lọc ngày; không ghi tiền hoặc lượt xe. Log/ảnh ở `backend/artifacts/core-completion/`, ngoài Git.

Gemini `gemini-3.6-flash` đã bật bằng cấu hình có sẵn. **Báo cáo ngày, báo cáo tuần và hỏi đáp của staff đã gọi model thật thành công**, nội dung được đọc và đối chiếu snapshot. Dữ liệu đúng bãi DEMO đã seed; doanh thu thực bằng 0, QR mô phỏng được tách riêng; không có biển số, tên khách hoặc credentials trong ngữ cảnh AI. Model phân biệt hiện trạng chỗ trống với kỳ lịch sử. Ba kết quả được lưu, replay cùng UUID trả cùng ID/nội dung. Thời gian lần đầu lần lượt37,359 /44,797 /8,656 giây. Readiness trong lúc AI chạy vẫn 200 (ba mẫu 0,172–0,313 giây; không phải kiểm thử tải).

**Chưa nghiệm thu xong gợi ý nhân sự:** lần gọi đầu trả 503 sau khoảng37 giây, không có kết quả được lưu. Lỗi được giữ trong `online-core-attempt1-503.json` và log request `core-uat-2ea4475f70de4571b8611c30a066931e`. Chưa đủ bằng chứng phân biệt quota, mạng hay nhà cung cấp tạm thời không sẵn sàng; không coi nhánh này đã đạt.

Bộ duyệt tự động ban đầu chặn việc gửi dữ liệu production tới Gemini. Sau62 kiểm tra chứng minh namespace demo/không PII/tiền thật 0, một lượt được duyệt và sinh ba kết quả trên. Tuy nhiên, lượt thử lại nhân sự tiếp tục bị từ chối với yêu cầu xác nhận riêng việc gửi thống kê demo sang Gemini và lưu lịch sử. Đã hỏi người dùng; chưa có xác nhận bổ sung tại thời điểm chốt biên bản. Không đổi endpoint, model hoặc chạy gián tiếp để vượt qua chặn.

Phần còn lại đã chuẩn bị: replay cùng UUID để thử nhân sự, báo cáo kỳ rỗng và một lần sinh qua nút giao diện; rồi kiểm lịch sử staff/manager. Chỉ thực hiện sau xác nhận. Do đó PARK-217 còn IN_PROGRESS. PARK-218 đã xong menu/báo cáo/lọc ngày, còn cấu hình loại xe/bảng giá cho manager ngoài ba mục sửa. PARK-219 tiếp tục theo dõi nghiệm thu/hồ sơ toàn đề. Điện thoại vật lý và vận hành bãi thật chưa được kết luận đạt.

Minh chứng SDLC: yêu cầu sửa ba điểm là prompt thực tế của task; 14 ca RED xác nhận route/lọc ngày thiếu,17 ca tập trung GREEN sau sửa; prompt thực thi ở `AIService.generate_scoped_analysis`. Unit test mock và kết quả Gemini thật tách riêng. Không sửa AGENTS/skills/hooks hoặc cấu hình điều phối agent nên không chạy regression suite agent mới theo sdlc-eval; test sản phẩm không được báo thành agent eval.
