# Triển khai sau phê duyệt — 15/09/2026

Người dùng đã phê duyệt PROPOSAL.md và EXTENSION_PLAN.md. Đợt triển khai hiện tại đã hoàn thiện nền một bãi (P0), có mã và UAT cho vòng đời/phí (P1), đã kiểm nội dung AI thật (P2), đối chiếu nghiệm thu lõi SQLite local (P3) và đang triển khai phần mở rộng. Đây không phải biên bản hoàn tất P0–P8 hoặc nghiệm thu ngân hàng/camera thật.

## Thay đổi và lý do

| Yêu cầu | Thay đổi | Bằng chứng chính |
|---|---|---|
| F01/F02/F08 | Manager/admin ghi khu/chỗ/loại/giá/vé tháng; staff đọc và xử lý khách/xe. API kiểm quyền theo thao tác; menu/nút dùng cùng ma trận. Giữ guard dữ liệu nhiều bãi. | `tests/test_core_crud_permissions.py`, frontend role tests |
| F01 | Manager tạo và khóa tài khoản staff thuộc bãi; tạo tài khoản và membership cùng giao dịch; không được đổi vai trò, sửa bản thân/admin/manager khác hoặc xóa user. | `tests/test_manager_staff_accounts.py` |
| F02 | Bật/tắt loại xe qua API/UI; ngừng nhận mới khi tắt, giữ lịch sử và các điều kiện bảo toàn lượt đang gửi. | Tests loại xe và nhận xe |
| F08 | Nhãn vé sắp hết hạn trong 7 ngày, tính theo ngày Việt Nam; các vé hết/còn hiệu lực vẫn tách rõ. | Frontend monthly status tests |
| F09–F12 | Phạm vi dữ liệu `operations`/`management` xét cả role tài khoản lẫn membership. Staff không truy vấn sổ thu khi tổng hợp; không truyền tài chính tới AI. | `tests/test_core_analytics_permissions.py` |
| F10/F11 | Lịch sử/replay AI tài chính không đọc được sau hạ quyền; kết quả cũ không có scope chỉ manager đọc; kiểm lại quyền sau provider. | 8 ca hồi quy ban đầu tái hiện lỗi trước sửa, sau sửa đạt |
| F09/F12 | Theo ngày/giờ có lượt vào, ra, tổng vào + ra; cao điểm tách từng chỉ số. Xe vào hôm trước vẫn tính lượt ra hôm sau. Prompt không biến tổng tuần thành tốc độ một ca. | `tests/test_core_site_analytics.py` |
| F09 | Xuất CSV UTF-8 cùng kỳ/số liệu/phạm vi như báo cáo UI; staff không xuất dòng tài chính; trường văn bản không thành công thức. | Export tests trong `test_core_analytics_permissions.py` |
| F13/P0 | Bộ demo độc lập một bãi, hướng dẫn chạy, UAT HTTP và kiểm tra backup/restore. | `SINGLE_LOT_DEMO.md`, scripts kiểm chứng, artifact cục bộ |

Các API cũ `/dashboard`, `/dashboard/revenue-chart`, `/parking/statistics`, `/reports/revenue`, `/reports/export/*`, `/ai/*` chứa tài chính được giới hạn manager/admin. Staff dùng báo cáo/AI theo bãi cho vận hành; vẫn nhận/trả xe, xem chỗ, tra cứu, quản lý khách/xe cần thiết và ca/chứng từ được phép.

## Demo và kiểm chứng

Khởi tạo từ DB mới, không chỉnh/xóa dữ liệu cũ. Bộ mẫu có một bãi, 3 khu, 40 vị trí (36 hoạt động, 4 dự phòng ngừng dùng), 476 lượt lịch sử tổng hợp trong 14 ngày, 14 ca đóng khớp tiền, 2 xe đang gửi và vé tháng còn/sắp/hết hạn. Tiền trong sổ mẫu được gắn ngữ cảnh dữ liệu giả lập của cả DB, không phải ngân hàng đã nhận tiền. QR demo vẫn tách riêng khỏi tiền mặt mẫu.

Hướng dẫn và launcher: [SINGLE_LOT_DEMO.md](../SINGLE_LOT_DEMO.md). Username `manager_demo`, `staff_demo`, `customer_demo`, `admin_demo`; mật khẩu ngẫu nhiên chỉ trong tệp credentials ignored của DB, không ghi ở tài liệu/memory.

