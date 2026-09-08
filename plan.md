# Plan

## Objective
Hoàn thiện bản đồ án ParkingAI với cổng khách hàng, QR thanh toán mô phỏng, đặt chỗ, quản lý nhiều bãi thuộc cùng đơn vị và camera điện thoại dùng YOLO/OCR.

## Context / Existing Behavior
Ứng dụng FastAPI, SQLAlchemy và React/MUI đã có nghiệp vụ vào/ra, báo phí có chữ ký, xác nhận thu tiền, vé tháng, sổ thu và chốt ca. Các module mở rộng đã có phần lớn backend nhưng chưa ghép đủ giao diện, migration và hướng dẫn demo. Mốc gốc: f9e80a6f99555ce9ed219f576df0517804be7462.

## Scope
- Hồ sơ khách được xác minh; quyền xem xe/lượt gửi được kiểm tra tại server.
- Gói vé, đơn hàng, QR ngẫu nhiên có nhãn DEMO; thành công/thất bại/hủy, hoàn mô phỏng, PDF, thông báo.
- Bãi, quyền nhân viên, đặt chỗ, giữ chỗ, danh sách chờ và đội xe doanh nghiệp.
- Ảnh từ điện thoại, YOLO nhận diện vùng biển số và OCR, nhân viên duyệt; dự báo/backtest và kịch bản nhân sự.
- Nâng cấp schema an toàn, dữ liệu và bộ chạy demo riêng, kiểm thử, tài liệu sử dụng.

## Out of Scope
Thanh toán ngân hàng thật, barie tự động, cam kết độ chính xác biển số Việt Nam khi chưa có bộ đánh giá, SaaS đa doanh nghiệp. Không đưa dữ liệu giả vào cơ sở dữ liệu vận hành.

## Files / Components Affected
backend/expansion, backend/models, backend/main.py, backend/database.py, backend/db_rollout.py, backend/postgres_readiness.py, backend/alembic/versions, frontend/src/pages/Expansion, routes/layout/context, tests, docs và scripts demo.

## Implementation Steps
1. Chốt backend mở rộng và kiểm thử quyền, trạng thái, tranh chấp. Phụ thuộc nghiệp vụ hiện có; xác minh bằng pytest theo module.
2. Hoàn thiện migration SQLite/PostgreSQL, backfill bãi mặc định, giữ dữ liệu/constraint. Phụ thuộc model đã chốt; kiểm thử clone DB cũ, migration lặp, rollback.
3. Ghép giao diện cổng khách, quản trị đơn, bãi, đặt chỗ, camera và dự báo. Phụ thuộc API; lint/build, test xử lý payload và trình duyệt desktop/mobile.
4. Tách API quản trị cũ khi có nhiều bãi để quyền bãi không bị vượt qua. Kiểm thử tài khoản và đường dẫn trực tiếp.
5. Chuẩn bị demo riêng và hướng dẫn chụp từ điện thoại, QR mô phỏng, dữ liệu tổng hợp. Kiểm tra khởi động và quy trình end-to-end.
6. Chạy toàn bộ kiểm tra phù hợp, ghi bằng chứng, cập nhật trạng thái và snapshot báo cáo sau khi code ổn định.

## Risks
Migration CHECK SQLite, quyền truy cập chéo bãi/khách, xử lý thanh toán lặp, xung đột đặt chỗ, dữ liệu giả bị hiểu là dữ liệu thật, model OCR khác định dạng biển số thực tế.

## Test / Verification Plan
pytest toàn bộ; kiểm tra PostgreSQL khi có runtime; npm test/lint/build; demo API và trình duyệt trên database riêng; YOLO/OCR trên ảnh thật có nguồn; kiểm tra bản đóng gói/snapshot. Không coi test mock là bằng chứng độ chính xác OCR.

## Rollback / Recovery
Migration SQLite chạy trên candidate và chỉ thay sau preflight/readiness; giữ backup theo db_rollout. Demo dùng tệp DB riêng, không thay cấu hình triển khai hiện tại. Không phát hành khi còn lỗi kiểm tra bắt buộc.

## Open Questions
Không cần tài khoản thanh toán hoặc camera thật cho phạm vi đồ án. Model có metadata giấy phép khác model card; tài liệu phải ghi nguồn và giới hạn đúng thực tế.

