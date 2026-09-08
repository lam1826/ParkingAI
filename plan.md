# Plan

## PARK-209 — nghiệm thu điện thoại thật và biển Việt Nam (08/09/2026)

Điều chỉnh phạm vi trong lúc thực hiện: người dùng chỉ cần **một bãi để nộp đồ án**. Giao diện website chọn bãi demo A (ID 2 đã đối chiếu API), ẩn đổi/tạo bãi và chỉ công bố gói vé của bãi này. Cấu hình giao diện không thay quyền server, schema hoặc dữ liệu lịch sử. Dùng bốn vai trò admin/manager_a/staff_a/customer_a cho kịch bản nộp bài. Không triển khai thêm năng lực nhiều bãi.

- [x] Thu gọn giao diện một bãi qua `frontend/public/config.js`, bộ lọc catalog, bộ chọn bãi và trang vào mặc định; kiểm tra config sai/không có quyền không tự chọn sang bãi khác.
- [ ] Frontend test/lint/build, kiểm tra trình duyệt cùng API giả lập hai bãi để phát hiện chọn nhầm, ghi trạng thái phát hành rõ ràng.

Yêu cầu tiếp theo của người dùng: hoàn tất phần đo OCR Việt Nam và thử trên iQOO Neo 9/Chrome, iPhone/Safari. Không thay model hoặc cấu hình production trước khi có bằng chứng; đo cục bộ cùng mã và model đã phát hành. Ảnh, nhãn biển số, kết quả từng ảnh và thông tin thiết bị nằm trong `backend/artifacts/phone-vn-acceptance/` ngoài Git.

- [x] Chốt nguồn dữ liệu, điều kiện sử dụng, revision/checksum, nhãn gốc và cách chọn mẫu trước khi chạy nhận diện.
- [x] Thêm `edge/evaluate_plates.py` để đo detection ở IoU 0.5, đọc đúng toàn biển, CER, tỷ lệ gợi ý cần sửa và thời gian; tách ảnh crop/ảnh toàn xe, dữ liệu công khai/ảnh điện thoại. Không loại ảnh khó hoặc lỗi khỏi mẫu số.
- [x] Kiểm thử bộ tính điểm bằng kết quả biết trước, dữ liệu rỗng/sai, khớp một-một và ảnh trùng; chạy YOLO/RapidOCR thật, lưu kết quả tái lập.
- [x] Chuẩn bị `docs/PHONE_VN_ACCEPTANCE.md` và biểu mẫu riêng cho hai điện thoại; nghiệm thu thao tác vật lý chỉ từ kết quả người dùng thực hiện, không thay bằng viewport mô phỏng.
- [ ] Cập nhật PARK-209 và release gate theo kết quả thực đo; nêu rõ giới hạn mẫu, nguồn dữ liệu training chưa công bố và các tình huống chưa thử.

Tiêu chí: báo cáo các tỷ lệ cùng số đếm, không lấy confidence làm accuracy. Ảnh crop chỉ kiểm tra nhận diện trên crop, không chứng minh detection ngoài bãi. Mẫu độc lập với việc tinh chỉnh trong đợt này; không thể xác nhận không trùng tập training của publisher. Không thay đổi DB/schema, không benchmark tải trên Fly, không gọi Gemini. Rollback: bỏ công cụ/tài liệu nghiệm thu; runtime và dữ liệu website giữ nguyên. Câu hỏi còn mở: mẫu/version iPhone, kết quả thao tác hai điện thoại và ảnh/nhãn có quyền sử dụng do người dùng cung cấp.

## Vòng 3 — kế hoạch đã được người dùng duyệt 08/09/2026
- [x] PR-01: system map, 14 mục review, research, benchmark và backlog cập nhật.
- [x] PR-02: kiểm chứng correctness/security, nhất là cap đặt chỗ nhiều xe cùng khách.
- [x] PR-03: chốt ca/chứng từ/doanh thu theo bãi; sửa khu/chỗ trong phạm vi bãi.
- [x] PR-04: phân loại audit v2, request ID, timing và log worker.
- [x] PR-05: đóng gói YOLO/OCR online, bằng chứng crop/candidates/model; sửa OOM và đo lại trên Fly1GB.
- [x] PR-06: so sánh ba baseline và đo coverage khoảng ước lượng.
- [x] PR-07: UX bốn vai trò và mobile, xử lý lỗi/thao tác lặp.
- [x] PR-08: backup và restore rehearsal, deploy đúng SHA, seed namespace riêng, UAT online, bàn giao.

Quyết định: website hiện tại là nơi trình diễn; YOLO chạy trên Fly hiện có, chưa tăng gói. Gemini tắt; QR mock. Bổ sung nullable site_id cho ca/chứng từ, dữ liệu lịch sử không suy diễn bãi. API v1 giữ nguyên boundary; API mới theo v2/sites. Mật khẩu ngẫu nhiên lưu file ignored; không reset database.