Các lệnh từ Git root:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q --tb=short
& .\.venv\Scripts\python.exe scripts/verify_single_lot_core.py --credentials backend/artifacts/demo/single-lot-approved-20260915.db.demo-credentials.json --output backend/artifacts/demo/core-http-acceptance.json
& .\.venv\Scripts\python.exe scripts/verify_single_lot_recovery.py --database backend/artifacts/demo/single-lot-approved-20260915.db --output backend/artifacts/demo/core-recovery-acceptance.json
```

`verify_single_lot_core.py` chỉ nhận HTTP loopback và marker một bãi, ghi các bản ghi UAT có nhãn trong DB demo. Script không chạy với CSDL sản xuất hoặc gọi provider. Kiểm tra khôi phục tạo hai file mới, so sánh toàn bộ nội dung bảng qua hash, chạy integrity/foreign-key/readiness; không phục hồi đè DB nguồn.

Mốc P0 và phần P2 độc lập, chốt lúc 06:32 ngày 15/09/2026 (giờ Việt Nam), trước khi triển khai P1:

| Kiểm chứng | Kết quả | Bằng chứng cục bộ |
|---|---|---|
| Backend toàn bộ, mã đã ổn định | **1.359 passed, 20 skipped, 0 failed**, 1.755,56 giây; 199 cảnh báo datetime adapter SQLite/Python 3.12 | `pytest -q --tb=short`, exit 0 |
| Frontend | **155 passed**, lint và build exit 0 | `npm test`, `npm run lint`, `npm run build` |
| API trên DB UAT riêng | **58 bước PASS**, có ghi dữ liệu thử có nhãn | `backend/artifacts/demo/core-http-acceptance.json` |
| Backup/restore SQLite | **36 bảng khớp nội dung**, integrity/foreign-key/readiness PASS | `backend/artifacts/demo/core-recovery-acceptance.json` |
| Chrome với API fixture | **34/34 PASS** | `backend/artifacts/core-roles-ui/aec717b3d4/result.json` |
| Chrome với backend thật | **24/24 PASS**, không lỗi HTTP/render; số bản ghi nghiệp vụ giữ nguyên | `backend/artifacts/core-roles-live/6b637d64dd/result.json` và ảnh manager/staff |

Tại mốc P0, bản demo trình bày dùng DB `backend/artifacts/demo/single-lot.db` (nay giữ làm dữ liệu trước nâng cấp). UAT nghiệp vụ ghi vào `single-lot-approved-20260915.db`, không dùng file này làm bộ mẫu sạch. Kiểm UI thật đăng nhập manager/staff, chọn tuần kết thúc 14/09: 238 lượt vào, 238 lượt ra; manager thấy tổng thu, staff không thấy; vé hết 17/09 có nhãn sắp hết hạn. Hai lần chạy chỉ thêm bốn audit đăng nhập.

Manifest SHA-256 của 455 file mã/test/script tại mốc này ở `backend/artifacts/core-p0-source-manifest.json`. Artifact cục bộ nằm ngoài Git, không chứa mật khẩu/token. Kết quả là bằng chứng SQLite/local; không thay cho chạy PostgreSQL, Gemini, ngân hàng hoặc camera thật.

## SDLC và các lỗi đã phát hiện

- KT1: ma trận quyền, dữ liệu một bãi và phân biệt lưu lượng–tài chính từ phương án đã duyệt.
- KT2: Codex sinh/sửa dependency router và fixture role có chủ đích; default `test_user` vẫn staff, test nghiệp vụ cấu hình dùng `manager_user`. Không sửa kỳ vọng nghiệp vụ để hợp thức hóa lỗi quyền.
- KT3: truy vết `summarize → AIService → history/replay` phát hiện tài chính gửi tới staff; 8 test RED trước sửa. Bổ sung bối cảnh quyền và ngữ nghĩa lượt ra/tổng giao dịch trong prompt, kiểm bằng provider giả có quan sát đầu vào. Không dùng kết quả giả làm minh chứng AI live.
- Kiểm tra độc lập phát hiện thêm `/parking/statistics`, quản lý tài khoản nhân viên, export báo cáo, vé sắp hết và trạng thái loại xe; đã đưa vào phạm vi sửa đợt này.
- Đóng đường tổng phí fleet cho staff bằng cả quyền trả dữ liệu và SQL không tính tổng. Frontend hiển thị thiếu quyền riêng với giá trị thực bằng 0.
- Kiểm tra tranh chấp loại xe phát hiện vehicle cache cũ trong xác nhận đặt chỗ; refresh sau khóa rồi mới xét loại. Test hai connection đồng bộ ở lần ghi đầu vào `vehicle_types`, giữ kiểm chứng đúng trình tự khóa mới.
- Lượt toàn bộ đầu trong lúc agent còn cập nhật có một fixture staff cũ gọi thống kê manager-only; chạy lại riêng đạt rồi chạy toàn bộ mã ổn định đạt như bảng trên. Không dùng lần chạy chồng thay đổi làm bằng chứng cuối.
- UAT ban đầu dùng giả định sai về tên cờ cấu hình, mẫu số chỗ và mã HTTP từ chối xe trùng; sửa script theo hợp đồng thực tế (`SINGLE_SITE_ID`, tổng hoạt động 36, duplicate admission 400). Không đổi nghiệp vụ chỉ để làm script đạt.
- Kiểm tra SQLite thô ban đầu thiếu hàm `unicode_casefold` dùng bởi expression index; runner phục hồi đăng ký đúng hàm của ứng dụng rồi kiểm lại.

## P1 — mã và UAT sau thay đổi phí

Chính sách chi tiết tại [BILLING_AND_EXCEPTIONS.md](BILLING_AND_EXCEPTIONS.md). Lượt mới chốt giá `entry-v1` khi vào; vé tháng chỉ thu phần sau quyền lợi đã chốt. Snapshot và sự kiện ngoại lệ được bảo vệ tại ứng dụng và DB. Lượt cũ giữ nhánh tương thích, không điền giá lịch sử phỏng đoán.

Quản lý có thể hủy nhận nhầm, xác nhận mất vé và tạo vé thay thế khi sửa biển đủ điều kiện. Cả ba có lý do, người thực hiện và mã thử lại; hủy giữ lịch sử và trả chỗ. Lượt thay thế giữ giờ vào/giá/loại/chỗ, không sửa hồ sơ xe cũ. Tra cứu có mã lượt chính xác; báo cáo loại lượt đã hủy. UI hiển thị căn cứ giá server, lịch sử và lý do không đủ điều kiện.

| Kiểm chứng P1 | Kết quả đã xác nhận | Bằng chứng |
|---|---|---|
| Snapshot/phí/migration/race/checkout/scoped/seed | 140 passed; nhóm tài chính và seed cuối 23 passed | Các suite `test_billing_snapshot*`, `test_checkout*`, seed và tài chính |
| Ngoại lệ, migration và tranh chấp SQLite | 42 passed | `test_session_exceptions*` và migration |
| Tra cứu mã/cancelled/analytics | 31 passed; review độc lập mã/legacy 10 passed | `test_session_id_search.py`, `test_cancelled_analytics.py`, `test_core_site_analytics.py` |
| Frontend | 171 passed; lint/build exit 0 | npm test/lint/build |
| API với DB đã nâng cấp | 79 bước PASS | `backend/artifacts/demo/p1-core-http-acceptance.json` |
| Chrome trên backend thật | 38 kiểm tra chức năng PASS, 16 kiểm tra ảnh ổn định PASS; không HTTP/runtime errors | `backend/artifacts/p1-browser/07e42cebe0/result.json`, `f257e345f7/result.json` |
| Migration trên bản sao P0 | PASS; 478 lượt giữ snapshot NULL, 476 phiếu thu cũ nguyên vẹn; lặp migration không đổi dữ liệu | `backend/artifacts/demo/p1-upgrade-acceptance.json` |
| Backup/restore P1 sau UAT | 37 bảng khớp, integrity/FK/readiness PASS | `backend/artifacts/demo/p1-recovery-acceptance.json` |
| Backend toàn bộ baseline P1 | 1.469 passed, 20 skipped, 2 lỗi fixture, 970,00s; hai fixture đã sửa và kiểm lại đạt như mô tả dưới | Manifest `backend/artifacts/core-p1-source-manifest.json` |

Browser tạo đúng bốn thao tác nghiệp vụ trên DB UAT: nhận xe → sửa biển → xác nhận mất vé → hủy; chỗ trống trở về 35. Các lần kiểm/chụp ảnh thêm bảy audit đăng nhập. PDF vé thay thế được render kiểm tra một trang; vé sau hủy ghi rõ không còn hiệu lực. Root đã xem ảnh desktop/mobile.

Migration P0 gặp ba vé mẫu miễn phí chưa có thẻ/biên nhận. Trình nhập tài chính đã có của hệ thống bổ sung đúng ba thẻ và ba chứng từ 0 đồng, nguồn lịch sử không xác định; không gán người thu/ca/bãi phỏng đoán. Verifier cho phép đúng phần bổ sung được kiểm chứng đó: 33 bảng giữ nguyên mọi giá trị; ba bảng còn lại chỉ thay liên kết thẻ và thêm các dòng hợp lệ. 476 chứng từ cũ, 478 lượt và mọi giá trị cũ khác không đổi. Seed mới tạo sẵn ba thẻ/biên nhận DEMO 0 đồng để khởi động lặp không phát sinh nhập bù.

Các test không cộng thành một tổng duy nhất vì có phần giao nhau. PostgreSQL trong đợt này mới kiểm schema/catalog tĩnh; chưa chạy server PostgreSQL thực.

## P2 — Gemini thật và đối chiếu

Đã gọi Gemini thật năm ca trên DB tổng hợp mới `single-lot-live.db`: ngày, tuần, hỏi đáp chỗ/cao điểm, nhân sự, kỳ rỗng. 30 kiểm tra HTTP/lưu lịch sử/replay/phân quyền đạt. Context lấy từ dữ liệu đã lưu cùng mỗi lần sinh, không lấy snapshot ở thời điểm khác.

Artifact `backend/artifacts/demo/p1-live-ai-final-acceptance.json` hiện chỉ đạt **TRANSPORT_AND_PERSISTENCE_PASS**. Review nội dung phát hiện AI cộng hai nhóm giờ 17 và 18 (144 + 96 = 240 giao dịch cả tuần) nhưng ghi khoảng 17:00–18:00; đúng phải là 17:00 đến trước 19:00. Báo cáo tuần còn diễn đạt thiếu dữ liệu từng ngày dù đã có tổng theo ngày; phần thiếu thực tế là giờ theo từng ngày/ca và năng suất nhân viên. Đây là kết quả trước sửa, giữ trạng thái CHANGES_REQUIRED để làm bằng chứng phát hiện lỗi.

Lần chạy trong tài khoản sandbox bị chặn mạng, không sinh kết quả. Sau kiểm chứng nguyên nhân, tạo DB tổng hợp riêng thuộc tài khoản người dùng và chạy server/evaluator với quyền mạng đã được duyệt; không đổi ACL hoặc đưa key vào artifact. Đây là lỗi môi trường, không phải kết quả AI thành công.

## SDLC P1/P2 và giới hạn còn lại

- Tái hiện tám lỗi đếm/nhãn cancelled trước sửa; test xanh sau khi loại lượt hủy khỏi lưu lượng và sửa nhãn lịch sử.
- Các ca retry/tranh chấp dùng hai kết nối SQLite thực, kiểm số lượt/chỗ/chứng từ sau cùng; không chỉ kiểm phản hồi HTTP.
- UAT đổi giá 5.000 → 9.000 → 12.000 đồng xác nhận lượt đã vào giữ giá cũ, lượt mới dùng giá mới; bản sửa biển giữ cùng snapshot.
- P2 đã sửa prompt, 2 hồi quy RED→GREEN và 122 test AI/analytics đạt (34,64s). Gọi lại 5 ca Gemini/30 checks; root và reviewer độc lập đối chiếu đạt với hai ghi chú diễn đạt nhỏ. Không dùng output trước sửa làm bằng chứng nội dung đạt.
- P4–P8 tiếp tục theo phê duyệt: portal vé giờ/ngày/tháng, đặt chỗ có hạn, QR provider/hóa đơn/đối soát, OCR làn, CV ô và UAT tích hợp.
- Chưa commit/push/deploy; chưa giao dịch tiền thật hoặc kết nối camera vật lý. P1 có migration; sau phát sinh `entry-v1` phải dùng backend hiểu chính sách này, không rollback thẳng về P0.

DB trình bày hiện tại: `backend/artifacts/demo/single-lot-live.db`, server `http://localhost:8766` bật AI; mật khẩu nằm trong sidecar ignored tương ứng. DB trước nâng cấp và DB UAT được giữ riêng. Launcher mặc định AI tắt; chọn rõ DB khi chạy theo [hướng dẫn demo](../SINGLE_LOT_DEMO.md).

