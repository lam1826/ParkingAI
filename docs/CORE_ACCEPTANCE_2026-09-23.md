# Nghiệm thu theo đề bài gốc — 23/09/2026

> Cập nhật: người dùng đã duyệt demo và yêu cầu triển khai. Bằng chứng dưới đây thuộc vòng kiểm tra lõi trước khi ghép giao diện; kết quả triển khai hiện hành ở [DEMO_IMPLEMENTATION_2026-09-23.md](DEMO_IMPLEMENTATION_2026-09-23.md). Không còn chờ duyệt prototype. Chưa commit/push/deploy.

Phạm vi: **một bãi phục vụ đồ án**, ứng dụng FastAPI/SQLAlchemy/React/MUI, SQLite cục bộ. Git base `5922894`; thay đổi đang ở working tree, chưa commit/push/deploy. Các CSDL kiểm chứng mới nằm trong `backend/artifacts/core-20260923/`, không ghi đè CSDL trình bày hoặc dữ liệu website.

**Kết luận hiện tại:** nghiệp vụ cốt lõi qua kiểm chứng HTTP thật 79/79 bước. Phần AI có mã, kiểm thử tự động và bằng chứng live lịch sử; **chưa chốt nghiệm thu toàn đề lần này** vì Gemini thật trả `503 UNAVAILABLE`. Prototype HTML không phải bằng chứng backend, xác thực, CSDL hoặc AI thật.

## Đối chiếu yêu cầu

| Mã | Yêu cầu | Mã / bằng chứng mới | Trạng thái trong đợt này |
|---|---|---|---|
| F01 | Đăng nhập, phân quyền quản lý/nhân viên | Auth, `site_scope.py`, core CRUD permissions; HTTP kiểm manager/staff và từ chối sai quyền | Đạt cục bộ; giữ Staff để đáp ứng đề, Admin bao gồm quyền Manager |
| F02 | Quản lý khu vực, vị trí, loại xe | Zone/slot/type routers; manager CRUD trong HTTP; menu danh mục và quản lý vị trí từ sơ đồ | Có và đã kiểm; thêm loại xe khác không cần thêm luồng nhận xe |
| F03 | Xe vào, thời gian vào, vị trí | `ParkingService`, scoped check-in; HTTP + lifecycle/concurrency tests | Đạt cục bộ; không bắt buộc đặt trước hoặc camera |
| F04 | Xe ra, thời gian gửi, trả chỗ | Checkout quote/xác nhận/thử lại; HTTP + concurrency tests | Đạt cục bộ; xác nhận thu và retry không tạo thu trùng |
| F05 | Phí theo loại và thời gian | Bảng giá, snapshot lúc vào, fee/monthly coverage tests; HTTP đổi giá và kiểm phí | Đạt các ca đã kiểm; không thay giá lịch sử |
| F06 | Chỗ trống theo khu vực | Availability API, regression giữ chỗ, hiển thị theo khu/tên loại | Đã sửa: loại ô đang giữ/ngừng phục vụ khỏi số nhận xe được |
| F07 | Tra cứu theo biển, thời gian | `search_sessions`, `/sites` và tests tìm kiếm; HTTP | Đạt; có thêm mã lượt/trạng thái |
| F08 | Vé tháng hoặc khách quen | Customer/vehicle/monthly APIs; HTTP cấp vé, nhận và trả xe được miễn phí | Đạt; test còn/hết hạn và coverage riêng |
| F09 | Lưu lượng, doanh thu, giờ cao điểm | `site_analytics`, reports/finance; HTTP báo cáo/CSV đúng quyền và tests kỳ/giờ | Đạt các ca đã kiểm; Staff chỉ xem vận hành |
| F10 | AI báo cáo ngày/tuần | `generate_scoped_analysis(kind=report)`, scoped AI API/history; AI regression | Có triển khai; live mới CHƯA ĐẠT vì provider 503 |
| F11 | AI hỏi đáp cao điểm/chỗ trống | `kind=question`, JSON tổng hợp theo bãi/quyền; prompt/integrity tests | Có triển khai; chưa chạy đến ca live mới do lỗi ở báo cáo ngày |
| F12 | AI gợi ý nhân sự | `kind=staff`; prompt yêu cầu nêu giả định, không bịa định biên | Có triển khai; chưa chạy đến ca live mới |
| F13 | Minh chứng AI trong SDLC | Bảng KT1–KT3 dưới đây; [bộ minh chứng hiện có](upgrade-2026-09-15/SDLC_EVIDENCE.md) | Markdown/code/test có nguồn; Word/slide lịch sử chưa xuất lại |

## Thay đổi thực hiện

