# ParkingAI — System map và khảo sát kỹ thuật vòng 3

Ngày khảo sát: **08/09/2026**. Baseline cố định: `caaef39042ea15fc93f01938af46a7ac64890258`.

Tài liệu mô tả mã tại baseline trước các thay đổi vòng 3. Việc một khả năng có trong mã hoặc có test không đồng nghĩa đã được nghiệm thu trên website. Kết quả sửa và kiểm thử candidate phải được ghi riêng khi có bằng chứng mới. Phần nghiên cứu, benchmark và kế hoạch nằm trong [REVIEW_ROUND3_RESEARCH.md](REVIEW_ROUND3_RESEARCH.md).

Quy ước: **CONFIRMED** là điều xác định được từ mã/caller/schema hoặc biên bản đã có; **HYPOTHESIS** cần tái hiện hoặc đo thêm; **NOT VERIFIED** chưa có bằng chứng phù hợp. `NO MATERIAL GAP FOUND` chỉ có nghĩa không thấy gap đáng kể trong phạm vi được ghi, không phải cam kết không còn lỗi. Khảo sát này không phát hiện thêm P0 đã được tái hiện.

## 1. Domain map và request flow

### Entity thật trong repository

| Nhóm | Class / bảng thật | Quan hệ và ranh giới quan trọng |
| --- | --- | --- |
| Danh tính | `User/users`, `Role/roles`, `Customer/customers` | Tài khoản đăng nhập khác hồ sơ khách; không suy ra quyền khách chỉ từ số điện thoại. |
| Bãi và quyền | `ParkingSite/parking_sites`, `SiteMembership/site_memberships` | Membership duy nhất theo `(site_id, user_id)`, role tại bãi là `staff` hoặc `manager`. Không có tenant/operator thứ hai. |
| Tài nguyên | `Zone/zones`, `ParkingSlot/parking_slots`, `VehicleType/vehicle_types`, `Vehicle/vehicles` | `Zone.site_id` nullable cho tương thích; slot có zone và loại xe; vehicle có loại xe và customer. |
| Gửi xe | `ParkingSession/parking_sessions` | `parking_slot_id`, `vehicle_id`, `staff_in_id`, `staff_out_id`, `check_in_time`, `check_out_time`, `parking_fee`; status `active/completed`. Site suy từ slot → zone. |
| Phí và vé | `PriceConfig/price_configs`, `ParkingCard/parking_cards`, `MonthlyPass/monthly_passes` | Quyền gửi trả trước và khoảng hiệu lực khác cam kết giữ một chỗ cụ thể. Phiên giữ `monthly_pass_id`, `monthly_coverage_end`. |
| Thu/hoàn | `Payment/payments` | `source_type=parking_session/monthly_pass`, `source_id`, `kind=receipt/refund`, `method=cash/transfer/legacy_unknown/demo`; `original_payment_id` cho hoàn. Đây là sổ thu/hoàn, không phải hệ kế toán kép đầy đủ. |
| Ca thu | `CashShift/cash_shifts` | `staff_id`, tiền mở ca, tiền đếm, tiền dự kiến, chênh lệch; baseline chưa có `site_id`. |
| Quyền portal | `PortalAccountLink/portal_account_links`, `PortalVehicleOwnership/portal_vehicle_ownerships`, `PortalSessionGrant/portal_session_grants` | Link tài khoản–khách; duyệt quyền xe có `approved_at`; grant lịch sử gắn `parking_session_id` và `customer_id` ngay khi vào. |
| Yêu cầu duyệt | `PortalLinkRequest/portal_link_requests`, `PortalVehicleRequest/portal_vehicle_requests` | `pending/approved/rejected`; reviewer độc lập với người yêu cầu theo guard service. |
| Gói và đơn | `SubscriptionPlan/subscription_plans`, `PortalOrder/portal_orders` | Plan có site/loại xe/giá/số ngày; order đóng băng `amount`, `start_date`, `end_date`, site/xe/gói; request duy nhất theo `(user_id, idempotency_key)`. |
| Sự kiện và hoàn portal | `PortalPaymentEvent/portal_payment_events`, `PortalRefundRequest/portal_refund_requests` | Event duy nhất theo `(provider, reference)`; refund request liên kết order và payment hoàn; không có I/O ngân hàng. |
| Đặt chỗ | `ParkingReservation/parking_reservations` | Site, slot, xe, khách, `[start_at,end_at)`, `arrival_deadline`, request ID, session ID duy nhất. Enum thật: `confirmed/arrived/cancelled/expired`; no-show được biểu diễn bằng quá hạn, không có enum `no_show`. |
| Bảo đảm chỗ | `GuaranteedAllocation/guaranteed_allocations` | Slot cụ thể trong một khoảng; `active/cancelled`; không đồng nghĩa với vé tháng đã trả tiền. |
| Danh sách chờ | `SiteWaitlist/site_waitlist` | `waiting/offered/cancelled`, `reservation_id` duy nhất khi đã cấp đề nghị. |
| Nhóm xe | `Organization/organizations`, `OrganizationMembership/organization_memberships`, `FleetVehicle/fleet_vehicles` | Organization thuộc một site; xe tham gia có `created_at`; báo cáo lọc cả site và thời điểm tham gia. |
| Camera và quan sát | `Camera/vision_cameras`, `VisionObservation/vision_observations` | Camera có site/zone/hướng/retention/token hash. Observation lưu ảnh chuẩn hóa dạng **BLOB trong DB**, hash, kích thước, timestamps, OCR, detections và kết quả review. |
| Thông báo | `PortalNotification/portal_notifications` | Theo customer, `event_key` unique, `read_at`; kênh hiện tại là trong ứng dụng. |
| Báo cáo AI và audit | `AiReport/ai_reports`, `AuditLog/audit_logs` | AI lưu báo cáo; audit lưu metadata HTTP. Forecast là kết quả tính, không có entity `Forecast` riêng. Checkout quote là token ký, không có bảng `CheckoutQuote`. |