Ghi chú phiên bản kiểm: bộ hồi quy toàn bộ đã nạp baseline P1 trước bản sửa prompt khoảng giờ P2. Prompt mới được kiểm bằng suite AI riêng và gọi lại provider; không dùng lần full này để khẳng định prompt mới đã qua kiểm toàn bộ.

## Chốt lõi P1–P3 trước mở rộng

Lần full P1 kết thúc với **1.469 passed, 20 skipped, 2 failed** (970,00s, 212 cảnh báo datetime adapter). Cả hai lỗi ở fixture: test import cô lập chưa copy `core/billing_guards.py`; test migration chỗ đỗ dựng bảng lượt thiếu các cột lifecycle vốn tồn tại ở schema cũ. Đã sửa fixture đúng hợp đồng, giữ guard sản phẩm; **3 test import đạt 5,58s** và **69 test zone/snapshot migration đạt 13,90s**. Không gọi lần full ban đầu là xanh, không chạy lại toàn bộ chỉ để đổi số đếm sau hai sửa fixture. Kết quả mới/prompt được ghi riêng; hồi quy tích hợp toàn bộ sẽ chạy sau P4–P8.

Prompt P2 SHA256 `996767c692d16d3c549c199b2f9ef8bb6734efc4340fae9110b88e272d368094`. Năm câu trả lời mới ở `backend/artifacts/demo/p2-live-ai-acceptance.json`: **30 kiểm tra transport/history/replay/quyền và review semantic PASS** trong phạm vi bộ ca này. Staff dùng đúng17:00–trước19:00 khi cộng240 giao dịch; báo cáo tuần nhận biết dữ liệu ngày và chỉ nêu thiếu phân bố giờ×ngày/ca/năng suất. Hai ghi chú nhỏ không đổi số liệu: lặp từ “ca” một lần, dùng “doanh thu thực tế” ở kỳ rỗng sau khi đã ghi dữ liệu mô phỏng.