- Sidebar chia vận hành/báo cáo, danh mục, quản trị và tài khoản. Camera/portal/CV nằm trong mục mở rộng có thể mở; giữ route và guard hiện có. Customer giữ luồng riêng. Thêm điều hướng bàn phím và nhãn trang đang xem.
- `/parking/available-slots` và thống kê hiện tại dùng cùng điều kiện giữ chỗ với nhận xe. Ô vật lý trống nhưng có reservation/allocation/đơn chưa thanh toán còn giữ chỗ không được gợi ý. API bổ sung `total_reserved`/`reserved_slots`; đọc thống kê không tự thay trạng thái đặt chỗ.
- UI theo khu chỉ đếm `available_now === true`; hiển thị tên loại xe. Sơ đồ danh mục phân biệt trống vật lý với nhận xe được, không coi loại xe ngừng hoạt động là chỗ có thể phục vụ.
- Ghim đồng hồ riêng test tương thích lượt không có ô để tránh chạy qua biên tính giờ. Không thay nghiệp vụ tính phí hay bỏ kiểm tra quote hết hiệu lực.

## Kiểm chứng mới

Các nhóm dưới đây có thể trùng ca; không cộng thành một tổng coverage hoặc gọi đây là lần chạy toàn bộ hệ thống.

| Nhóm | Kết quả | Phạm vi |
|---|---|---|
| Backend core baseline | 294 pass | Auth, quyền CRUD, khu/ô/loại, phí, khách, vé tháng, checkout và tìm kiếm |
| Backend sau sửa | 167 pass | 13 suite vào/ra, concurrency SQLite, chỗ trống, báo cáo, múi giờ, coverage vé và quyền analytics; gồm 7 hồi quy giữ chỗ mới |
| AI + analytics | 144 pass / 44,22 giây | Provider giả, prompt, dữ liệu rỗng/sai, lỗi provider, quyền, kỳ và thống kê; không gọi Gemini |
| Frontend | **227/227 pass**, lint/build đạt | Logs `backend/artifacts/core-frontend-tests.log`, `core-frontend-build.log`; build lại sau chỉnh bố cục cuối |
| Trình duyệt với API giả | **44/44 pass** | React thật, API fixture; quyền/menu, loại xe ngừng dùng, chỗ trống, bàn phím/desktop/mobile. `backend/artifacts/core-first-ui/434021e326/result.json` |
| Trình duyệt với API thật | **21/21 pass** | Manager/Staff đăng nhập, menu lõi, chỗ theo khu, báo cáo đúng quyền, desktop/mobile. `backend/artifacts/core-live-browser/8226aedb6e/result.json`; chỉ hai lần login, không ghi nghiệp vụ/gọi AI |
| HTTP ứng dụng thật | **79/79 pass** | `scripts/verify_single_lot_core.py`, DB riêng `acceptance.db`, `core-http.json`; provider tắt để kiểm cả trạng thái không sẵn sàng |
| Gemini thật | Chưa đạt | Hai lượt qua app ở môi trường có mạng dừng tại báo cáo ngày 503; chưa có output để review nội dung |

Lượt backend trước khi ghim test: 166 pass/1 fail; ca đó chạy riêng đạt nhưng phụ thuộc thời điểm ở biên giờ. Lượt 167 pass sau sửa là kết quả mới, không thay tên lượt lỗi thành đạt.

AI dùng đúng cấu hình Gemini hiện có, dữ liệu tổng hợp giả lập. Metadata model truy cập được; chẩn đoán tại seam của ứng dụng ghi `ServerError`, code `503`, status `UNAVAILABLE`. Không đổi model/key để che lỗi và không tạo báo cáo giả thay phản hồi provider. Lượt sandbox ban đầu bị chặn kết nối được giữ riêng. Artifact `ai-live-retry.json`, `ai-live-final.json`, `provider-diagnostic.json` chỉ chứa bằng chứng đã làm sạch; không có output AI thành công trong lần kiểm này. [Năm ca live đạt ngày 15/09](upgrade-2026-09-15/CORE_ACCEPTANCE.md) là bằng chứng lịch sử, không chứng minh provider hiện hoạt động.

## Minh chứng SDLC và tái lập

| Giai đoạn | Minh chứng |
|---|---|
| KT1 | Yêu cầu gốc → [intent](../intent.md), [plan](../plan.md), ma trận F01–F13; mô hình một bãi/khu/ô/xe/lượt/vé/giá hiện có. Số chỗ nhận xe được phải loại cả giữ chỗ, không chỉ `is_occupied=false`. |
| KT2 | Lỗi chỗ giữ vẫn được gợi ý được tái hiện trước sửa, sau đó dùng `has_slot_commitment`; 7 test tại `tests/test_legacy_availability_commitments.py`. Diff code/test và bộ HTTP là bằng chứng thực của đợt này. |
| KT3 | Prompt thật ở `backend/services/ai_service.py::generate_scoped_analysis` và `_build_grounded_qa_prompt`: JSON theo quyền, không tự tạo số liệu, phân biệt cộng dồn tuần và tốc độ theo giờ, nêu thiếu dữ liệu/giả định nhân sự. Unit test và lỗi provider thật được ghi tách biệt. |
| Cuối kỳ | Tài liệu này + [hướng dẫn chạy một bãi](SINGLE_LOT_DEMO.md) + [SDLC chi tiết](upgrade-2026-09-15/SDLC_EVIDENCE.md). Chưa xuất Word/slide mới và chưa chốt buổi bảo vệ toàn bộ. |