Nguồn schema: [models](../backend/models), [site models](../backend/expansion/site_models.py), [portal models](../backend/expansion/portal_models.py), [vision models](../backend/expansion/vision_models.py). Không thay tên `ParkingSlot` thành entity mới `ParkingSpace`, hoặc tự tạo thêm entity `Ledger`, khi mô tả schema hiện tại.

### Caller → API → service → dữ liệu

| Luồng | Caller frontend và API thật | Luồng xử lý |
| --- | --- | --- |
| Xe vào | `SitesWorkspace` → `POST /api/v2/sites/{site_id}/check-in` | `require_site_access` → `ParkingService.check_in` → kiểm tra/khóa xe và slot → claim atomic → tạo session → `capture_session_ownership` và `record_admission` → commit. |
| Xem phí | `siteForms.js`/checkout UI → `GET /api/v2/sites/{site_id}/sessions/{session_id}/checkout-quote` | `scoped_session` kiểm tra đúng bãi → `CheckoutService.quote` → dùng `ParkingService.calculate_fee` → ký state/fee/rate/actor/session/expiry; không đóng phiên. |
| Xe ra | `PUT /api/v2/sites/{site_id}/sessions/{session_id}/check-out` | Schema bắt xác nhận boolean → kiểm chữ ký, actor, state → khóa cashier/claim session → kiểm lại hạn và giá → completed + giải phóng slot + receipt nếu có phí → commit chung; replay chính xác trả kết quả đã chấp nhận. |
| Vé tháng portal | `CustomerPortal` → `/api/v2/me/orders`, `/{id}/simulate` | Quyền xe → giá/kỳ hạn từ plan phía server → order snapshot → event unique → `_fulfill` → vé và receipt; DEMO không vào doanh thu thật. Nhánh thu quầy dùng `/portal/admin/orders/{id}/collect`. |
| Lịch sử khách | `CustomerPortal` → `/api/v2/me/sessions`, `/me/receipts`, `/me/receipts/{id}/pdf` | Lọc customer được liên kết và grant/source được phép; không backfill quyền lịch sử khi duyệt một xe cũ. |
| Booking/waitlist | `ReservationsPage` và `SitesWorkspace` → `/me/reservations`, `/sites/{site_id}/reservations`, `/sites/{site_id}/waitlist/{id}/offer` | `reserve` kiểm quyền/khung, khóa xe → slot → kiểm overlap → tạo commitment. `arrive` dùng đúng slot qua parking service. `offer_waitlist` tạo reservation và thông báo có event key. |
| Fleet | `FleetSection` → `GET /api/v2/organizations/{organization_id}/fleet` | `require_organization` → chung bộ join `_fleet_sessions` cho list và totals → lọc site + `check_in_time >= FleetVehicle.created_at`; tổng phí lượt đã hoàn tất không được gọi là doanh thu thuần. |
| Camera | `VisionPage`/`imageUpload.js` → `POST /api/v2/vision/observations`; edge → `/vision/edge-events` | Chặn upload dồn → xác thực camera/site → kết thúc DB transaction trước decode/inference → chuẩn hóa ảnh → YOLO crop → OCR → lưu observation. `/review` chỉ ghi kết quả nhân viên; UI điều hướng sang `/sites` để làm nghiệp vụ riêng. |
| Insights | `InsightsPage` → `/api/v2/insights/forecast`, `/anomalies`, `/staff-plan` | `_zones` kiểm quyền site → lấy counts lịch sử → `build_forecast`/`build_staff_plan`; không gọi LLM để tạo số. |
| Ca thu cũ | `financeService.js` → `/api/v1/cash-shifts`, `/api/v1/payments` | `require_legacy_workspace` bao router → `CashShiftService`/`PaymentService`; hệ có từ hai bãi chặn staff/manager ở boundary v1. Đây là gap ca thu theo bãi đã xác nhận. |