## Status
### Review/debug vòng 2 ngày 08/09/2026
- Nguồn yêu cầu: `docs/REVIEW_ROUND2_2026-09-08.md`, backlog `docs/tickets/epics.json` và `docs/tickets/tickets.json`.
- P0 PARK-101–104: đã tái hiện bằng test đỏ và sửa bốn lỗi chặn demo: dữ liệu email legacy làm v1 serialize 500; replay portal giữ khóa SQLite và làm mất audit; upload ảnh giữ connection/cạn pool và audit chặn event loop; SPA demo che API `/dashboard`.
- Kiểm chứng P0 theo module: 94 test đạt. Pipeline camera hiện giảm tải trước DB, không giữ transaction lúc decode/OCR; pool PostgreSQL timeout mặc định 5 giây; audit SQL chạy ngoài event loop.
- Tiếp theo: P1 theo cụm vận hành/bất biến đặt chỗ (PARK-105–108, 113), frontend bền (PARK-109–110), bảo mật API/proxy (PARK-111–112), rồi P2 release/PG/vision/thời gian (PARK-114–117).
- Rollback cụm P0: revert commit P0; không có migration và không đổi dữ liệu. Các file hồ sơ báo cáo cục bộ vẫn ngoài Git theo `.gitignore`.

### Nghiệm thu độc lập theo yêu cầu được gửi lại ngày 07/09/2026
- Hoàn thành đối chiếu mã tracked/untracked, giữ bốn nâng cấp A–D đã có; sửa tám nhóm lỗi được tái hiện: quyền bảo đảm chỗ sau đổi chủ, khoảng lọc không hợp lệ, ảnh bãi đóng, lỗi nguồn phụ làm ẩn portal/vô hiệu nhận xe/mất lịch đặt chỗ, fleet thiếu retry và crash đơn khi danh sách tải lỗi.
- Giữ kiểm thử RED/GREEN; thêm 27 ca backend và một ca frontend. Hai kết nối SQLite kiểm tra chuyển chủ giữa lần đọc/lần ghi: guard rollback 409, không xác nhận lỗi mới.
- Bản cuối: 1.141 backend đạt/7 bỏ qua/0 lỗi, 130 frontend đạt, lint/build exit 0; 11 kịch bản React và 9/9 nhóm UAT với 12 ảnh, không lỗi JavaScript/console/tràn ngang. PostgreSQL thực và thiết bị điện thoại vật lý chưa được kiểm chứng.
- Word 103/15 trang đã cập nhật từ bản hiện tại, backup/render/QA và giữ 26/5 ảnh, định dạng gốc. Snapshot 444 file đồng bộ và kiểm tra byte sau chốt tài liệu. Kết luận READY cho demo SQLite tại docs/EXPANSION_RELEASE_GATE.md; chi tiết docs/ACCEPTANCE_REVIEW_2026-09-07.md.
- Không push/deploy, không thay DB/cấu hình đang có; các server UAT/profile đều riêng. Các trạng thái và số liệu bên dưới là lịch sử.

### Đợt 2 ngày 07/09/2026: kiểm chứng bản sửa, review giao điểm và bốn nâng cấp
Kế hoạch (thực hiện ngay, cập nhật kết quả bên dưới khi có bằng chứng):
1. Kiểm chứng bảy nhóm sửa bằng chính test hồi quy mới và các reproduction cũ (đồng hồ thật, hợp đồng v1/zone/legacy renew). Không hoàn tác.
2. Review giao điểm phân quyền/tiền/đặt chỗ/ảnh/dự báo/frontend/migration; chỉ ghi lỗi có tái hiện.
3. Nâng cấp A: lọc bãi/trạng thái/khoảng giờ và phân trang tại server cho đặt chỗ, phân bổ, danh sách chờ (khách và bãi); thứ tự ổn định có khóa phụ `id`; giữ dạng mảng trả về để tương thích caller; frontend đọc trang >100 và về trang đầu khi đổi bộ lọc.
4. Nâng cấp B: DTO tường minh cho báo cáo đội xe, tổng lượt/tổng phí tính trên toàn tập được cấp quyền, phân trang lịch sử.
5. Nâng cấp C: tách `useRemote` theo từng phần màn hình bãi/cổng khách/đặt chỗ, retry riêng, mutation làm mới đúng phần phụ thuộc; giữ bảo vệ kết quả trả muộn và bài `tests/browser/remote_hook_regression.py`.
6. Nâng cấp D: coverage dự báo gồm số giờ có bản ghi, số giờ điền 0, cảnh báo lịch sử thưa, độ đầy đủ quan sát "chưa xác định" khi không có nhật ký nguồn; test rỗng/thưa/nhiễu/múi giờ/tương lai.
7. Chạy toàn bộ pytest, frontend test/lint/build, UAT trình duyệt desktop và viewport điện thoại trên DB demo mới; cập nhật tài liệu, Word và snapshot.