Browser mở đủ năm kết quả đã lưu với hai vai trò: **26 kiểm tra PASS**, nội dung hiển thị khớp output, đổi kỳ xóa kết quả cũ, staff không có tổng thu, desktop/mobile không tràn ngang. Artifact `backend/artifacts/p2-ai-browser/010b2dc7bd/result.json`; chỉ hai audit đăng nhập, không gọi thêm provider/ghi nghiệp vụ. Root đã xem ảnh. P1 UI đang hiển thị ký hiệu Markdown dưới dạng chữ; cải thiện trình bày được ghép vào đợt frontend mở rộng, không sửa nội dung AI đã lưu.

[CORE_ACCEPTANCE.md](CORE_ACCEPTANCE.md) đối chiếu F01–F13; [SDLC_EVIDENCE.md](SDLC_EVIDENCE.md) ghi KT1–KT3/cuối kỳ; [P1_VERIFICATION.json](P1_VERIFICATION.json) ghi kết quả máy đọc và giới hạn. **Lõi đủ bằng chứng SQLite/local để tiếp tục P4**; chưa nghiệm thu PostgreSQL, ngân hàng hoặc camera vật lý. P4 backend/frontend đang thực hiện theo [TIMED_PARKING_DESIGN.md](TIMED_PARKING_DESIGN.md); adapter payOS và capture edge được phát triển độc lập, chưa coi là tích hợp xong.


