# Hoàn thiện báo cáo, Gemini và tra cứu ngày cho một bãi

Phạm vi: ba mục sửa theo đề gốc. Đã phát hành `0b8c54c15d940face4ca30b2dfb4b6cc3509b9ad`, gồm chỉnh prompt sau khi đọc kết quả Gemini thật. Báo cáo/AI đúng quyền và lọc ngày đã kiểm trên website. **Gate nghiệm thu đầy đủ: BLOCKED** bởi bộ duyệt tự động đối với lần ghi kết quả AI tiếp theo; người dùng đã cho phép nhưng bộ duyệt yêu cầu xác nhận cụ thể hơn. Chi tiết hiện tại ngay bên dưới, các mốc trước được giữ làm lịch sử.

## Cập nhật sau xác nhận và bản chỉnh prompt — 09/09/2026

Người dùng đã trả lời “cho phép” cho câu hỏi gửi thống kê tổng hợp bãi demo tới Gemini và lưu kết quả. Sau xác nhận, thử lại cùng UUID đã thành công: nhân sự 22,843 giây, kỳ rỗng 34,312 giây; API đạt111 kiểm tra. Tuy nhiên, đọc nội dung nhân sự phát hiện model gọi40 lượt cộng dồn theo cùng giờ trong tuần là “40 lượt/giờ”, đồng thời đề xuất bỏ trực khi0 lượt vào dù thiếu phân bố xe ra. Không coi HTTP201 là đạt chất lượng nội dung.

Bản `0b8c54c15d940face4ca30b2dfb4b6cc3509b9ad` bổ sung định nghĩa tổng cộng dồn theo giờ trong toàn kỳ, không suy định biên từ tổng tuần và không suy0 xe ra từ0 xe vào. Test hợp đồng prompt từng RED; sau sửa99 test AI/quyền/đầu vào đạt, sáu kết hợp kind/period được kiểm lại. Preflight Gemini thật với snapshot demo đã được phép đã trả đúng161 lượt vào/160 lượt ra,17:00 có40 lượt cộng dồn tuần; nêu cần đo xe ra/năng suất trước khi chốt số người. Preflight không ghi lịch sử production và không thay bằng chứng thao tác website.