Nguồn luồng: [site router](../backend/expansion/site_router.py), [portal router](../backend/expansion/portal_router.py), [vision router](../backend/expansion/vision_router.py), [frontend Expansion](../frontend/src/pages/Expansion), [checkout service](../backend/services/checkout_service.py).

## 2. Kiến trúc hiện tại và compatibility

**CONFIRMED:** backend là modular monolith FastAPI với SQLAlchemy đồng bộ; các module v2 gọi lại service nghiệp vụ hiện có. `main.py` quản lý lifespan/worker, các route và middleware; `database.py`, model DDL và Alembic duy trì ràng buộc theo dialect. Không cần tách microservices để giải quyết các gap đã thấy.

| Thành phần | Hiện trạng baseline | Giới hạn phải giữ |
| --- | --- | --- |
| `/api/v1/*`, `/parking`, `/dashboard`, `/reports`, `/ai` | Được mount với `require_legacy_workspace` | Khi có ít nhất hai site, kể cả site đóng, các module global này chỉ admin. Không tháo guard để mở chức năng cho staff. |
| `/api/v2/sites/*`, `/me/*`, `/portal/admin/*`, `/vision/*`, `/insights/*` | Scoped bằng service/helper và ownership | Có role toàn cục chưa đủ; phải xét site membership hoặc quyền khách trên đối tượng. |
| `/api/v2/system/capabilities` | Trả `scope=single_operator`, cờ legacy, QR demo và camera confirmation | Frontend dùng capability để điều hướng; capability không thay kiểm quyền backend. |
| Demo | `start_demo.ps1` → `demo_server.py`; một port API + SPA, SQLite có `.demo.json` | Không dùng seeder SQLite này để ghi trực tiếp lên DB production. |
| Production | Cloudflare Pages → Fly FastAPI → Supabase PostgreSQL | Backend Docker ghim digest, chạy user không phải root; release chạy Alembic rồi production gate. |
| Maintenance | Lifespan có worker portal; Fly đặt interval 30 giây | Worker dùng cùng service/locking, xử lý batch; mất worker không được làm mất event đã nhận. |
| AI/OCR | Gemini mặc định tắt; OCR import/model tùy chọn, CPU | Gemini disabled/unavailable fail closed. Trạng thái availability khác bằng chứng accuracy. |

