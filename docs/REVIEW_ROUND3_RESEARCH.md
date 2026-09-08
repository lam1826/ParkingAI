# ParkingAI — Nghiên cứu, benchmark và hướng cải tiến vòng 3

Ngày truy cập nguồn và khảo sát: **08/09/2026**. Baseline: `caaef39042ea15fc93f01938af46a7ac64890258`. Đây là phần 8–14 của review; phần 1–7 nằm trong [system map](REVIEW_ROUND3_SYSTEM_MAP.md). Trạng thái trong tài liệu là **trước sửa vòng 3**, không phải chứng nhận candidate đã qua kiểm thử.

Mục tiêu đã chốt: một đơn vị vận hành nhiều bãi; admin/manager/staff/customer; website hiện tại dùng trình diễn đồ án; QR mock, Gemini tắt; YOLO/OCR thử chạy trên Fly hiện có với phép đo tài nguyên trước khi bật. Không tăng gói tự động, không ngân hàng thật, không SaaS multi-tenant và không tự động mở barrier.

## 8. Các hệ thống tham khảo và bằng chứng primary sources

Nghiên cứu dùng tài liệu/mã do chủ hệ thống phát hành. Tính năng của nhà cung cấp là bằng chứng về pattern, không phải benchmark độc lập về hiệu suất. `WHY`, `RELEVANCE`, `ACTION`, `REASON` là đánh giá của review đối với ParkingAI. Không sao chép code proprietary, giao diện hay branding.

