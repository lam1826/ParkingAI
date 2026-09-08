# Kiểm tra bàn giao ParkingAI — 07/09/2026

**Kết luận: READY cho bản đồ án SQLite cục bộ.**

Lượt nghiệm thu độc lập đã kiểm tra mã hiện có, giữ bốn nâng cấp A–D, sửa tám nhóm lỗi được tái hiện bổ sung và chạy kiểm tra trên bản cuối. Không push/deploy, không thay database hoặc cấu hình đang có. Kết luận không áp dụng cho PostgreSQL, website đang vận hành hoặc sản phẩm thương mại. Chi tiết nguyên nhân, test RED/GREEN và đối chiếu yêu cầu tại [review nghiệm thu](ACCEPTANCE_REVIEW_2026-09-07.md).

## Điều kiện đã đạt

| Điều kiện | Kết quả và bằng chứng mới |
| --- | --- |
| Backend toàn bộ | **1.141 đạt, 7 bỏ qua, 0 lỗi**, 1.148 thu thập, 551,34 giây; `backend/artifacts/acceptance-current/backend-final.xml` và `.log` |
| Frontend | **130 đạt, 0 lỗi/0 bỏ qua**, `npm.cmd test`; lint/build exit 0 sau bản sửa cuối, log `backend/artifacts/acceptance-current/frontend-*.log` |
| React/component thật | **11/11 kịch bản**: portal/hook 5, workspace 6; lỗi riêng API, retry riêng, mutation refresh, mục 101, đổi bộ lọc và bãi; `review-remote/9b27169a41/result.json`, `workspace-sections/cd87016113/result.json` dưới `backend/artifacts` |
| UAT API và trình duyệt thật | **9/9 nhóm**, **12 ảnh**, 0 runtime exception/console error/cảnh báo, không tràn ngang; `backend/artifacts/uat/771c6a2fe6/summary.json`. Desktop 1440px và viewport mobile 390×844 |
| Quyền và giao dịch | Chủ mới không dùng quyền bảo đảm chỗ của chủ cũ; kiểm tra tranh chấp chuyển chủ với hai kết nối SQLite, trả 409/rollback; các hồi quy chủ xe, bãi, API cũ, thu/hoàn và xử lý lặp có trong lượt pytest cuối |
| A/B | Năm API được kiểm tra với tập sau lọc hơn 100 mục, biên múi giờ và khoảng sai; fleet 125 lượt qua 4 trang, DTO đúng tập trường và tổng toàn phạm vi; `tests/test_acceptance_booking_fleet.py` |
| C/D | Các nguồn dữ liệu tải/retry riêng, giữ thông tin đơn khi danh sách lỗi; coverage ghi số giờ có sự kiện/điền 0 và mức đầy đủ chưa xác định; UAT xác nhận đơn/vé/chứng từ cập nhật và đổi tài khoản không nhận dữ liệu cũ |
| SQLite/migration | Bộ pytest kiểm tra migration trên bản sao, readiness, integrity và bảo toàn nguồn; demo seeder chỉ tạo DB mới |
| YOLO/OCR | UAT chạy upload → YOLO ONNX/OCR cục bộ → nhân viên duyệt; không tự nhận xe. Kết quả OCR chỉ là gợi ý, không chứng minh độ chính xác biển Việt Nam |
| Word | Báo cáo **103 trang**, hướng dẫn **15 trang**, giữ **26/5 ảnh**, styles/numbering/theme và khổ/lề; có backup, cập nhật mục lục, render/QA. Manifest `../ParkingAI-Report-Work/acceptance-document-verification.json` |
| Snapshot | **444 file**, đồng bộ byte và kiểm tra không có DB, token, .env, model hoặc artifact; kết quả cuối ghi tại `backend/artifacts/acceptance-current/snapshot.log` và `verification.json` |

Các lượt chọn lọc có giao nhau, không cộng thành tổng kiểm thử. Hai runner React và 9 nhóm UAT chạy riêng ngoài 130 bài frontend/pytest. Bộ UAT được lưu tại `tests/browser/expansion_uat.py`; các lần lỗi do harness và sửa hợp đồng test được ghi trong review để truy vết. Nguồn cũ 1.086/1.114 test và UAT đợt 1–2 là lịch sử, không phải bằng chứng bản cuối.

## Giới hạn

Bảy bài bỏ qua gồm sáu bài PostgreSQL thực vì thiếu `POSTGRES_TEST_URL`/dịch vụ và một bài owner/group POSIX không áp dụng trên Windows. Có 193 cảnh báo datetime adapter sqlite3 trên Python 3.12; không tăng skip. SQL offline và SQLite không thay kiểm chứng khóa PostgreSQL.

QR là DEMO, không chuyển tiền ngân hàng; DEMO không được cộng vào tiền thực. Camera dùng ảnh, chưa phải video hoặc barie tự động. Chưa thử điện thoại vật lý, tải bãi thật, độ chính xác OCR biển Việt Nam hay SaaS nhiều doanh nghiệp. Dự báo dùng 56 ngày tổng hợp, không quảng bá chất lượng trên dữ liệu vận hành thật. Khác biệt giấy phép model đã ghi trong hướng dẫn camera.

## Chạy và khôi phục

Chạy `./scripts/start_demo.ps1` tại thư mục dự án; thêm `-Lan` để dùng cùng Wi-Fi. Khi cần buổi demo mới, dùng `-Database` với tên chưa tồn tại. Giữ database cũ và mật khẩu lúc tạo; không sửa marker hoặc .env. Bộ demo chạy bảo trì mỗi 30 giây và mặc định tắt LLM bên ngoài. Lượt nghiệm thu chỉ chạy dịch vụ trên DB mới tại cổng 18960, không nạp lại server 8765.

Trước vận hành thật: kiểm tra PostgreSQL trên môi trường riêng, migration/backup/restore trên bản sao mục tiêu, worker và giám sát; sau đó mới nghiệm thu ngân hàng hoặc camera thật. [Hướng dẫn demo](DEMO_GUIDE.md), [migration](EXPANSION_MIGRATION.md), [trạng thái và backlog](EXPANSION_IMPLEMENTATION_STATUS.md).