Nguồn: [main.py](../backend/main.py), [system boundary](../backend/expansion/system_router.py), [Dockerfile](../backend/Dockerfile), [Fly](../backend/fly.toml), [demo](../scripts/demo_server.py). Các số version dependency trong prompt là bối cảnh, không thay lock/manifests của candidate.

Thay đổi vòng 3 phải bổ sung API site-scoped khi cần, giữ caller v1 hợp lệ. Thêm nullable `site_id` cho ca/chứng từ là thay đổi additive đã được duyệt; dữ liệu lịch sử không có nguồn xác định phải để null. Không suy bãi của khoản thu từ membership hiện tại của nhân viên.

## 3. Invariants và nơi thực thi

| Invariant | Bảo vệ trong baseline | Nghiệm thu cần giữ |
| --- | --- | --- |
| Một xe/chỗ có tối đa một phiên active | Hai partial unique index `uq_parking_session_one_active_per_vehicle` và `uq_parking_session_one_active_per_slot`, claim và khóa trong service | Hai kết nối tranh cùng slot/xe chỉ một kết quả hợp lệ; rollback không để occupied mồ côi. |
| Xe phải vào slot cụ thể hợp lệ | `SiteCheckIn.parking_slot_id`, site/zone/type guards và admission checks | Không cho chọn slot của bãi khác hoặc khu ngừng hoạt động; future commitment không bị bỏ qua. |
| Checkout ký, hạn 120 giây | `CheckoutService`, `QUOTE_TTL_SECONDS`, state/rate/fee/actor snapshot; `CheckoutConfirmation` | Quote hết hạn/đổi bảng giá/đổi state phải xem lại; `payment_confirmed` phải true; fee=0 không tạo khoản thu giả. |
| Retry không nhân đôi tiền/phiên | Hash quote được chấp nhận trên session; unique receipt theo source; payment idempotency | Cùng token/actor/method nhận kết quả cũ; xác nhận khác bị từ chối; receipt lỗi phải rollback checkout. |
| Tiền do server tính, số nguyên VND | `VND_DATABASE_TYPE`, exact integer bounds, fee service, order snapshot | Client không áp giá/kỳ hạn; hoàn không vượt khoản gốc; ledger không sửa/xóa. |
| DEMO khác tiền thật | `Payment.method=demo`, trigger không gắn ca, bộ lọc doanh thu, refund chỉ cùng chế độ | Có thể lưu chứng từ demo để minh họa; mọi tổng thật/ca thật phải loại chúng, PDF ghi rõ mô phỏng. |
| Quyền lịch sử đúng thời điểm | `PortalVehicleOwnership.approved_at` → `PortalSessionGrant` ở admission | Duyệt xe sau không mở lịch sử cũ; đổi chủ không trao grant cũ. |
| Khoảng đặt `[start,end)` | Overlap `start_at < other.end_at AND end_at > other.start_at`, check constraints và trigger | Hai booking tiếp giáp được phép nếu các điều kiện khác hợp lệ; arrival một lần, đúng slot. |
| Hạn đến 15 phút và code một lần | Deadline giới hạn trong khoảng; reservation có session unique; `arrive`/`record_admission` | Quá hạn thành expired; nhân viên không dùng lại code để tạo session thứ hai. |
| Waitlist không cấp hai chỗ | Khóa hàng chờ, `reservation_id` unique, reserve service và notification event key | Offer song song không tạo hai booking/thông báo; không cấp quá sức chứa. |
| OCR không tự vận hành | Review state `pending/accepted/rejected`, confirmed plate do nhân viên nhập; UI chuyển trang riêng | Upload/review không đổi session, tiền, slot hoặc barrier. |
| Forecast không bịa dữ liệu | Cửa sổ 42–84 ngày, chỉ dùng quá khứ, coverage và completeness unknown | Không đủ dữ liệu trả `insufficient_data`; số điền 0 không được coi là quan sát chắc chắn. |

Nguồn: [ParkingSession](../backend/models/parking_session.py), [Payment](../backend/models/payment.py), [reservations](../backend/expansion/reservations.py), [portal service](../backend/expansion/portal_service.py), [forecast](../backend/expansion/forecast.py).

