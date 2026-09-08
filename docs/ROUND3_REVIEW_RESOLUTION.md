# Review độc lập vòng 3 — đối chiếu sau cài đặt

Mốc `caaef39042ea15fc93f01938af46a7ac64890258`; commit backend được review: `0979d1c`. Nguồn spec là kế hoạch đã duyệt trong `plan.md` và `intent.md`. Giao diện được cài đặt trong working tree, phát hành sau backend. Khảo sát 14 mục ban đầu nằm trong `REVIEW_ROUND3_SYSTEM_MAP.md` (1–7) và `REVIEW_ROUND3_RESEARCH.md` (8–14); không thay khảo sát baseline thành lời khẳng định production hiện tại.

## Standards

Không thấy vi phạm cứng tiêu chuẩn viết mã được ghi trong repository. Một nhận xét về **Duplicated Code**: middleware request tự dựng response 500 bên ngoài middleware bảo mật, làm thiếu HSTS, Referrer-Policy và Permissions-Policy. Đã tái hiện bằng test header bị thiếu; sửa bằng `apply_security_headers` dùng chung cho response thường và lỗi. Bản sao SQL frozen trong migration được giữ có chủ đích, không coi là lỗi cần hợp nhất.

## Spec

Một lỗi P1 đã tái hiện: yêu cầu “Ca mới gắn một bãi; giao dịch không được nhập vào ca của bãi khác” bị vượt qua khi admin mở ca qua v1 với `site_id=null`. Hai khoản từ hai bãi cùng nhập ca mới đó thành công trên SQLite riêng. Test HTTP xác nhận v1 trả 201/site null trước sửa. Service hiện tự chọn bãi khi chỉ có đúng một bãi, từ chối 409 khi nhiều bãi và hướng sang workspace v2. Dữ liệu lịch sử null không backfill. Cơ sở dữ liệu legacy chưa có bãi vẫn tương thích cho đến rollout tạo bãi mặc định.

Tại thời điểm review mã độc lập chưa xác nhận thêm lỗi spec đáng kể trong finance, thu hồi quyền, khóa giới hạn đặt chỗ, forecast, OCR và seed. UAT sau đó phát hiện lỗi OOM của runtime OCR, được xử lý riêng bên dưới; kết quả review mã không thay bằng chứng chạy thật.

Kết quả review ban đầu: Standards có 0 vi phạm cứng/1 nhận xét heuristic (thiếu header lỗi); Spec có 1 lỗi P1 (ca mới không gắn bãi). Cả hai đã có ca tái hiện và bản sửa; kết quả kiểm thử cuối ghi ở release gate.

## Các gap baseline đã xử lý

| Gap | Quyết định và thực thi | Bằng chứng kiểm tra |
| --- | --- | --- |
| Cap đặt chỗ nhiều xe một khách | FIX: khóa customer trước vehicle; kiểm lại chủ xe và cap | PG hai kết nối: trước sửa cả hai request thành công và tổng 6; sau sửa 201/409 và tổng 5 |
| Quyền manager tồn dư | FIX: role toàn cục bị hạ phải chặn quyền manager từ membership cũ | Test đổi role trước/sau, UI nhận effective role staff |
| Không có finance/config scoped | ADD: v2 cash-shifts/payments/revenue/PDF/refund và PATCH zone/slot | SQLite contract, PG checkout/refund/close races, browser staff/manager |
| Audit v2 chung chung | FIX: phân loại domain action/resource, request ID/site/duration | Tests success/invalid-ID/500, giữ v1 action; log không có body/token |
| OCR không có runtime website | ADD/FIX: build flag, pin/hash, crop/candidates; giới hạn resize sau khi UAT tái hiện OOM | RED tensor736x2944; GREEN23 tests; CI memory345,4MiB; Fly cuối371,2MiB và upload/giao diện đạt |
| Chưa có baseline đối chứng | ADD: rolling-origin naive/seasonal/weekday-hour + empirical coverage | Không lấy future data/residuals; giữ model hiện tại |
| Demo thiếu tài khoản/dữ liệu | ADD: seeder namespaced, dry-run, manifest, replay | SQLite và clone PG17; 7 tài khoản mật khẩu riêng ignored, lịch sử 0 phí |
| Finance append-only, quote, legacy boundary | KEEP: NO MATERIAL GAP FOUND trong các phần giữ nguyên đã kiểm | Regression và DB guard suites; không tháo guard v1 |
| Video liên tục, ngân hàng thật, SaaS | FUTURE: ngoài phạm vi đồ án đã duyệt | Không thêm dịch vụ hoặc gói có phí |

Các ticket nhập Jira/Trello nằm trong `docs/tickets/round3-tickets.json` và CSV cùng tên. Đây là PR plan gồm tám nhóm logic; việc đưa code lên website dùng hai batch backend rồi frontend để tránh caller chạy trước API. Không tự tạo ticket trên dịch vụ bên ngoài.

Hotfix `adc749f` bổ sung sau hai batch: RapidOCR mặc định phóng cạnh ngắn lên736, gây OOM khi upload qua browser. Đã tắt engine, tái hiện với thư viện thật, giới hạn crop và chế độ resize, thêm CI Docker cô lập có hạn RAM rồi mới bật lại. Ba upload API và19 kiểm tra giao diện cuối đạt. Sự cố cũ, độ trễ cold và giới hạn đánh giá được giữ trong `ROUND3_RELEASE_GATE.md`; không nâng gói hoặc nới CSP.