## Đợt mở rộng trước thanh toán phí lượt — 15/09/2026 07:53

P4 vé giờ/ngày đã có giữ chỗ, đơn bất biến, cấp vé/đặt chỗ cùng transaction và chính sách `prepaid-window-v1`. Review độc lập phát hiện guard INSERT từng chặn cả hold tương lai không chồng lấn; đã sửa nhất quán với quyền nhận xe có giới hạn thời gian và thêm regression. 11 kiểm tra độc lập tại `tests/test_timed_parking_acceptance.py` đạt (1,87s): đổi gói/bảng giá không đổi đơn, tới muộn không kéo dài gói, checkout chỉ thu 0/5.000/10.000 đồng quá giờ, replay và tổng thu không nhân đôi, vé ngày đúng 24 giờ, từ chối hoàn vé đã dùng và nhận sai chỗ. Các số tiền là dữ liệu test cô lập.

Bản P1 đóng băng bằng SQLite online backup có SHA256 `13103b579490490625f29260d5eb063320b4ec4857f8a269886a0ce8fcf46c96`. Rehearsal P4 ở `backend/artifacts/demo/p4-verified-3e222265a2c74c559fe5aba314763c15.verification.json` xác nhận mọi hàng/cột cũ của 37 bảng nguyên, source nguyên, initialize lặp lại/integrity/FK đạt. Đây là P4 trước ghép schema thanh toán online và CV; migration toàn bộ vẫn đang chốt. Hồi quy P4 rộng có 216 pass +2 expectation failures (DTO mới/migration head); sửa fixture/assertion và kiểm lại riêng2 pass; bộ P4/billing/migration/PG catalog86 pass. Không cộng các bộ trùng nhau.