## 4. Security và privacy review

| Mặt kiểm tra | Quan sát có bằng chứng | Việc còn cần xác minh |
| --- | --- | --- |
| JWT/RBAC | `get_current_user` giải mã bằng algorithm allowlist, tải user hiện tại từ DB, chặn inactive; role/helper được kiểm mỗi request | Chạy lại stale-role và thu hồi membership bằng hai phiên đăng nhập. Không kết luận logout thu hồi mọi JWT chỉ từ guard này. |
| Site BOLA | `require_site_access`, `scoped_session`, `_camera`, `_observation` và `require_organization` kiểm đối tượng/site; customer có ownership/grant riêng | Matrix admin/manager/staff/customer × own/foreign/missing object, gồm receipt, fleet, booking, ảnh. |
| Legacy boundary | `require_legacy_workspace` đếm cả site đã đóng; frontend `LegacyRoute` chuyển về sites | Mọi route mới phải giữ cùng boundary; không dùng v1 làm đường vòng cho báo cáo/ca. |
| Mass assignment/SQL | `StrictBody.extra=forbid`; query ORM bind tham số; serialized fields allowlist ở v2 | Kiểm DTO và raw SQL mới; không suy rằng toàn repo miễn SQL injection từ vài service. |
| Upload | MIME JPEG/PNG đối chiếu format thật, tối đa 2 MB/12 triệu pixels, xác minh ảnh, loại EXIF/GPS và chuẩn hóa JPEG; MPO điện thoại chỉ lấy ảnh chính | Fuzz format giả, bomb, ảnh hỏng, nhiều frame, timeout và upload song song theo hai dialect. |
| Ảnh và filesystem | Observation dùng BLOB, lấy ảnh theo ID đã kiểm quyền; không có đường dẫn file người dùng cho route ảnh | Không áp giả định “orphan file” cho BLOB. Cần kiểm record hết hạn/xóa khi đang review; model path là cấu hình server, edge fetch là ranh giới riêng. |
| Giới hạn ảnh | Retention mặc định 24h, 30 ảnh/phút/camera, cap 500/site; có eviction terminal và purge | Không dùng rate limit như bằng chứng chịu được mọi tải; kiểm lock/cleanup race trên PostgreSQL thật. |
| Secret/error/log | 422 redaction và security headers; audit không đọc body; proxy header chỉ tin khi cấu hình | Request ID/log mới không thu password, JWT, ảnh, secret hoặc query chứa dữ liệu cá nhân. |
| Gemini | Prompt phân định câu hỏi không tin cậy; provider không được cấp tool truy vấn/ghi DB; API global đang sau legacy guard | Delimiter không loại hết prompt injection. Giữ OFF và 503; nếu thêm QA theo site phải lọc dữ liệu trước prompt, kiểm không rò bãi khác. |
| CORS/CSRF/redirect/SSRF | CORS allowlist; ứng dụng gọi Bearer API; camera upload là bytes, không phải URL do khách yêu cầu fetch | Nếu đổi sang cookie auth thì đánh giá CSRF lại. Kiểm redirect/query navigation và ingress edge riêng trước mở remote camera URL. |

**CONFIRMED gap audit:** `_classify_action` chỉ nhận tên nghiệp vụ v1; route v2 nhận CREATE/UPDATE chung. `_extract_resource` không có nhánh v2 nên nhiều bản ghi thành resource `api`, mất ID hữu ích. `AuditLog` baseline không có site/request correlation; middleware không ghi GET denial. Đây là gap truy vết P2, chưa là bằng chứng data leak hay P0.

Nguồn: [auth service](../backend/services/auth_service.py), [audit middleware](../backend/middleware/audit.py), [audit model](../backend/models/audit_log.py), [vision service](../backend/expansion/vision_service.py), [AI service](../backend/services/ai_service.py), [acceptance security tests](../tests/test_acceptance_security.py).

## 5. Concurrency và transaction review

