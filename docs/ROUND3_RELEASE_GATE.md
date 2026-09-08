# ParkingAI — release gate vòng 3, 08/09/2026

**Overall: READY cho trình diễn đồ án online trong phạm vi dưới đây.** Bản tối ưu một bãi `3afc56c` đã phát hành và kiểm tra sau CD ngày 08/09/2026 (UTC+7); bằng chứng các release trước giữ riêng bên dưới. Nghiệm thu điện thoại vật lý vẫn chưa hoàn tất.

Phạm vi nộp bài hiện tại: **một bãi**, QR mô phỏng, Gemini tắt, nhân viên duyệt biển số, dùng website hiện tại. Khả năng nhiều bãi đã được kiểm tra ở vòng3 là bằng chứng lịch sử, không phải yêu cầu mở rộng tiếp. Đây không phải nghiệm thu vận hành bãi thật.


## Bản tối ưu từ hệ thống AI tham khảo — hiện tại

Đã tham khảo bảy hệ thống/dự án, sửa ba vấn đề có ca tái hiện: availability N+1, đọc BLOB thừa trong danh sách ảnh và đảo thứ tự chữ OCR. Không đổi schema, model, cấu hình Fly hoặc phạm vi một bãi. Bằng chứng nguồn, phép đo trước/sau và giới hạn: [SINGLE_SITE_OPTIMIZATION.md](SINGLE_SITE_OPTIMIZATION.md).