[CI34268240778](https://github.com/lam1826/ParkingAI/actions/runs/34268240778) và [CD34269857506](https://github.com/lam1826/ParkingAI/actions/runs/34269857506) thành công. Linux1253 pass/22 skip; PostgreSQL16:18 pass; frontend142/lint/build; Windows191 pass/1 skip; OCR memory gate đạt. API đúng SHA,ready200,CORS và bundle `index-DFzXDObx.js` khớp. **Trên bản mới:62 kiểm tra API chỉ đọc và18 kiểm tra giao diện đạt**, không lỗi JavaScript/ghi nghiệp vụ. Ảnh viewport đã xem; không phải điện thoại vật lý.

Backup mới trước chỉnh prompt: release038d6c9,revision20260908_03,1.903.576 bytes,SHA256 `e3ea0160413d4cbf58c525cee0627f38e0d434e490ab42385a7710176d0ca9cb`. Đã phục hồi37 bảng trên PostgreSQL17.11 riêng, khớp counts và hash sau migration no-op. Cluster Temp cũ thiếu pg_notify được giữ nguyên; tạo cluster mới để phục hồi và dừng sau kiểm thử. CD kiểm recovery point Supabase hoàn tất2026-09-08T16:54:37.981000+00:00. Không đổi schema/UI/model/Fly; rollback prompt về038d6c9 giữ nguyên dữ liệu.

**Gate hiện tại: BLOCKED cho nghiệm thu đầy đủ sau chỉnh prompt.** Bộ duyệt tự động chặn lần gọi UAT mới dù đã có xác nhận. Đã trích hội thoại gốc: câu hỏi lúc17:24:37Z nêu Gemini và lưu kết quả, câu trả lời “cho phép” lúc19:12:09Z. Lần thử lại sau đối chiếu vẫn bị từ chối, lý do yêu cầu câu xác nhận nêu rõ payload/đích/side effect. Không đổi công cụ/endpoint để vượt chặn. Đã hỏi xác nhận cụ thể cho tối đa6 kết quả mới (5 API,1 UI), chỉ thống kê demo bãi2, không biển số/thông tin khách. Chưa có kết quả gọi mới trên bản0b8c54c.

Còn thực hiện sau khi được duyệt: chạy `online_core_uat.py` (đã ghim SHA mới, UUID mới cho prompt thay đổi; các UUID cũ được giữ riêng), đọc năm kết quả, rồi `online_core_browser.cjs` sinh một báo cáo qua nút UI. Script có lưu kết quả để tránh sinh lặp khi tiếp tục. Finalizer READY chỉ chạy khi có bằng chứng đủ, không dùng preflight hay test mock thay UAT này. PARK-217 giữIN_PROGRESS; PARK-218 đã xong menu/lọc ngày nhưng còn loại xe/bảng giá manager ngoài ba mục sửa; PARK-219 còn UAT/hồ sơ toàn đề.

Artifact tại `backend/artifacts/core-completion/` ngoài Git: `online-core-before-unit-fix.json`, `preflight-units-result.json`, `units-release-final.json`, `units-restore-evidence.json`, hai kết quả readonly và bằng chứng xác nhận trongprivate. Lỗi503 đầu và kết quả diễn giải sai được giữ để truy vết, không sửa lịch sử cho thành kết quả đạt. Không tăng tài nguyên hoặc thay key.

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

Gemini hiện đã bật (`AI_ENABLED=true`) bằng model hiện có; không in hoặc thay key qua chat. Defaults phát triển/test vẫn fail-closed khi AI tắt. QR mô phỏng, 1 GB Fly và model OCR giữ nguyên.


## Lịch sử nghiệm thu bản038d6c9 trước xác nhận tiếp tục

Trạng thái bên dưới là mốc trước câu trả lời “cho phép”; cập nhật hiện tại nằm ở đầu tài liệu.

CI [34253340017](https://github.com/lam1826/ParkingAI/actions/runs/34253340017) và CD [34255366293](https://github.com/lam1826/ParkingAI/actions/runs/34255366293) thành công. Linux: 1253 pass/22 skip; PostgreSQL 16: 18 pass; frontend 142 pass/lint/build; Windows 191 pass/1 skip; Docker/OCR memory gate đạt. Supabase recovery gate xác nhận backup hoàn tất `2026-09-08T16:54:37.981000+00:00`. API đúng SHA, `/ready` 200, CORS và checksum bundle `index-DFzXDObx.js` khớp.

API online chỉ đọc đã đạt62 kiểm tra: đăng nhập, menu capability, quyền của quản lý/nhân viên/khách, cách ly bãi, báo cáo ngày/tuần, lọc ngày và từ chối khoảng đảo ngược. Lượt vào và histogram giờ được so với danh sách session có phân trang; doanh thu so với sổ thu. Giao diện online đạt 18 kiểm tra; đã đăng nhập ba vai trò, xem báo cáo, lịch sử AI thật và lọc ngày; không ghi tiền hoặc lượt xe. Log/ảnh ở `backend/artifacts/core-completion/`, ngoài Git.

Gemini `gemini-3.6-flash` đã bật bằng cấu hình có sẵn. **Báo cáo ngày, báo cáo tuần và hỏi đáp của staff đã gọi model thật thành công**, nội dung được đọc và đối chiếu snapshot. Dữ liệu đúng bãi DEMO đã seed; doanh thu thực bằng 0, QR mô phỏng được tách riêng; không có biển số, tên khách hoặc credentials trong ngữ cảnh AI. Model phân biệt hiện trạng chỗ trống với kỳ lịch sử. Ba kết quả được lưu, replay cùng UUID trả cùng ID/nội dung. Thời gian lần đầu lần lượt37,359 /44,797 /8,656 giây. Readiness trong lúc AI chạy vẫn 200 (ba mẫu 0,172–0,313 giây; không phải kiểm thử tải).

**Chưa nghiệm thu xong gợi ý nhân sự:** lần gọi đầu trả 503 sau khoảng37 giây, không có kết quả được lưu. Lỗi được giữ trong `online-core-attempt1-503.json` và log request `core-uat-2ea4475f70de4571b8611c30a066931e`. Chưa đủ bằng chứng phân biệt quota, mạng hay nhà cung cấp tạm thời không sẵn sàng; không coi nhánh này đã đạt.

Bộ duyệt tự động ban đầu chặn việc gửi dữ liệu production tới Gemini. Sau62 kiểm tra chứng minh namespace demo/không PII/tiền thật 0, một lượt được duyệt và sinh ba kết quả trên. Tuy nhiên, lượt thử lại nhân sự tiếp tục bị từ chối với yêu cầu xác nhận riêng việc gửi thống kê demo sang Gemini và lưu lịch sử. Đã hỏi người dùng; chưa có xác nhận bổ sung tại thời điểm chốt biên bản. Không đổi endpoint, model hoặc chạy gián tiếp để vượt qua chặn.

Phần còn lại đã chuẩn bị: replay cùng UUID để thử nhân sự, báo cáo kỳ rỗng và một lần sinh qua nút giao diện; rồi kiểm lịch sử staff/manager. Chỉ thực hiện sau xác nhận. Do đó PARK-217 còn IN_PROGRESS. PARK-218 đã xong menu/báo cáo/lọc ngày, còn cấu hình loại xe/bảng giá cho manager ngoài ba mục sửa. PARK-219 tiếp tục theo dõi nghiệm thu/hồ sơ toàn đề. Điện thoại vật lý và vận hành bãi thật chưa được kết luận đạt.

Minh chứng SDLC: yêu cầu sửa ba điểm là prompt thực tế của task; 14 ca RED xác nhận route/lọc ngày thiếu,17 ca tập trung GREEN sau sửa; prompt thực thi ở `AIService.generate_scoped_analysis`. Unit test mock và kết quả Gemini thật tách riêng. Không sửa AGENTS/skills/hooks hoặc cấu hình điều phối agent nên không chạy regression suite agent mới theo sdlc-eval; test sản phẩm không được báo thành agent eval.