| Đường ghi | Hiện trạng baseline | Ca kiểm thử rủi ro tiếp theo |
| --- | --- | --- |
| Entry/reserve/arrival | Thứ tự khóa xe → slot; guard DB là lớp bảo vệ bổ sung | Hai xe cùng slot; cùng xe hai slot; arrive cạnh tranh walk-in; không dùng check-then-write thay claim. |
| Giới hạn booking/khách | Có horizon 30 ngày và cap 5 booking hiệu lực | **HYPOTHESIS:** nhiều xe khác nhau của cùng khách có thể tranh kiểm đếm cap nếu chỉ khóa xe; phải tái hiện và đánh giá tác động trước khi gắn bug hoặc priority. |
| Checkout/payment/shift | Khóa cashier chung; claim session; ledger unique; chốt ca kiểm balance và khóa staff | Checkout cùng staff ở hai session; thu tiền đồng thời close ca; sau thêm site không được gắn tiền bãi B vào ca A. |
| Order/event/refund | Order/event unique, `_lock_order_context`, fulfillment chung, refund bù trừ và worker retry | Callback/worker cùng event; success tới muộn; approve refund lặp; lỗi giữa cấp vé và receipt phải rollback. |
| Waitlist | `offer_waitlist` dùng reserve và notification dedup | Hai offer cho một hàng; hai hàng tranh slot cuối; cancel/offer đồng thời. |
| Image/review/retention | Admission gate trước inference; inference không giữ DB connection; trạng thái review có lock | Review/delete/purge đồng thời; hai upload tại cap 500; ảnh đã review không bị ghi đè bởi request cũ. |
| Audit | SQL ghi audit chạy threadpool sau xử lý route; portal write wrapper commit trước response | Kiểm lại replay SQLite không giữ writer lock khiến audit tự chờ; audit lỗi không treo readiness. |

SQLite dùng cơ chế writer lock/atomic update khác PostgreSQL `FOR UPDATE` và transaction isolation. Hai connection SQLite không thay test PostgreSQL 16. Test tham chiếu: [check-in concurrency](../tests/test_check_in_concurrency.py), [checkout concurrency](../tests/test_check_out_concurrency.py), [portal concurrency](../tests/test_portal_concurrency.py), [PostgreSQL integration](../tests/test_postgres_integration.py), [vision API](../tests/test_expansion_vision_api.py). Trong lượt khảo sát tài liệu này chỉ đọc các test, chưa chạy lại.

## 6. Database, migration và hiệu năng

**CONFIRMED:** có FK, unique/check constraints, partial indexes và trigger tương ứng SQLite/PostgreSQL cho session, payment, shift, paid period và commitment. Alembic baseline đã có revision `20260908_01`; release kiểm readiness/trigger inventory. Không thay guard DB bằng validation Pydantic.

| Vùng | Quan sát | Đánh giá / hành động |
| --- | --- | --- |
| Ledger/ca | Payment append-only, source là polymorphic nên dùng trigger kiểm nguồn; ca đóng bất biến | `NO MATERIAL GAP FOUND` trong thiết kế bất biến đã đọc. Chưa có site của ca/chứng từ: gap riêng P1, cần migration additive. |
| Dữ liệu legacy | Zone/site nullable; session cũ có thể không gắn bãi; `_revenue_events` giữ bridge và tránh double count khi có receipt | Không xóa bridge hoặc backfill site theo phỏng đoán. Tổng site phải báo số legacy chưa phân loại. |
| Commitment | Index slot/khoảng, trạng thái và trigger ngừng khu/chỗ còn cam kết | Giữ `[start,end)`; bổ sung test ORM/direct SQL và contention khi sửa scoped zone/slot. |
| Timestamp | Metadata `func.now()` được serialize UTC; giờ nghiệp vụ qua `BUSINESS_TZ/business_now` | Không gắn +07 vào UTC metadata; deadline/quote/test cần kiểm quanh nửa đêm và exact boundary. |
| Query/pagination | Sessions, booking và fleet session có limit/offset; fleet totals dùng cùng tập quyền với list | Danh sách xe fleet và một số catalog vẫn trả `.all()`. Đây là phạm vi cần đo, chưa có bằng chứng chậm. |
| Availability | `availability` duyệt slot rồi gọi kiểm admission cho từng slot | **HYPOTHESIS hiệu năng:** số query tăng theo slot. Đo SQL count/P95 trước khi thêm index/cache hoặc viết lại. |
| Forecast | Query lấy lịch sử có giới hạn thời gian; Python tổng hợp theo giờ | Benchmark dữ liệu tăng trước khi tối ưu; giữ cutoff và coverage, không đẩy aggregate sang LLM. |
| Blob ảnh | Tối đa 500 observation/site không đồng nghĩa có giới hạn tổng dung lượng toàn DB | Theo dõi storage/latency và cleanup; không tự thêm object store khi chưa có phép đo. |
| Migration | SQL/DDL nằm ở model, rollout và Alembic cần đồng bộ | Test upgrade từ DB có lịch sử, chạy lại, FK/index/trigger parity; restore vào DB riêng, không downgrade phá chứng từ. |

