# Hoàn thiện báo cáo, Gemini và tra cứu ngày cho một bãi

Phạm vi: ba khoảng thiếu người dùng yêu cầu sửa sau lần đối chiếu đề gốc ngày 08/09/2026. **Release gate: READY cho ba mục sửa trên website trình diễn**, sau khi kiểm Gemini thật, quyền Báo cáo/AI và tra cứu ngày. Ứng dụng hiện tại `0b8c54c15d940face4ca30b2dfb4b6cc3509b9ad`. Không dùng kết luận này thay nghiệm thu toàn bộ đồ án hoặc vận hành bãi thật.

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

Gemini đã bật bằng cấu hình hiện có trên website; key không thay đổi và không đưa vào chat/Git. Người dùng đã cho phép gửi thống kê tổng hợp bãi demo tới Gemini và lưu kết quả. Defaults phát triển/test vẫn fail-closed khi AI tắt. QR mô phỏng, 1 GB Fly và model OCR giữ nguyên.


## Nghiệm thu website ngày 09/09/2026

Ứng dụng `0b8c54c15d940face4ca30b2dfb4b6cc3509b9ad` đã qua [CI 34268240778](https://github.com/lam1826/ParkingAI/actions/runs/34268240778) và [CD 34269857506](https://github.com/lam1826/ParkingAI/actions/runs/34269857506). Linux 1253 pass/22 skip; PostgreSQL 16: 18 pass; frontend 142 pass/lint/build; Windows 191 pass/1 skip; Docker/OCR memory gate đạt. API đúng SHA, readiness 200, CORS và checksum frontend khớp. Không đổi schema, UI hoặc model trong bản chỉnh prompt cuối.

API online đạt **111 kiểm tra**, gồm năm đầu ra Gemini thật: báo cáo ngày, báo cáo tuần, hỏi đáp của nhân viên, nhân sự và kỳ rỗng. Kiểm quyền quản lý/nhân viên/khách, cách ly dữ liệu, lịch sử của staff, retry cùng UUID và ngày đảo ngược đều đạt. Lưu lượng và histogram được so với session phân trang; doanh thu so với sổ thu. Cùng UUID trả cùng ID/nội dung, không tạo thêm bản ghi lịch sử. Thời gian của lượt chạy sau bản sửa (replay nếu có): daily: 17.188 giây, weekly: 27.781 giây, question: 10.656 giây, staffing: 15.797 giây, empty: 11.047 giây; đây không phải p95 hoặc kiểm thử tải.

Giao diện online đạt **21 kiểm tra**: đăng nhập ba vai trò, mở Báo cáo/AI, đổi ngày/kỳ, xem lịch sử, một lần bấm sinh báo cáo gọi Gemini thật và tra cứu khoảng ngày rỗng. Không lỗi JavaScript hoặc ghi nghiệp vụ ngoài đăng nhập/lịch sử AI. Đã xem ảnh viewport 1440/390; không tính là thử điện thoại vật lý.

Nội dung năm kết quả API và kết quả mới qua UI đã được đọc, đối chiếu với snapshot server. Báo cáo ngày có 3 lượt vào/2 lượt ra; kỳ 7 ngày có 161 lượt vào/160 lượt ra, khung 17:00 có 40 lượt vào cộng dồn toàn kỳ. Câu hỏi xác định đúng cao điểm/chỗ trống. Nhân sự chỉ đề xuất phân bổ và nêu dữ liệu còn thiếu trước khi chốt định biên. Kỳ rỗng nêu chưa đủ dữ liệu để xác định cao điểm; hiện trạng chỗ trống được tách khỏi kỳ lịch sử bằng thời điểm `as_of`. Doanh thu thật bằng 0; tiền QR demo tách riêng. Không có biển số, thông tin khách hoặc credentials trong ngữ cảnh gửi model.

### Lỗi đã thấy và xử lý

Lần đầu nhân sự trả HTTP503 sau khoảng 37 giây; retry sau khi người dùng xác nhận đã thành công bằng cùng UUID, không tạo trùng. Chưa đủ bằng chứng xác định nguyên nhân 503 cụ thể; không gọi đây là lỗi quota đã được chứng minh. API phản hồi lỗi rõ ràng, thống kê vẫn dùng được.

Khi đọc kết quả retry, phát hiện Gemini diễn giải 40 lượt cộng dồn cùng giờ trong tuần thành “40 lượt/giờ” và đề nghị bỏ trực làn khi không có xe vào, dù thiếu phân bố xe ra. Bản `0b8c54c` bổ sung định nghĩa đơn vị cùng giới hạn suy luận nhân sự vào prompt. Test prompt từng RED, sau sửa 99 test AI/quyền/đầu vào đạt; sáu kết hợp ngày/tuần và ba loại phân tích giữ hợp đồng này. Preflight Gemini và nghiệm thu lại trên website đạt. Đây là bằng chứng cho các mẫu đã kiểm, không cam kết mọi câu trả lời tương lai luôn đúng.

Auto-review yêu cầu xác nhận riêng việc gửi thống kê demo/lưu lịch sử và vẫn chặn sau câu trả lời “cho phép” ban đầu, kể cả khi đã đối chiếu hội thoại gốc. Người dùng sau đó xác nhận cụ thể gửi thống kê bãi demo ID2 tới Google Gemini và lưu tối đa6 kết quả mới (5 API,1 UI); chỉ tiếp tục trong phạm vi này sau khi được duyệt. Kết quả thất bại/lỗi diễn giải cũ được giữ nguyên trong artifact riêng; không sửa nội dung lịch sử để làm thành kết quả đạt.

### Backup và bàn giao

Trước bản chỉnh prompt, đã backup lại release `038d6c9`, revision `20260908_03`: 1.903.576 bytes, SHA256 `e3ea0160413d4cbf58c525cee0627f38e0d434e490ab42385a7710176d0ca9cb`. Phục hồi 37 bảng vào PostgreSQL 17.11 riêng, khớp counts và hash dữ liệu sau migration no-op. Cluster Temp cũ thiếu thư mục nên đã giữ nguyên và tạo cluster mới; chỉ bản phục hồi mới được tính đạt. Cluster thử đã dừng. CD tiếp tục kiểm Supabase recovery point. Bản này chỉ chỉnh prompt: có thể rollback ứng dụng về `038d6c9` mà giữ nguyên schema/lịch sử.

Tại website: quản lý/nhân viên chọn **Báo cáo** để xem số liệu; chọn **AI báo cáo & hỏi đáp**, ngày/kỳ rồi sinh báo cáo, hỏi hoặc gợi ý nhân sự. Khi provider báo lỗi, chờ rồi thử lại trong màn hình; cùng mã yêu cầu tránh trùng kết quả đã lưu. Tra cứu lượt gửi dùng **Ngày vào từ/đến → Tìm lượt gửi**; hai mốc tính trọn ngày Việt Nam.

PARK-217 DONE. PARK-218 đã xong menu/báo cáo/lọc ngày; còn cấu hình loại xe/bảng giá cho manager ngoài ba mục sửa. PARK-219 giữ IN_PROGRESS cho UAT/hồ sơ toàn đề. Điện thoại vật lý, tập ảnh OCR đại diện và vận hành bãi thật vẫn chưa được kết luận đạt. Credentials, backup, prompt/output thô và ảnh màn hình ở `backend/artifacts/core-completion/` hoặc thư mục private hiện có, ngoài Git; hồ sơ Word vẫn chỉ cục bộ.

Minh chứng SDLC: yêu cầu sửa ba điểm là prompt thực tế của task; 14 ca RED ở đợt bổ sung API/lọc ngày, 17 ca tập trung GREEN; lỗi diễn giải được phát hiện từ model thật và sửa tại `AIService.generate_scoped_analysis`. Mock và live được ghi riêng. Không đổi AGENTS/skills/hooks hay cấu hình điều phối nên không phát sinh suite agent theo sdlc-eval; không gọi test sản phẩm là agent eval.