Đã phát hành ứng dụng `adc749f0fe9185c208ea964b6e9bd6bce8577c3e`: CI34232954119/CD34234708346 đạt; public SHA và bundle khớp. Linux1195pass/19skip, PG16pass, Windows safety190pass/1skip, frontend134pass/lint/build; UAT API237, vào/ra31, browser19 đạt theo phạm vi ghi trong release gate. Seed2bãi/7tài khoản và replaycreated0;79 bản ghi cũ giữ nguyên; PG17 restore36bảng khớp. OCR ban đầu OOM được tái hiện/sửa, CI container riêng đạt; API cuối3upload201, RSS371,2MiB trên Fly1GB. Kết luận READY cho đồ án online, NOT READY cho bãi thật. Chưa nghiệm thu accuracy Việt Nam/điện thoại vật lý; Cloudflare được người dùng hoãn. Runbook: docs/ROUND3_OPERATIONS.md; biên bản: docs/ROUND3_RELEASE_GATE.md;12ticket JSON/CSV có9DONE,2FUTURE,1hoãn. Hồ sơ/credentials/model/ảnh/backup vẫn ngoài Git.

Kiểm tra từng batch trước khi chuyển tiếp: focused tests, regression liên quan, SQLite/PostgreSQL, frontend test/lint/build, Docker, CI, backup/recovery, release SHA và UAT. Rollback code nếu schema tương thích; không tự downgrade hoặc xóa chứng từ phát sinh. Mọi trạng thái bên dưới là lịch sử trước vòng 3.

## Objective
Hoàn thiện bản đồ án ParkingAI cho **một bãi đỗ xe**, với cổng khách hàng, QR thanh toán mô phỏng, đặt chỗ và camera điện thoại dùng YOLO/OCR. Năng lực nhiều bãi đã có là phần mở rộng trong mã, không thuộc kịch bản nộp bài hiện tại.

## Context / Existing Behavior
Ứng dụng FastAPI, SQLAlchemy và React/MUI đã có nghiệp vụ vào/ra, báo phí có chữ ký, xác nhận thu tiền, vé tháng, sổ thu và chốt ca. Các module mở rộng đã có phần lớn backend nhưng chưa ghép đủ giao diện, migration và hướng dẫn demo. Mốc gốc: f9e80a6f99555ce9ed219f576df0517804be7462.

## Scope
- Hồ sơ khách được xác minh; quyền xem xe/lượt gửi được kiểm tra tại server.
- Gói vé, đơn hàng, QR ngẫu nhiên có nhãn DEMO; thành công/thất bại/hủy, hoàn mô phỏng, PDF, thông báo.
- Bãi, quyền nhân viên, đặt chỗ, giữ chỗ, danh sách chờ và đội xe doanh nghiệp.
- Ảnh từ điện thoại, YOLO nhận diện vùng biển số và OCR, nhân viên duyệt; dự báo/backtest và kịch bản nhân sự.
- Nâng cấp schema an toàn, dữ liệu và bộ chạy demo riêng, kiểm thử, tài liệu sử dụng.

## Out of Scope
Thanh toán ngân hàng thật, barie tự động, cam kết độ chính xác ngoài bãi khi chưa có bộ đánh giá đại diện, SaaS đa doanh nghiệp. Không đưa dữ liệu giả vào cơ sở dữ liệu vận hành.

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
- PARK-105–114 và PARK-117 đã được triển khai cùng test hồi quy: worker production/expiry, horizon và cap đặt chỗ, guard ngừng khu, chống tự duyệt, frontend phục hồi sau chunk/mạng, ranh giới proxy/API, bất biến đặt chỗ, eviction/retention/trạng thái vision, timezone và thông báo waitlist.
- PARK-115 đã có cổng backup/PITR fail-closed trước migration, ghim Fly action và Docker digest, cùng runbook rollback frontend. PARK-116 thống nhất khóa `vehicle → slot` và thêm đường ghi PostgreSQL. Hai ticket này chỉ hoàn tất vận hành sau khi secrets/reviewer và CI PostgreSQL 16 thực tế đều xanh.
- Kiểm tra candidate cuối: backend **1.177 đạt/8 bỏ qua/0 lỗi** trong 640,01 giây; frontend 134/134, lint/build đạt, Impeccable detector `[]`. Smoke `start_demo.ps1` trên DB/cổng tạm trả ready, login, dashboard JSON và SPA 200.
- Bảng đối chiếu và điều kiện phát hành: `docs/REVIEW_ROUND2_RESOLUTION_2026-09-08.md`.
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