- Application `3afc56cad9cd6a4d43f56eb96766c7006141dd0f`; [CI34246127629](https://github.com/lam1826/ParkingAI/actions/runs/34246127629) và [CD34247663250](https://github.com/lam1826/ParkingAI/actions/runs/34247663250) thành công. Linux 1.235 passed/21 skipped, PostgreSQL: 17 passed, Windows release safety: 190 passed/1 skipped; frontend: 139 passed/lint/build. Docker OCR 6 ảnh, 1 CPU/640 MiB, đỉnh 350,6 MiB.
- Recovery gate đạt với backup Supabase hoàn tất `2026-09-07T16:54:11.668000+00:00`; đã lưu snapshot ứng dụng trước thay đổi. Không restore DB lại trong bản không đổi schema; bằng chứng restore PG17 vòng 3 vẫn ở phần lịch sử. CD xác nhận đúng SHA/ready/CORS lúc 22:55 UTC+7.
- 18 kiểm tra API sau CD đạt, gồm một upload OCR có nhãn/quyền sử dụng; ảnh được nhận dạng và vẫn chờ xác nhận, không tạo lượt gửi hoặc thanh toán. OCR lượt này 9,683 giây; không phải p95 hoặc accuracy. 31 kiểm tra giao diện bốn vai trò đạt, không lỗi JavaScript; có 4 cảnh báo Cloudflare CSP đã biết. Hai nhóm có phần kiểm trùng, không cộng thành số ca duy nhất; viewport không tính là điện thoại thật.
- Bundle `/assets/index-DU4U-j2Z.js` khớp SHA256 `072e94f8fda1a12e1d96324b5133a89d0762614dccbee705314bf28ce342d505`; `SINGLE_SITE_ID: 2` giữ nguyên. Artifact thô ở `backend/artifacts/single-site-optimization/` ngoài Git.
- OCR trực tiếp trên crop 457/500; cả YOLO/OCR trên crop 64/500; pilot toàn xe 20/20 cùng 9 FP. Đây là corpus hồi quy, không phải accuracy website hoặc test set độc lập. Điện thoại vật lý và nhãn pilot do người kiểm vẫn PENDING.

Backlog hiện tại 16 ticket: 13 DONE, PARK-209 IN_PROGRESS, PARK-210 DEFERRED_BY_USER, PARK-211 OPEN/FUTURE. PARK-214/215/216 DONE cho ba tối ưu; PARK-211 không còn lặp lại N+1, giữ phép đo tải API thực tế nếu cần sau đồ án. Commit biên bản chỉ đổi tài liệu, không là release ứng dụng mới.

## Lịch sử giao diện một bãi trước bản tối ưu

Phạm vi nộp bài đã thu gọn còn một bãi (demo A, ID2). Ứng dụng `76ef211821c52c3e5fae11bb5c980dcd8cabd35c` đã qua139 test/lint/build,33 kiểm tra trình duyệt cục bộ và31 kiểm tra trên website sau CD, gồm đăng nhập bốn vai trò và OCR status available. Lượt online không ghi nghiệp vụ hoặc upload ảnh, không có lỗi JavaScript; có bốn cảnh báo beacon Cloudflare bị CSP chặn đã được người dùng hoãn xử lý. Trước khi API triển khai có30 kiểm tra online; không cộng hai lượt thành61 ca độc lập. Mô phỏng viewport không tính là điện thoại thật. API/schema/model không đổi trong bản này.

Bundle online `/assets/index-DxpqSu6n.js` khớp SHA256 build `fee3926842a2a531fa7b0e1836f29e071c66ed14391b4c5c1ff4772cdff1f5d6`; `/config.js` đặt `SINGLE_SITE_ID: 2`. Snapshot HTML/config/bundle trước thay đổi được giữ tại `backend/artifacts/phone-vn-acceptance/pre-release/`. Việc thu gọn giao diện không cần migration hoặc sửa dữ liệu.

CI của đúng commit: [34241074566](https://github.com/lam1826/ParkingAI/actions/runs/34241074566) thành công. Linux1216 passed/19 skipped; PostgreSQL16 passed; Windows rollout190 passed/1 skipped; frontend139 passed, lint/build đạt. Container OCR một CPU/640MiB/network none xử lý6 ảnh, đỉnh345,1MiB. Bộ chấm điểm mới có21 ca đạt (nằm trong tổng Linux), không dùng kết quả mock làm accuracy model.

CD [34242469234](https://github.com/lam1826/ParkingAI/actions/runs/34242469234) thành công, gồm Supabase recovery gate. API công khai trả đúng SHA `76ef211821c52c3e5fae11bb5c980dcd8cabd35c`, `/ready` trả ready và CORS cho `https://parkingai.am` đạt. Lần cập nhật này không chạy restore DB mới; bằng chứng restore PG17 của vòng3 vẫn ghi bên dưới. Commit ghi biên bản sau bản này chỉ thay tài liệu, không phải release ứng dụng tiếp theo.

Đã có đo OCR trên500 crop thật có nhãn: OCR trực tiếp456/500 (91,2%), cả YOLO/OCR trên crop64/500 (12,8%). Pilot20 ảnh toàn xe:20 đúng toàn biển nhưng9 vùng thừa; nhãn agent chưa được người kiểm tra độc lập. Các số này không phải cam kết accuracy Việt Nam. iQOO Neo9/Chrome và iPhone/Safari vẫn PENDING vì chưa có kết quả thao tác vật lý. Chi tiết: [PHONE_VN_ACCEPTANCE.md](PHONE_VN_ACCEPTANCE.md). PARK-209 còn IN_PROGRESS; PARK-213 DONE trong phạm vi giao diện một bãi trên website.

## Lịch sử phát hành vòng3 trước giao diện một bãi

- Backend `3c6fdf2dac6e9627ef85e07d5672b08938e4c04a` vượt CI [34228923155](https://github.com/lam1826/ParkingAI/actions/runs/34228923155) và CD [34230062434](https://github.com/lam1826/ParkingAI/actions/runs/34230062434). API mới sẵn sàng lúc 13:12:24 UTC, trước khi push frontend `a99bfac`.
- Frontend `a99bfacdcbec4ea7109d2699be5b2732f4f691f1` vượt CI [34230768316](https://github.com/lam1826/ParkingAI/actions/runs/34230768316). Bundle `/assets/index-B-63aXU6.js` trên website khớp SHA256 của build. CD [34232996611](https://github.com/lam1826/ParkingAI/actions/runs/34232996611) triển khai API SHA này; không suy SHA release từ `head_sha` của workflow_run.
- Bản sửa OOM **`adc749f0fe9185c208ea964b6e9bd6bce8577c3e`**: CI [34232954119](https://github.com/lam1826/ParkingAI/actions/runs/34232954119) và CD [34234708346](https://github.com/lam1826/ParkingAI/actions/runs/34234708346) thành công, gồm backup gate. API công khai trả đúng SHA, `/ready` 200 tại thời điểm nghiệm thu; bundle frontend khớp build. Commit `970e828` ghi biên bản chỉ thay tài liệu, không phải SHA ứng dụng mới.
- Artifact thô nằm tại `backend/artifacts/round3/` ignored. Credentials, dump và manifest ID trong `private/`; không đính kèm vào GitHub, log công khai hoặc ticket.

## Các gate vòng3 đã kiểm tra tại bản adc749f

| Gate | Bằng chứng | Trạng thái |
| --- | --- | --- |
| Correctness/security | CI cuối: Linux1195 passed/19 skipped, PG16 passed/0 skipped, Windows release-safety190 passed/1 skipped. Trước hotfix OCR: Windows toàn bộ1192 passed/17 skipped. IDOR, role downgrade, cap nhiều xe, quote/retry, finance guards và AI disabled có test | PASS |
| Frontend | 134 test, lint, build đạt; browser cuối19 passed/0 failed, bốn vai trò, mobile không tràn ngang ở các trang đã thử; upload/crop/sửa biển số/chuyển màn hình nghiệp vụ đạt | PASS |
| Backup/restore | Dump public schema SHA256 `924e4ffca951b52d1c4d1f494635c1d2427234660d613dfcbf3cbc8241f1f747`; restore PG17 riêng, 36 bảng khớp số dòng; clone nâng schema và seed/replay đạt | PASS |
| Migration | `20260908_02`: nullable site_id, index/FK và guard; lịch sử không suy diễn bãi/số tiền; readiness và backup gate fail-closed trong CD | PASS |
| Seed | Hai bãi, bảy tài khoản, 32 chỗ, bốn camera, bốn gói, 56 ngày lịch sử tổng hợp có nhãn/0 phí; manifest committed đã tải về. Chạy lại trên production: committed, created={} | PASS |
| Dữ liệu cũ | Đối chiếu ID/hash của 79 bản ghi gốc thuộc 35 bảng: 79 còn nguyên, 0 thay đổi sau seed và UAT | PASS |
| API online | 237 kiểm tra, 0 lỗi: bảy login, hai bãi, hai khách, quyền v1/v2, QR failed/cancelled/success/refund/replay, PDF và cách ly ảnh; đây là kết quả trước khi phát hiện OOM ở giao diện | PASS trong phạm vi từng ca; không thay thế gate OCR |
| Xe vào/ra + audit | 31 kiểm tra, 0 lỗi trên website: nhận xe có vé tháng demo, quote 0, checkout, retry, trả chỗ, lịch sử khách, request ID đến audit; không sinh thu thật | PASS |
| OCR tài nguyên | Lỗi OOM cũ tái hiện; bản sửa đạt23 test liên quan. CI Docker640MiB/1CPU/network none:6 ảnh, đỉnh345,4MiB. API Fly cuối3 upload201, browser upload201, không có OOM mới trong lượt đo; API RSS/đỉnh371,2MiB, MemAvailable422,3MiB | PASS trong phạm vi kiểm tra ngắn, một ảnh đồng thời |
| Bảo mật artifact | Không track dossier, credentials, model, ảnh hoặc backup; log không xuất mật khẩu/JWT/chuỗi DB | PASS |

Các số skipped là skip thực, không tính thành pass. Suite Windows/Linux khác một ca quyền POSIX; test PostgreSQL chạy riêng bằng hai kết nối thật. CI thường không cài runtime/model OCR, nên ca tensor thật chạy riêng cục bộ; CI Docker chạy model thật trong gate tài nguyên. Kết quả cũ không được cộng với kiểm tra lại thành số lượng test duy nhất.

## Sự cố phát hiện và cách xử lý

13:25:43 UTC, upload ảnh từ website trên bản `3c6fdf2` làm Fly OOM/exit 137, máy tự khởi động lại. Lần API OCR trước đó trả 201 trong 12,321 giây và lượt đồng thời trả 429/Retry-After 3; kết quả đó không đủ kết luận ổn định. Bộ nhớ API trước lỗi: RSS khoảng 701 MiB, đỉnh khoảng 851 MiB, RAM khả dụng khoảng 64 MiB.

Đã tắt `PARKING_VISION_ENGINE` tại runtime để bảo vệ API. Test tái hiện tensor 736×2944 do RapidOCR phóng cạnh ngắn lên 736. Bản sửa giới hạn crop và đổi chế độ resize; CI thực thi inference trong container độc lập có hạn RAM, không thử thêm tiến trình nặng cạnh API production. Automatic approval review đã từ chối phương án benchmark trên cùng máy sau OOM; phương án CI độc lập đã chạy thành công. Không tăng cấu hình Fly hoặc mua dịch vụ.

Nguồn ảnh CC0 và model revision/checksum, giới hạn giấy phép được ghi trong [runbook](ROUND3_OPERATIONS.md). Không sử dụng kết quả ảnh này để công bố accuracy biển Việt Nam.

Sau khi CI/CD của bản sửa đạt, đã bật lại engine và thử API: cold10,624 giây; hai lượt tiếp theo0,553 và0,505 giây, đều201/recognized. Trong thời gian đó có28 yêu cầu readiness/nghiệp vụ, tất cả200; readiness chậm nhất0,785 giây, truy vấn lượt gửi chậm nhất3,782 giây. Lần tải đầu có độ trễ thấy rõ, cần đợi kết quả; số này không phải p95 tải thực. Fly giữ1CPU/1024MB, một máy chạy và máy dự phòng dừng như cấu hình có sẵn. Schema20260908_02, model checksum đúng, bảy tài khoản, AI_ENABLED=false, QR/showcase/YOLO bật. Chưa có bằng chứng vận hành OCR dài hạn hoặc tải đồng thời lớn.

## Giới hạn và công việc tiếp theo

- Cloudflare beacon còn bị CSP chặn; người dùng đã yêu cầu để sau. Giữ nguyên CSP. PARK-210: `DEFERRED_BY_USER`.
- Đã đo500 crop Việt Nam có nhãn publisher và pilot20 ảnh toàn xe; giới hạn nguồn/nhãn, kết quả detection/đúng toàn biển/tỷ lệ sửa ghi trong PHONE_VN_ACCEPTANCE.md. Chưa thử chụp trên điện thoại vật lý và chưa có bộ đánh giá đại diện cho bãi thực; viewport Chrome không thay cho thiết bị thật. PARK-209 còn IN_PROGRESS.
- QR không chuyển tiền; Gemini tắt; OCR không điều khiển barie, tự nhận/trả xe hay thu tiền.
- Không có kết quả tải lớn, video liên tục, độ bền dài hạn, SLA hay đối soát cổng ngân hàng. PARK-211 và các mục FUTURE.

Không còn gate bắt buộc thất bại trong phạm vi trình diễn đã chốt. Tại mốc trước bản tối ưu, backlog có13 ticket vòng3:10 DONE,1 FUTURE còn mở,1 IN_PROGRESS (PARK-209),1 Cloudflare hoãn theo người dùng. Các phần chưa có bằng chứng ở trên được giữ riêng, không gọi là đã hoàn thành cho bãi thật.

**Vận hành bãi thật: NOT READY.** Cần nghiệm thu các phần trên với dữ liệu, thiết bị, chính sách nghiệp vụ và phương án vận hành thực tế. Kết luận này độc lập với việc trình diễn đồ án.

## Bàn giao và rollback

Website: [parkingai.am](https://parkingai.am). Hướng dẫn vai trò, camera, seed và rollback: [ROUND3_OPERATIONS.md](ROUND3_OPERATIONS.md). Bốn tài khoản và kịch bản một bãi: `backend/artifacts/phone-vn-acceptance/private/TAI_KHOAN_DO_AN_MOT_BAI.md` trên máy người dùng. Bản bàn giao bảy tài khoản trước đây vẫn giữ riêng ngoài Git. Danh sách nhập Jira/Trello: [JSON](tickets/round3-tickets.json) và [CSV](tickets/round3-tickets.csv); chưa tạo ticket trên dịch vụ ngoài.

Nếu OCR lỗi, tắt engine trước, giữ nhập biển số thủ công. Nếu ứng dụng lỗi, quay về image/SHA trước tương thích schema, giữ các bản ghi mới. Chỉ phục hồi DB theo runbook đã thử trên đích riêng và đối chiếu chứng từ phát sinh; không reset DB, xóa ca/chứng từ hoặc downgrade schema tài chính. Backup public schema không bao gồm Supabase managed Auth/Storage/roles; recovery point nhà cung cấp vẫn được kiểm riêng trong CD.