P5 portal payOS có mapping tạo trước HTTP, inbox ký HMAC bất biến, worker GET phục hồi callback/response mất, cấp quyền qua ledger chung, review và quyết định quản lý nối thêm. 258 kiểm tra adapter/integration/portal/timed/finance đạt 75,24s; có3 tranh chấp SQLite file thực. Adapter122 kiểm tra riêng không phải cộng thêm258. Chưa gọi ngân hàng, chưa có tài khoản payOS. Demo server ép payOS tắt, bất kể cấu hình bên ngoài. Luồng trả phí lượt đang gửi là đợt kế tiếp tại [SESSION_FEE_PAYMENT_DESIGN.md](SESSION_FEE_PAYMENT_DESIGN.md), chưa triển khai hoặc nghiệm thu ở mốc này.

P6 capture agent28 kiểm tra offline. Camera receipt-health và privacy hiện35 pass/1 skipped (17,54s): hai regression RED cho GET/list sau giảm retention, rồi thêm RED giảm–tăng trước purge; đã sửa lọc trước phân trang, hạn DTO, và clamp hạn ảnh trong cùng transaction cấu hình để ảnh hết hạn không xuất hiện lại. Trạng thái mới chỉ nói có ảnh được nhận trong30 giây, không khẳng định thiết bị online.

P7 có hai bảng calibration/observation, thuật toán CPU `reference-diff-v1`, khoanh vùng và giao diện đối chiếu. 33 kiểm tra engine/API đạt theo đợt agent, chưa phải độ chính xác camera thực tế. Chỉ lưu quan sát CV, không ghi chỗ/lượt/tiền. Xem [OCCUPANCY_DESIGN.md](OCCUPANCY_DESIGN.md).

Frontend sau ghép P4/P5 portal/P6/P7:203 tests, lint và build đạt. Root thêm7 test trạng thái thanh toán (12 khi chạy cùng5 portal state), chống QR quá hạn/lạc đơn, URL khác host, tiền tệ/số tiền sai, mất response và response tới sau đổi tài khoản. Bundle P1 được giữ ở `backend/artifacts/p1-dist-before-extensions`. Browser trên schema mới và HTTP P4/P6 còn chờ candidate; chưa gọi toàn bộ mở rộng hoàn tất.

## Nghiệm thu HTTP P4/P6 và ghép trả phí lượt — 15/09/2026 08:10

Chạy `scripts/verify_single_lot_extensions.py` trên máy chủ local thật phát hiện lỗi: khách dùng vé giờ, ra sớm và trả chỗ nhưng đặt chỗ `arrived` vẫn chặn sức chứa đến hết khung giờ đã mua. Đã sửa predicate và các guard liên quan: đặt chỗ đã nhận xe chỉ giữ cam kết khi lượt liên kết còn `active`/`checking_out`; giữ nguyên lịch sử. Regression kiểm ra sớm → chỗ khả dụng → đơn mới trong khung cũ → hủy đơn → nhận xe vãng lai, còn quá giờ đang gửi vẫn chiếm chỗ. Hai bộ liên quan73 và66 test đạt, có phần trùng nhau.

Lần HTTP sau sửa **36 kiểm tra đạt**, artifact `backend/artifacts/demo/p4-p6-http-fixed-acceptance/result.json`: phân quyền khách/nhân viên/quản lý, đơn không nhận giá từ client, hold, cấp vé và phát lại, PDF, vào đúng khung, ra miễn phí gói và phát lại, sức chứa phục hồi. Sau đó chạy tiến trình capture thật đọc AVI tổng hợp và gửi2 frame qua HTTP; kiểm quyền ảnh, nhận ảnh gần đây, xác nhận biển không tự nhận xe, ngừng camera thu hồi token. **Không dùng webcam vật lý, không đo OCR và không nhận tiền thật**. Bản lỗi được giữ riêng, không sửa dữ liệu để làm test đạt.