Prompt tái lập cho KT2 (viết để tái lập, **không phải bản chép prompt lịch sử**): “Tạo ca một ô đang trống vật lý nhưng bị giữ bởi đặt chỗ hoặc đơn chưa thanh toán. Kiểm số chỗ và danh sách gợi ý phải trùng điều kiện nhận xe; đọc chỗ trống không sửa dữ liệu đặt chỗ. Sửa bằng điều kiện dùng chung và giữ test hết hạn/ngừng hoạt động.”

Lệnh kiểm AI tự động:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ai.py tests/test_ai_integrity.py tests/test_ai_provider_fail_closed.py tests/test_core_site_analytics.py tests/test_core_analytics_permissions.py tests/test_report_period_consistency.py tests/test_cancelled_analytics.py -q --tb=short
```

Hai bộ backend đã chạy (294 ca baseline, rồi 167 ca sau sửa):

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_auth.py tests/test_auth_security_regressions.py tests/test_core_crud_permissions.py tests/test_zone_slot_integrity.py tests/test_slots.py tests/test_fee.py tests/test_monthly_pass_api.py tests/test_customer_integrity.py tests/test_vehicle_type_integrity.py tests/test_vehicle_type_activation.py tests/test_price_config_api.py tests/test_checkout_quote_contract.py tests/test_session_id_search.py --tb=short
.venv\Scripts\python.exe -m pytest -q tests/test_legacy_availability_commitments.py tests/test_check_in.py tests/test_check_in_server_time.py tests/test_check_out.py tests/test_check_in_concurrency.py tests/test_check_out_concurrency.py tests/test_slots.py tests/test_dashboard.py tests/test_cancelled_analytics.py tests/test_timezone_hardening.py tests/test_monthly_coverage_snapshot.py tests/test_core_analytics_permissions.py tests/test_core_site_analytics.py --tb=short
```

Kết quả lần lượt 69,19 và 116,85 giây, exit 0. Kết quả ghi ở phiên công cụ, không tạo file log riêng cho hai nhóm này. Frontend chạy `npm test`, `npm run lint`, `npm run build` trong `frontend/`; hai harness UI mới là `frontend/tests/browser/core_first_uat.py` (fixture) và `core_live_uat.py --credentials backend/artifacts/core-20260923/acceptance.db.demo-credentials.json` (server thật cổng 8792).

Lệnh HTTP đã thực hiện (server dùng DB mẫu riêng, AI tắt):

```powershell
.venv\Scripts\python.exe scripts/verify_single_lot_core.py --base-url http://127.0.0.1:8792 --credentials backend/artifacts/core-20260923/acceptance.db.demo-credentials.json --output backend/artifacts/core-20260923/core-http.json
```

Khi Gemini hoạt động, chạy lại bộ 5 ca trên server DB tổng hợp có `--enable-ai`:

```powershell
.venv\Scripts\python.exe scripts/verify_single_lot_ai.py --base-url http://127.0.0.1:8791 --credentials backend/artifacts/core-20260923/live-acceptance.db.demo-credentials.json --output backend/artifacts/core-20260923/ai-live-next.json
```

Sau khi runner đạt transport/history, vẫn phải đối chiếu cả 5 nội dung với `aggregate_input`: kỳ ngày/tuần, số lượt, doanh thu đúng quyền, chỗ hiện tại có thời điểm, không bịa định biên và kỳ rỗng không bịa cao điểm. HTTP 201 chưa đủ để đánh dấu AI đạt.

## Thứ tự trình diễn và phần còn mở

1. Manager cấu hình khu/chỗ/loại/giá; Staff đăng nhập và nhận xe không cần đặt trước.
2. Xem chỗ theo khu giảm, tìm biển/ngày/mã lượt, xem giờ gửi/phí, xác nhận thu và trả xe; kiểm chỗ tăng lại.
3. Minh họa vé tháng/khách quen; báo cáo ngày/tuần/doanh thu/cao điểm và giới hạn quyền Staff.
4. Chạy ba nhóm AI từ dữ liệu nguồn khi provider sẵn sàng, kiểm kỳ rỗng và lỗi. Có thể đọc output lịch sử nhưng phải ghi rõ thời điểm và nguồn, không trình bày là sinh mới.
5. Trình bày prompt/code/test KT1–KT3. Sau khi đủ lõi mới giới thiệu camera, QR và đặt chỗ.

Phần còn mở: kiểm lại Gemini + review nội dung, xuất Word/slide mới nếu cần nộp định dạng đó. Đợt này không migration, không chạy lại full suite/PostgreSQL/website đã deploy, không kiểm ngân hàng hoặc camera vật lý. Không lấy các phần mở rộng làm điều kiện thay thế yêu cầu gốc.