| SYSTEM / CATEGORY | RELEVANT FEATURE / HOW IT WORKS | WHY IT IS GOOD / PARKINGAI RELEVANCE | ACTION / REASON |
| --- | --- | --- | --- |
| **SKIDATA — parking operations** | Điều hành, giám sát, sự cố và báo cáo tập trung cho nhiều bãi, cấu hình theo địa điểm. [Nguồn](https://www.skidata.com/en-ie/segments/parking-operator) | Một manager xem dữ liệu đúng bãi; admin so sánh danh mục bãi. Tập trung vào việc cần xử lý hơn là thêm nhiều dashboard rời. | **ADAPT:** học portfolio/site view và incident workflow trong monolith; không mua hoặc tái tạo nền tảng enterprise. |
| **Parkalot — parking reservation** | Hạn xác nhận chỗ giữ sẵn; quá hạn giải phóng; waitlist theo khu/loại tài nguyên; booking window có cấu hình. [FAQ](https://parkalot.io/faq/), [waitlist guide](https://parkalot.io/wp-content/uploads/2025/08/The-Waitlist-Explained-Parkalot-Admin-User-Guide-.pdf) | Phân biệt trống hiện tại với khả dụng trong khoảng đặt; người chờ biết khi được cấp chỗ. | **ADAPT:** deadline, thông báo, promotion có kiểm sức chứa và thứ tự rõ. Không khẳng định thuật toán nội bộ của Parkalot là FIFO. |
| **Skedda — reservation/no-show** | Cửa sổ check-in; quá hạn có thể log-only hoặc giải phóng, có activity log; khuyến nghị thử log-only khi đưa chính sách mới vào dùng. [Check-in](https://support.skedda.com/en/articles/5242690-check-in) | Hạn đến rõ, thao tác nhân viên có bằng chứng; giảm hủy nhầm khi vừa đổi chính sách. | **ADAPT:** lưu expired/no-show history; giữ `[start,end)` và deadline của ParkingAI. Không xóa bản ghi hoặc bê nguyên chính sách ngoại lệ booking trả tiền. |
| **Plate Recognizer — ANPR** | Output có crop/box, candidates, score/dscore, camera, ảnh và capture/arrival timestamps. [Output schema](https://guides.platerecognizer.com/docs/stream/results/) | Có bằng chứng để nhân viên so sánh và để dev phân biệt lỗi phát hiện với lỗi đọc ký tự. | **ADAPT:** tách scores/candidates, model provenance và ảnh crop; không tích hợp API trả phí. Quyết định cuối là người dùng của ParkingAI. |
| **RapidOCR — OSS OCR engine** | Det/cls/rec tách bước; có chế độ recognition-only, score threshold, chuẩn hóa ảnh và lazy model loading có khóa. [Code](https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/rapidocr/main.py), [docs](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/) | Phù hợp crop do YOLO tạo; thay đổi preprocess có thể được đo riêng, không phải thay toàn pipeline. | **ADAPT:** giữ adapter và model pin; benchmark ảnh Việt Nam trước nâng version. Code/library license không tự chứng minh license của mọi weight. |
| **Frigate — local camera/ANPR** | Tách detection/recognition threshold, min area, format filter, debug crops, kết quả trong Review/History; enhancement quá mức có thể giảm chất lượng. [LPR docs](https://docs.frigate.video/configuration/license_plate_recognition/) | Học quy trình kiểm tra ảnh và kết quả theo camera, tránh tối ưu mù theo confidence. | **ADAPT** bằng chứng/threshold; **FUTURE** video stream liên tục. Không cài nguyên NVR lên backend demo nhỏ. Review của Frigate không được coi là phê duyệt nghiệp vụ xe vào/ra. |
| **Stripe — payment state/retries** | Idempotency key nhận diện retry và so payload; webhook có thể lặp nên phải dedup event/object. [Idempotency](https://docs.stripe.com/api/idempotent_requests), [webhooks](https://docs.stripe.com/webhooks) | Một ý định thanh toán/cấp vé cho một kết quả ngay cả khi mất mạng hoặc bấm lại. | **ADOPT pattern:** unique key, payload check, transaction trong mock. Không tạo Stripe account; không sao chép cứng TTL hay việc cache mọi 500 của Stripe. |
| **TigerBeetle — financial ledger** | Transfer bất biến, sửa bằng bản ghi bù; pending resolve tối đa một lần sang posted/voided/expired. [Transfer](https://docs.tigerbeetle.com/reference/transfer/), [two-phase](https://docs.tigerbeetle.com/coding/two-phase-transfers/) | Tách đơn, thu tiền, hoàn và đối soát; giữ lịch sử thay vì sửa doanh thu quá khứ. | **ADAPT semantics; REJECT hạ tầng hiện tại:** Payment SQL đã có nhiều bảo vệ này. Không thay DB hoặc dựng kế toán kép chỉ để giống reference. |
| **skforecast — OSS forecast/backtest** | Baseline kỳ tương ứng và tổng hợp nhiều kỳ; tích hợp time-series folds và đánh giá ngoài mẫu. [Baseline](https://skforecast.org/latest/user_guides/forecasting-baseline.html), [backtesting](https://skforecast.org/latest/user_guides/backtesting.html) | Có tiêu chuẩn đo xem model có cải thiện so với cách đơn giản; phù hợp báo cáo đồ án. | **ADAPT:** so naive, seasonal naive, same-weekday-hour mean; ghi MAE, thời gian đo và coverage khoảng ước lượng. Không bắt buộc thêm dependency skforecast vào runtime. |

### Hai OSS đã kiểm tra code, tests, docs và activity

| Dự án | Bằng chứng đã đọc | Kết luận có giới hạn |
| --- | --- | --- |
| RapidOCR | [Pipeline](https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/rapidocr/main.py); [test_det_cls_rec.py](https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/tests/test_det_cls_rec.py) kiểm det/cls/rec riêng và kết hợp với assert text/output; [docs](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/); [commits](https://github.com/RapidAI/RapidOCR/commits/main/) có lazy-load locking 24/08/2026 và model routing 08/09/2026; [releases](https://github.com/RapidAI/RapidOCR/releases) có v3.9.2. | Có hoạt động và test thực chất, không dựa stars. Chỉ đọc, không chạy suite của dự án. Test văn bản không chứng minh accuracy biển số Việt Nam hoặc compatibility với `rapidocr_onnxruntime` đang dùng trong ParkingAI. |
| skforecast | [Implementation](https://raw.githubusercontent.com/skforecast/skforecast/master/skforecast/recursive/_forecaster_equivalent_date.py); [test_predict.py](https://raw.githubusercontent.com/skforecast/skforecast/master/skforecast/recursive/tests/tests_forecaster_equivalent_date/test_predict.py) kiểm offset 7, nhiều kỳ, missing data và không đổi input; [test backtesting](https://raw.githubusercontent.com/skforecast/skforecast/master/skforecast/model_selection/tests/tests_validation/test_backtesting_forecaster.py); [docs](https://skforecast.org/latest/user_guides/forecasting-baseline.html); [release v0.24.0](https://github.com/skforecast/skforecast/releases) ngày 24/08/2026. | Baseline/backtest có implementation và kiểm thử để tham khảo. Chỉ đọc, không chạy suite; không lấy số accuracy của dữ liệu mẫu khác làm kết quả ParkingAI. |

Nguồn bổ sung về phương pháp: FPP3 của Hyndman/Athanasopoulos giải thích [simple methods](https://otexts.com/fpp3/simple-methods.html), [rolling-origin cross-validation](https://otexts.com/fpp3/tscv.html) và [prediction intervals](https://otexts.robjhyndman.com/fpp3/prediction-intervals.html). OWASP yêu cầu kiểm quyền đối tượng ở mọi endpoint nhận ID và kiểm quyền mỗi request: [API1 BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/), [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Các hướng dẫn này bổ sung cho chín hệ thống trên, không được tính là một sản phẩm parking.

## 9. Bài học áp dụng và những gì không nên sao chép

| Quyết định | Nội dung |
| --- | --- |
| **KEEP** | Một operator nhiều site; role + membership + ownership; v1 global được bảo vệ; shared fee/checkout service; partial indexes; Payment append-only; QR mock tách doanh thu; human review; forecast đơn giản; explicit coverage unknown. |
| **FIX** | Audit v2 thiếu classification/object/site; thiếu correlation request. Kiểm chứng cap booking nhiều xe cùng khách trước khi sửa khóa. Đồng bộ analytics/CSP theo cấu hình dùng thật, không nới wildcard để che lỗi. |
| **ADD** | Ca/chứng từ/doanh thu theo bãi; sửa zone/slot qua scoped API; gói OCR trong image có provenance và resource gate; đủ tài khoản/dữ liệu demo online; bảng so baseline và coverage đo được. |
| **SIMPLIFY** | Tái sử dụng fee, locking, scope và response contracts hiện có. Dùng PostgreSQL + worker bounded trong monolith; không dựng framework event/CQRS mới. Phân biệt rõ forecast arrivals với occupancy dự kiến. |
| **REMOVE** | Chưa có dead code được chứng minh an toàn để xóa. Chỉ xóa nhánh không còn caller sau search/tests; giữ bridge ledger legacy, nhập biển thủ công và boundary v1. Nếu không dùng Web Analytics, tắt cấu hình chèn beacon. |
| **FUTURE** | Stream camera liên tục/edge, đo lấp đầy bằng cảm biến, điều phối waitlist tự động có fairness policy, lịch ca nhân sự đầy đủ, multi-site pricing có lịch sử version. Chỉ đưa model phức tạp vào khi cải thiện có đo. |

Không lấy “nhiều tính năng reference hơn” làm lý do thay đổi product scope. Không có khuyến nghị ngân hàng, Stripe/VNPay/MoMo thật, multi-tenant SaaS, Kafka, Kubernetes, Redis, service mesh hoặc microservices trong vòng này.

## 10. Benchmark matrix theo toàn bộ capability được yêu cầu

`—` là giữ/kiểm thử hồi quy, không phải ticket cải tiến. P0 chỉ dùng cho lỗi bảo mật/hỏng dữ liệu/core invariant đã xác nhận; P1 là gap sản phẩm cốt lõi; P2 chất lượng vận hành/UX; P3 mở rộng. Phạm vi ParkingAI trong bảng lấy từ [system map và caller](REVIEW_ROUND3_SYSTEM_MAP.md), không đoán theo tên file.

| Capability | ParkingAI tại caaef39 | Reference systems | Gap | Recommendation | Priority |
| --- | --- | --- | --- | --- | --- |
| Authentication | JWT allowlist, bcrypt, DB user active, login/register limits | OWASP | Chưa có phiên test production | KEEP; regression token/stale account và tạo user demo riêng | — |
| RBAC | RoleChecker, admin/manager/staff/customer | OWASP, SKIDATA | Chưa đo đủ matrix candidate | KEEP; kiểm route lẫn object | — |
| Site-level authorization | Membership/helper, v1 admin-only khi nhiều bãi | SKIDATA, OWASP | API mới có nguy cơ bỏ scope nếu làm riêng lẻ | KEEP shared helper; negative tests bãi A/B | — |
| Audit trail | Mutation metadata; v2 nhiều action chung/resource `api` | Skedda, OWASP | **CONFIRMED:** khó truy vết nghiệp vụ v2 | FIX classification, site/object, denial cần thiết | P2 |
| Parking allocation | Slot cụ thể, zone/type/commitment guards | SKIDATA, Parkalot | Không thấy gap vật lý trong luồng đã đọc | **NO MATERIAL GAP FOUND** trong admission design; giữ guard | — |
| Concurrent space allocation | Atomic claim, vehicle-first locking, partial unique | Parkalot; DB tests nội bộ | Cap theo khách cần test nhiều xe | Tái hiện H1 rồi sửa nếu xác nhận | Chưa gán; đánh giá theo tác động đã tái hiện |
| Pricing | Shared deterministic fee, server time, exact VND | SKIDATA | Bảng giá lượt hiện theo loại xe; chưa pricing từng bãi | KEEP hiện tại; pricing theo bãi/version để sau khi chốt nghiệp vụ | P3 |
| Signed checkout | Quote ký gắn actor/state/rate, TTL 120s, confirm | Stripe (retry pattern) | Không thấy gap hợp đồng quote đã đọc | **NO MATERIAL GAP FOUND** trong contract; giữ tests expiry/change/replay | — |
| Payment idempotency | Unique receipt/request/event và replay guard | Stripe | Không thấy duplicate path mới đã tái hiện | KEEP; cạnh tranh worker/HTTP và lỗi commit | — |
| Ledger | Append-only receipt/refund, guard source/amount/demo | TigerBeetle | Chưa có site trực tiếp cho chứng từ/ca | ADD site additive, giữ legacy null, không viết lại số cũ | P1 |
| Shift closing | CashShift + v1 UI, một ca mở/staff | TigerBeetle, SKIDATA | **CONFIRMED:** staff multi-site bị chặn v1, schema chưa site | ADD v2 site finance và caller scoped | P1 |
| Monthly passes | Server plan snapshot, paid periods, expiry 7/1 ngày | Parkalot, SKIDATA | Không đồng nghĩa guaranteed slot; online chưa có plan lúc kiểm trước | KEEP semantic; seed demo rõ nhãn, UI nói đúng quyền | P1 cấu hình |
| Customer portal | Profile/vehicle approval, grants, order/pass/receipt | Parkalot | Online chưa có tài khoản test trong biên bản trước | UAT khách thật đăng nhập bằng data demo riêng | P1 cấu hình |
| Reservation | `[start,end)`, 15 phút arrival, horizon/cap, đúng slot | Parkalot, Skedda | No-show là expired; không cần entity mới | KEEP; kiểm exact boundary/cancel/arrive race | — |
| Waiting list | Join/offer/cancel, reservation link, thông báo dedup | Parkalot | Promotion do staff, chưa scheduler fairness | KEEP thủ công rõ ràng; tự động theo policy là FUTURE | P3 |
| Fleet | Membership + site + thời điểm xe tham gia; totals cùng filter | SKIDATA B2B pattern, OWASP | Danh sách xe chưa paginated; chưa có tải thực tế | KEEP privacy; đo list lớn trước tối ưu | P2 nếu đo cần |
| ANPR | Local YOLO ONNX → RapidOCR chạy tùy chọn | Plate Recognizer, RapidOCR | **CONFIRMED:** image production chưa đóng gói OCR/model | ADD package/model provenance, đo RAM/latency; không tự nâng gói | P1 |
| Image security | Bytes/pixels/MIME verify, EXIF strip, BLOB, quota | Frigate, OWASP | Chưa kiểm candidate concurrency PG | Regression upload attacks và purge/review race | P2 |
| OCR verification | Pending/accepted/rejected, nhập sửa, không tự vào/ra | Frigate, Plate Recognizer | Chưa có bộ ảnh VN đánh giá; crop/score provenance cần rõ hơn | ADD bằng chứng; human confirm luôn bắt buộc | P1/P2 |
| Dashboards | Legacy global; site availability/sessions/insights | SKIDATA | Site operational finance/comparison chưa đầy đủ | ADD site summary; admin portfolio view sau dữ liệu chuẩn | P1/P2 |
| Reports | Global exports, fleet scoped, insights scoped | SKIDATA | Manager nhiều bãi không dùng global report | ADD site revenue/report đúng nguồn; không mở global guard | P1 |
| Forecasting | Same-weekday-hour mean, seasonal-naive MAE, range ước lượng | skforecast, FPP3 | Thiếu naive thứ ba và coverage của range | ADD benchmark nhất quán cutoff và interval coverage | P2 |
| Notification | In-app unique event key; pass 7/1 ngày; offer waitlist | Parkalot, Skedda | Worker health chưa được trình bày tốt | KEEP; log/timing/đếm xử lý; email/push là FUTURE | P2/P3 |
| PDF receipts | Owner-scoped PDF, chứng từ demo có nhãn | TigerBeetle audit pattern | Chưa UAT online có tài khoản; mở site finance cần scope | KEEP nội dung + ADD scoped staff access theo contract | P1/P2 |
| Monitoring | `/ready`, release ID, Fly health, workflow 15 phút | SKIDATA operations | Chủ yếu public contract, chưa traffic nghiệp vụ | ADD worker/inference timings và online UAT evidence | P2 |
| Backup/recovery | CD backup/PITR gate, runbook rollback | GitHub deployment controls; nội bộ | Chưa có restore rehearsal mới cho candidate | Rehearsal DB riêng và so row/invariant/schema trước release | P1 release gate |
| Deployment | Fly/CD, Pages auto build, pinned image/action | GitHub environments | Frontend/backend deploy riêng, cần kiểm cùng SHA/contract | KEEP gate; rollout compatibility rồi đối chiếu asset/API | P2 |
| Migrations | Alembic + SQLite rollout + trigger inventory | DB tests nội bộ | Site finance additive cần test populated DB | Upgrade/retry/parity/restore; không destructive backfill | P1 |
| Testing | Nhiều suite theo risk + PG CI + browser scripts | RapidOCR, skforecast | Số test không là coverage; thiếu dữ liệu/device production | Risk matrix ở phần 11, không lấy mock làm accuracy | P2 |
| Observability | Log thường, audit, health/release ID | OWASP, SKIDATA | **CONFIRMED:** thiếu request correlation/timing thống nhất | ADD request ID được kiểm, latency, structured worker log | P2 |
| Accessibility | MUI/form labels/busy/error; chưa audit toàn diện | Review persona; OWASP cho lỗi quyền | **NOT VERIFIED:** keyboard/screen-reader/focus | Kiểm các luồng vào/ra/portal/camera, sửa lỗi tái hiện | P2 |
| Responsive UI | Responsive stacks, portal/site pages, ảnh upload điện thoại | Parkalot, Skedda | Viewport chưa chứng minh chụp bằng điện thoại thật | Browser 390px + thiết bị thật; tránh tràn bảng/modal | P2 |
| Gemini boundary | Mặc định OFF, fail-closed, số liệu từ service | OWASP + FPP3 data provenance | Biên bản live trước ghi bật; chưa test provider | Tắt theo quyết định demo; giữ 503; không gọi LLM làm phí/quyền | P1 cấu hình |

Nguồn deployment phụ trợ: [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments). Tài liệu GitHub mô tả environment protections; trạng thái protection/secrets thực tế vẫn phải kiểm riêng, không suy từ YAML.

## 11. Risk-based test strategy và gaps

Trong lượt khảo sát này **chỉ đọc mã, test và bằng chứng cũ; không chạy test ứng dụng mới**. [Kết quả vòng 2](REVIEW_ROUND2_RESOLUTION_2026-09-08.md) ghi 1.177 backend và 134 frontend đã đạt ở thời điểm đó; các số này không được tái dùng làm kết quả candidate vòng 3.

| Risk | Test hiện có để mở rộng | Ca nghiệm thu vòng 3 |
| --- | --- | --- |
| BOLA/RBAC | `test_acceptance_security`, `test_expansion_legacy_boundary`, `test_portal_api`, `test_expansion_fleet_report` | Bốn role; own/foreign/missing IDs; site inactive; thu hồi membership; receipt/image/fleet; cấm client gán site của payment. |
| Financial invariants | `test_checkout_quote_contract`, `test_finance_concurrency`, `test_finance_and_shifts`, `test_portal_concurrency` | Quote 120s boundary, state/rate đổi; thu–đóng ca đồng thời; chứng từ đúng site; demo không vào ca/doanh thu thật; refund bù, replay không cấp vé thêm. |
| Booking concurrency | `test_expansion_sites_concurrency`, `test_check_in_concurrency`, `test_postgres_integration` | Cap 5 với nhiều xe của cùng customer và hai connection; last slot, waitlist offer, arrive/cancel; test cả SQLite và PostgreSQL. |
| Privacy thời điểm | `test_portal_api`, `test_monthly_coverage_snapshot`, `test_expansion_fleet_report` | Duyệt chủ sau admission không thấy lịch sử; xe đổi chủ/fleet không kéo lịch sử cũ; unlink không xóa dữ liệu. |
| DB/migration | `test_expansion_migration`, `test_snapshot_sync`, `test_postgres_contract`, `test_postgres_integration` | Schema ca/payment mới trên DB đã có thu/hoàn/ca đóng; nullable site lịch sử; trigger/index parity; upgrade lặp; restore tách biệt. |
| Vision security/resource | `test_expansion_vision_api`, `test_audit_responsiveness` | MIME spoof/bomb/EXIF/MPO; foreign camera/image; cap 500; 30/phút; review/purge race; inference không giữ DB; lỗi model không làm treo `/ready`. |
| OCR thực tế | Bộ ảnh có nhãn và metadata nguồn, tách khỏi test fake model | Exact full-plate match, detection misses, CER, latency, peak RAM; ảnh VN đủ ngày/đêm/nghiêng/mờ/hai dòng; không đặt mục tiêu accuracy giả từ hai ảnh nước ngoài. |
| Forecast validity | `test_expansion_forecast`, `test_expansion_insights_api` | Ba baseline cùng cutoff/folds/targets; no future leakage; missing vs zero; empirical interval coverage; nonnegative finite range; không đủ lịch sử không dự báo. |
| UI | Frontend node tests và browser scripts | Các persona, lỗi mạng/401/403/5xx, double-click, stale site/state, modal focus/keyboard, 390px, chụp điện thoại thật. |
| Release/ops | `test_release_safety`, `test_production_rbac_probe`, `test_production_monitor_workflow` | Build Docker có model hash/dependencies; migration gate; secrets không log; backup + restore evidence; online login UAT trên namespace demo. |

Không cần viết test chỉ để kiểm tra một dòng Markdown hoặc lặp y nguyên implementation. Với ca tài chính/quyền/concurrency mới, assertion phải kiểm kết quả và trạng thái DB sau tranh chấp, không chỉ HTTP 200. PG skip ở local phải được bù bằng bằng chứng CI PG cho đúng commit.

## 12. Production readiness tại thời điểm bắt đầu

Biên bản cục bộ ngày 08/09/2026 khoảng 18:19–18:30 giờ Việt Nam đã kiểm đúng release `caaef39`, revision `20260908_01`. Hồ sơ và credential files giữ ngoài Git; tài liệu này chỉ ghi số tổng hợp cần cho quyết định, không sao chép hồ sơ người dùng.

| Khía cạnh | Trạng thái lịch sử đã ghi | Ý nghĩa hiện tại |
| --- | --- | --- |
| Public API/site | API public smoke 45/45; browser 32/33, một lỗi beacon Cloudflare bị CSP chặn | Đây là kết quả cũ, không phải lần chạy mới. Lỗi analytics không phải lỗi xe vào/ra; không nới CSP wildcard. |
| Dữ liệu online | 1 site; 0 slot/session/plan/order/camera | Website có code nhưng chưa đủ dữ liệu để trình diễn nghiệp vụ đầy đủ tại lần kiểm đó. Không biến invariant trên bảng trống thành chứng minh giao dịch đúng. |
| Authenticated UAT | Không có tài khoản test production | Chưa chứng minh các flow sau login online từ public checks hoặc demo local. |
| QR/OCR | Demo payment tắt; OCR disabled, chưa model trong image production | Cần bật chế độ demo có chủ đích sau seed riêng và resource gate, không mặc nhiên coi đã chạy vì có trang UI. |
| Gemini | Default code false; biên bản live ghi `AI_ENABLED=true`, provider chưa được gọi | Theo quyết định mới, phải tắt cho bản demo vòng 3 và kiểm behavior 503. |
| Camera accuracy | Hai ảnh nước ngoài: một đọc sai toàn biển, một không tìm thấy biển | Không đủ tập đánh giá Việt Nam; giữ sửa tay/confirm, ghi giới hạn. |
| Backup/CD | CD đã qua gate trước release cũ; chưa có rehearsal mới trong khảo sát này | Phải kiểm lại freshness và thực hiện restore độc lập trước migration candidate. |

**Kết luận đầu vào:** bản demo SQLite có bằng chứng cũ về các flow đã chạy; online chưa được kết luận sẵn sàng trình diễn đầy đủ hoặc vận hành thật. Không chấm một phần trăm hoàn thành từ số trang/số test. Nghiệm thu theo capability, cấu hình, dữ liệu và bằng chứng cho đúng release.

## 13. Backlog và gap register

Đây là ID review nội bộ để đối chiếu PR; danh sách Jira/Trello chính thức nằm trong [tickets](tickets/tickets.json). Tài liệu này không tự tạo/cập nhật ticket trên dịch vụ ngoài.

| ID | Loại / priority | Công việc cụ thể | Acceptance / dependency |
| --- | --- | --- | --- |
| R3-G01 | CONFIRMED / P1 | Scoped shift/payment/revenue và UI cho staff/manager nhiều bãi | Bãi A không thấy B; ca/chứng từ đúng site; lịch sử null không được suy bãi; demo bị loại khỏi tổng thật; cần migration và tests tài chính/PG. |
| R3-G02 | CONFIRMED / P1 | Scoped sửa zone/slot cho vận hành bãi | Trả 403/404 phù hợp cho foreign ID; chặn đổi type/disable khi còn active/future commitments; giữ v1 admin boundary. |
| R3-G03 | CONFIRMED / P2 | Semantic audit v2, site/object, request ID và timing | Truy được entry/checkout/order/refund/booking/OCR/denial; ID hợp lệ hoặc sinh mới; không log secrets/body/ảnh; GET denial cần chính sách rõ. |
| R3-G04 | CONFIRMED / P1 | Đóng gói YOLO/RapidOCR và model cho Fly hiện tại | Hash/nguồn/license weight ghi rõ; Docker smoke; đo RAM/latency dưới tải nhỏ; readiness vẫn trả; không đạt thì giữ nhập tay, báo blocker cụ thể. |
| R3-G05 | CONFIRMED / P2 | Bằng chứng OCR và evaluation | Crop/scores/candidates/model metadata; no_plate/uncertain không ép thành đúng; review tách domain action; báo số đo trên tập có nhãn. |
| R3-G06 | CONFIRMED / P2 | Ba baseline + empirical coverage | Cùng folds/targets; naive, seasonal-naive, mean; MAE và coverage có sample count; legacy response fields tương thích; UI dải và cảnh báo đúng. |
| R3-G07 | CONFIRMED tại lần kiểm trước / P1 | Tài khoản và dữ liệu online riêng cho demo | Namespace định danh, 4 role, tối thiểu 2 site để test scope; script idempotent không reset DB; secret sinh ngẫu nhiên chỉ file ignored; UAT đủ flow. |
| R3-G08 | NOT VERIFIED / P2 | Mobile/a11y/reliability theo persona | Có bằng chứng keyboard/focus, viewport và điện thoại; lỗi nguồn phụ không phá flow chính; double-click không nhân đôi tác dụng. |
| R3-G09 | CONFIRMED tại lần kiểm trước / P2 | Beacon analytics/CSP không khớp | Nếu không dùng analytics: bỏ injection; nếu dùng: chỉ nguồn chính thức cần thiết. App vẫn giữ CSP chặt. |
| R3-H01 | HYPOTHESIS / chưa xếp lỗi | Race cap booking theo khách nhiều xe | Test hai connection tái hiện vượt 5 mới xác nhận bug và đánh giá priority theo tác động; nếu không tái hiện, ghi điều kiện bảo vệ và kết quả. |
| R3-H02 | HYPOTHESIS / P2 nếu đo có tác động | Availability query-per-slot, fleet list lớn, blob storage | Đo số query/latency/RAM/data size trước; tối ưu targeted thay vì thêm Redis/index hàng loạt. |
| R3-R01 | RELEASE CONDITION / P1 | Backup/restore rehearsal và phát hành đúng SHA | Restore DB riêng, kiểm schema/row totals/invariants; CI PG xanh; API release ID + Pages asset contract khớp; rollback code/schema tương thích. |

Những vùng giữ lại với **NO MATERIAL GAP FOUND** chỉ gồm: kiến trúc một operator + site guard đã đọc; thiết kế chọn slot và guard admission đã đọc; contract signed quote; sổ thu/hoàn append-only và DEMO exclusion trong service/model đã đọc. Không áp nhãn này cho toàn security, accessibility, OCR accuracy, authenticated production UAT hoặc hiệu năng chưa đo.

## 14. PR plan và lộ trình thực hiện đã duyệt

Chi tiết điều phối/candidate thực thi theo [plan.md](../plan.md). Các PR dưới đây là batch reviewable; không có yêu cầu viết lại v1 toàn bộ hoặc tạo một mega-refactor. Trạng thái mặc định trong tài liệu này là **planned**, không phải merged/deployed.

| Phase / PR | Nội dung | Cổng chuyển tiếp |
| --- | --- | --- |
| Phase 0 — PR-01 | System map, 14 mục review, primary research, benchmark và backlog | Liên kết/caller/schema được đối chiếu; tách confirmed/hypothesis; không suy kết quả mới từ test cũ. |
| Phase 0 — PR-02 | Correctness/security review, nhất là cap booking nhiều xe | Tái hiện → sửa → regression nếu có lỗi; các invariant/quyền không yếu đi; cả SQLite/PG. |
| Phase 1 — PR-03 | Ca/chứng từ/doanh thu theo site, sửa zone/slot scoped | Nullable site additive, v1 boundary giữ; phiếu demo không vào tiền thật; UI các role hợp lệ. |
| Phase 2 — PR-04 | Audit v2 và observability | Request ID/timing/log worker hữu ích, secrets không lộ; audit không giữ khóa/tắc event loop. |
| Phase 2 — PR-05 | YOLO/OCR trong image online, provenance/crop/candidates | Thử trên cấu hình Fly hiện có; đo tài nguyên; không tự bật khi OOM/readiness fail hoặc model không hợp lệ. |
| Phase 2 — PR-06 | Forecast baselines/range evaluation | Không leakage, coverage/sample count rõ; không đủ dữ liệu vẫn fail closed; không deep learning mới. |
| Phase 3 — PR-07 | UX staff/manager/admin/customer, mobile/a11y và lỗi mạng | Flow bốn role, keyboard/focus, retry/duplicate/stale state, thiết bị điện thoại và bằng chứng ảnh thật. |
| Phase 4 — PR-08 | Backup + restore, deploy, namespace demo online, UAT và bàn giao | Không reset dữ liệu; Gemini OFF, QR mock; đúng SHA; kiểm nghiệm tài khoản/thao tác sau login; ghi giới hạn OCR và rollback. |

Rollout theo thứ tự: hoàn tất candidate và tests → CI SQLite/PostgreSQL/frontend/Windows phù hợp → backup đủ mới + restore rehearsal → migration additive → deploy backend/frontend tương thích → kiểm release/health → seed namespace demo idempotent → UAT online. Migration rollback không đồng nghĩa phục hồi dữ liệu: không downgrade hoặc xóa chứng từ mới để đưa code cũ lên. Nếu schema vẫn tương thích thì rollback image; nếu không phải dùng kế hoạch restore đã kiểm chứng.

Các tiêu chí hoàn tất: không còn lỗi đã xác nhận phá invariant; chức năng mới có API, UI và test đúng phạm vi site; dữ liệu demo không lẫn báo cáo tiền thật; OCR có human confirmation và bằng chứng giới hạn; forecast có baseline và độ bất định; hoạt động online được kiểm bằng tài khoản thật. Chỉ ghi release hoàn thành sau khi có bằng chứng tương ứng.