Nguồn: [database.py](../backend/database.py), [PostgreSQL readiness](../backend/postgres_readiness.py), [Alembic versions](../backend/alembic/versions), [site service](../backend/expansion/site_service.py), [payment service](../backend/services/payment_service.py).

## 7. UX theo persona và frontend callers

| Persona | Có tại baseline | Gap / kiểm chứng tiếp |
| --- | --- | --- |
| Staff | Sites workspace: chọn bãi/xe/slot, lịch sử phiên, checkout quote + xác nhận; Vision dẫn sang nghiệp vụ sau review | Ca thu hiện đi v1 nên không dùng được trong multi-site. Kiểm keyboard, số bước, double-click, quote vừa hết hạn. |
| Manager | Bãi được cấp quyền, booking/allocation/waitlist, fleet, duyệt đơn/gói/hoàn, insights | Cần doanh thu/chứng từ/ca và sửa zone/slot theo site; không mở lại trang global. |
| Admin | CRUD toàn hệ thống, users/role, site/member, audit và báo cáo | Audit v2 thiếu ý nghĩa nghiệp vụ; cần so sánh bãi và phân biệt dữ liệu legacy chưa biết site. |
| Customer | Profile, xe đã duyệt, vé, order, booking/waitlist, grant lịch sử, PDF và notifications | Kiểm lỗi từng tab không làm biến mất tab khác; thông báo hạn đến và QR mock phải rõ; không đưa khái niệm model/ledger nội bộ vào thao tác khách. |

`shared.jsx` có hook tải dữ liệu/thao tác, loading/error/retry; `siteForms.js` dùng API checkout riêng; state/busy được dùng để hạn chế click lặp. `InsightsPage` hiển thị coverage và cảnh báo ước lượng; chart baseline chỉ vẽ upper và arrivals, bảng có lower–upper. Đây là cơ hội UX P2 để thể hiện dải đúng nghĩa, không phải lý do đổi model.

`frontend/public/_headers` đang có `Permissions-Policy: camera=()`; luồng đang dùng input chụp/chọn ảnh trên điện thoại, không chứng minh `getUserMedia` đã hoạt động. Nếu bổ sung preview camera trực tiếp phải quyết định policy/HTTPS và thử thiết bị thật; không coi viewport mobile là kiểm thử camera.

Khảo sát TODO/FIXME/HACK/NotImplementedError trong expansion/services/frontend expansion không thấy placeholder nghiệp vụ rõ ràng; chuỗi `placeholder` tìm được là dữ liệu test model giả. Không có bằng chứng để xóa code theo nhãn “dead code”. Accessibility toàn hệ thống, screen reader, focus và DataGrid ở quy mô lớn là **NOT VERIFIED**; cần audit thực tế thay vì suy từ việc dùng MUI.

Liên quan: [AppRoutes](../frontend/src/routes/AppRoutes.jsx), [finance caller](../frontend/src/services/financeService.js), [Expansion UI](../frontend/src/pages/Expansion), [frontend headers](../frontend/public/_headers). Bảy phần tiếp theo của review nằm tại [nghiên cứu, benchmark và kế hoạch](REVIEW_ROUND3_RESEARCH.md).