Migration P4/P5 portal/P7 trước phí lượt có46 bảng, giữ nguyên mọi hàng/cột cũ của37 bảng P1. Artifact chính xác `backend/artifacts/demo/p4-p7-final-migration-41a29be862c24554983c3cdd02ac1b50.db.verification.json`; source hash không đổi, chạy lại migration/readiness/FK/integrity đạt. P7 bổ sung bảng FK calibration-slot thứ ba để ngăn ID ô bị xóa/tạo lại dưới vùng camera cũ; đổi ánh xạ trả unknown.36 kiểm tra API/engine và9 kiểm tra evaluator offline đạt; chưa phải số đo độ chính xác bãi thật.

Trả phí lượt online đang ghép backend/sổ thu. Giao diện mới phân biệt F tổng phí, C đã trả và D còn thu; hai regression đã tái hiện RED rồi GREEN cho trả đủ online không thu lại và từ chối DTO số dư mâu thuẫn. Bộ frontend tập trung25 test đạt cùng lint:13 checkout,8 QR,4 đề nghị phí. Chưa build bundle này hoặc nghiệm thu HTTP phần credit ở mốc ghi nhận.

Giao diện AI Markdown mới đã đọc lại5 kết quả lưu trên8766:23 checks đạt, dữ liệu trước/sau giống nhau, chỉ2 audit đăng nhập và không gọi model mới. Artifact `backend/artifacts/saved-ai-browser/da61bf2748/result.json`. Không dùng kiểm tra trình bày này thay thế review semantic P2.

## P8 — hồi quy toàn bộ, UAT trên schema06 và hợp nhất bundle — 15/09/2026 14:15

Full backend lượt 1 (11:18) thu thập 1.920 ca: 1.887 pass, **13 FAILED**, 20 skip. Cả 13 ca là test cũ chưa theo hợp đồng mới: checkout trả dict `F/C/D` với `check_out_time` có múi giờ +07 thay vì model; migration 06 đổi snapshot schema; helper `_put_checkout` dùng chung cho `test_session_exception_concurrency`. Sửa năm file test (`test_check_out_concurrency`, `test_expansion_migration`, `test_expansion_sites`, `test_release_safety`, `test_review2_regressions`), không sửa mã sản phẩm; chạy riêng 16 ca pass, file concurrency 4/4 ba lần liên tiếp. Lượt 2 ghi tại FINAL_ACCEPTANCE.

Bốn phát hiện provider còn mở trong handoff (bằng chứng sớm nhất khi GET lỗi; inbox chưa xử lý chặn đề nghị mới sau khi link cũ kết thúc; lượt hủy không tích phí ảo; thu hồi quyền/liên kết trong lúc tạo link không trả QR 200) đã có test tương ứng trong `tests/test_session_online_payments.py` và `tests/test_session_payment_concurrency.py` (hai connection SQLite thật, tham số thu hồi link/grant/user/membership/role/bãi). Tám file thanh toán chạy lại độc lập: 229 passed, 54,9 s.

Bundle frontend được build lại từ nguồn hiện tại vào `frontend/dist` (212 test, lint, build đạt) và dùng chung cho launcher và phiên UAT; `backend/artifacts/p5-credit-dist` chỉ còn là bản lưu. Phiên UAT 8769 trên DB mới seed schema06 (`p8-uat-8769-2109fe2bdee4.db`, `--single-lot --no-vision`, AI tắt): lõi 79/79, mở rộng 41/41 với `--session-payments`, browser phí lượt live-disabled 7/7 và fixture 29/29, recovery 48 bảng PASS, upgrade rehearsal 48 bảng PASS nguồn không đổi. Launcher `start_single_lot_demo.ps1` chạy thử dưới Windows PowerShell 5.1 trên cổng 8770: build, `/ready`, `SINGLE_SITE_ID` từ marker, dừng sạch. Artifact tại `backend/artifacts/demo/p8-uat-8769/` và `backend/artifacts/session-credit-browser/{5e335e07e0,9ef479cfa6}`.

Chưa nghiệm thu: PostgreSQL đang chạy, webcam/điện thoại vật lý, độ chính xác OCR/CV bãi thật, tài khoản payOS/ngân hàng. Mã vẫn ở working tree, chưa commit/push/deploy.