Kết quả đợt 2:
- Bảy nhóm sửa: 28 bài hồi quy đạt; reproduction độc lập xác nhận đồng hồ thật đã ổn, hai bài còn lại đổi sang hợp đồng mới (409/422) đúng tài liệu. Không hoàn tác.
- Review giao điểm (agent chỉ đọc, 11 probe): không có P0–P2; sửa 3 lỗi P3 có tái hiện (đặt chỗ chủ cũ chặn chủ mới; 403/404 lộ id ảnh; đơn DEMO qua nửa đêm kẹt xét duyệt); 4 điểm chính sách đưa vào backlog.
- A: 5 endpoint có lọc bãi/trạng thái/khoảng giờ/xe và phân trang ổn định (`tests/test_expansion_booking_pagination.py`, 9 đạt trên 130+15+120 bản ghi xen kẽ). B: DTO đội xe 8 trường, tổng trên toàn tập, phân trang (`tests/test_expansion_fleet_report.py`, 8 đạt). C: `RemoteSection`/`usePage`/`refreshAll`, ba trang tách phần; hook trình duyệt 2 kịch bản đạt; UAT lỗi riêng API, đổi bãi nhanh, đổi bộ lọc, đăng nhập lại. D: coverage giờ có bản ghi/điền 0/thưa/“chưa xác định”, 6 test mới.
- Toàn bộ pytest: 1.114 đạt, 7 bỏ qua, 0 lỗi (lượt đầu 1 bài cũ thất bại vì hợp đồng 404 đổi có chủ đích, đã cập nhật assertion và chạy lại sạch); frontend 129 đạt, lint/build exit 0. PostgreSQL thực vẫn chưa chạy.

### Đối chiếu review Claude và sửa lỗi ngày 07/09/2026
- Người dùng đã xác nhận: kiểm chứng rồi sửa các lỗi đã xác nhận. Không mở rộng sang thanh toán/nghiệm thu PostgreSQL thực.
- Đã tái hiện và sửa bảy nhóm lỗi: clock danh sách chờ; khu legacy thiếu bãi/readiness; v1 nhận xe không vị trí; gia hạn legacy làm mất phạm vi vé portal; xác nhận đến sát hạn ghi dở giao dịch; vị trí đổi bãi trong lúc nhận xe; reload cũ sau đổi bộ lọc làm trang tải mãi.
- Đã thêm 28 trường hợp backend và một kịch bản trình duyệt React thật. Giữ kiểm tra rollback, quyền bãi, retry và giao dịch đồng thời. Assertion cũ được bổ sung tham số phạm vi bãi, giữ các điều kiện cũ.
- Lượt pytest toàn bộ cuối: 1.086 đạt, 7 bỏ qua, 0 lỗi (523,08 giây); frontend 129 đạt và lint/build exit 0; browser hook đạt; UAT mới 8/8 với 11 ảnh, không lỗi JavaScript/tràn ngang. Bằng chứng tại docs/CLAUDE_REVIEW_RESPONSE.md và docs/EXPANSION_IMPLEMENTATION_STATUS.md.
- Máy chủ demo cổng 8765 đã nạp mã mới, giữ DB demo hiện có và trả ready; chưa đẩy Git hoặc thay website bên ngoài. Word đã chốt kết quả mới, giữ 103/15 trang và cách trình bày gốc; snapshot 436 file đồng bộ và kiểm tra khớp nguồn. Kết luận READY cho demo SQLite cục bộ tại docs/EXPANSION_RELEASE_GATE.md.

### Mốc bàn giao trước review
- Code backend, UI quản trị/khách/bãi/camera/dự báo, migration và demo runner đã ghép; kiểm thử nhóm và build đã chạy.
- Đã kiểm chứng YOLO/OCR CPU trên ảnh thật: tìm đúng vùng nhưng đọc sai; trường hợp no_plate được ghi nhận riêng.
- Đã sửa lỗi QR mất sau refresh, dữ liệu bãi cũ khi chuyển lựa chọn, phương án nhân sự cũ, vé hết hạn, UUID trên HTTP LAN và worker bỏ sót batch nhắc vé.
- Đã chốt pytest: 1.058 đạt, 7 bỏ qua (6 PostgreSQL thật, 1 POSIX trên Windows); frontend 129 đạt, lint/build exit 0; UAT 8/8 với 11 ảnh desktop/mobile, không có lỗi JavaScript hoặc tràn ngang.
- Demo mặc định đã tạo riêng, bốn tài khoản được kiểm tra, máy chủ cổng 8765 trả ready. Bản mở rộng chưa đẩy Git/chưa thay website đang vận hành.
- Hai file Word đã hoàn tất: báo cáo 103 trang, hướng dẫn 15 trang; cập nhật mục lục và kiểm tra bản render, giữ bố cục/font/màu/ảnh/lề gốc. Bản sao trước chỉnh sửa ở ParkingAI-Report-Work/backup-before-demo-20260907.
- Snapshot hồ sơ đã đồng bộ 431 file và kiểm tra khớp nguồn, không có artifact chạy thử. Phạm vi demo đã hoàn thành; kết luận READY cho SQLite cục bộ tại docs/EXPANSION_RELEASE_GATE.md. Các giới hạn và bước phát triển tiếp được ghi tại docs/EXPANSION_IMPLEMENTATION_STATUS.md.
