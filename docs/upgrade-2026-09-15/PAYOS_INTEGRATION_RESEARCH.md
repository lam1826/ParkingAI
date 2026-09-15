# payOS: nghiên cứu tích hợp P5

Ngày đối chiếu: **2026-09-15**. Phạm vi: tài liệu công khai chính thức và mã hiện có của ParkingAI. Đây là phương án triển khai; chưa tích hợp hay nghiệm thu tiền thật. Không đọc cấu hình bí mật, gọi Merchant API, đăng ký webhook hoặc chuyển tiền trong lần nghiên cứu này.

**Đề xuất:** thêm adapter payOS nhỏ dùng `httpx` và HMAC của thư viện chuẩn; giữ DEMO riêng. Tách sự kiện tiền đã xác minh khỏi trạng thái cấp vé. P5 cần cả đối soát và kiểm thử lỗi/trùng/trễ, không chỉ hiển thị QR. Phạm vi này khớp [kế hoạch mở rộng](EXTENSION_PLAN.md), mục 6 và P5.

## 1. Những gì nguồn chính thức xác nhận

### Môi trường và phiên bản

payOS công bố **không có sandbox/staging riêng**; thử nghiệm tích hợp sử dụng môi trường production. Vì vậy test tự động của đồ án phải dùng transport giả lập; kiểm thử có giao dịch thật là một đợt nghiệm thu riêng khi đã cấu hình tài khoản. [Môi trường test payOS](https://payos.vn/docs/moi-truong-test/).

PyPI đang công bố `payos 1.1.0`, phát hành 2026-01-22, Python từ 3.9. Metadata SDK yêu cầu `httpx>=0.24.0`, `typing-extensions>=4.0.0`, `pydantic>=2.11.7`. Chưa cài SDK vào dự án. [Bản phát hành PyPI](https://pypi.org/project/payos/1.1.0/), [metadata SDK](https://github.com/payOSHQ/payos-lib-python/blob/main/pyproject.toml).

API Python hiện hành dùng `PayOS`/`AsyncPayOS`, `CreatePaymentLinkRequest`, `payment_requests.create()` và `webhooks.verify()`; có hỗ trợ async cho FastAPI. Không lấy ví dụ SDK đời cũ làm hợp đồng mới. [Python SDK chính thức](https://payos.vn/docs/sdks/back-end/python/), [hướng dẫn chuyển SDK v0 sang v1](https://github.com/payOSHQ/payos-lib-python/blob/main/MIGRATION.md).

### REST tối thiểu

Base URL: `https://api-merchant.payos.vn`; xác thực bằng `x-client-id`, `x-api-key`. [payOS API](https://payos.vn/docs/api/).

| Thao tác | Endpoint | Nội dung chính |
|---|---|---|
| Tạo | `POST /v2/payment-requests` | `orderCode`, `amount`, `description`, `cancelUrl`, `returnUrl`, `signature`; tùy chọn `expiredAt` |
| Tra cứu | `GET /v2/payment-requests/{id}` | `id` nhận mã đơn hoặc mã link |
| Hủy link | `POST /v2/payment-requests/{id}/cancel` | `cancellationReason` tùy chọn |
| Đăng ký webhook | `POST /confirm-webhook` | `webhookUrl`; provider gửi giao dịch mẫu để kiểm tra |

`expiredAt` là Unix timestamp Int32. Mô tả có giới hạn 9 ký tự với tài khoản không liên kết qua payOS. [Hợp đồng REST](https://payos.vn/docs/api/).

SDK bật kiểm chữ ký response cho create/get/cancel; cancel còn ký body. Tên hàm: `payment_requests.get(id)`, `payment_requests.cancel(id, cancellation_reason=...)`. Đây là chi tiết quan trọng khi thay SDK bằng HTTP trực tiếp; trang REST chỉ thể hiện lý do hủy trong ví dụ. [Mã resource payment requests](https://github.com/payOSHQ/payos-lib-python/blob/main/src/payos/resources/v2/payment_requests/payment_requests.py).

Response create có `paymentLinkId`, `orderCode`, `amount`, `currency`, `status`, `checkoutUrl`, `qrCode` và thông tin tài khoản nhận. Get/cancel dùng `id`, `amountPaid`, `amountRemaining`, `transactions` cùng số tiền/trạng thái. SDK khai báo `transactions` là danh sách; ví dụ REST hiện hiển thị `{}` nên không dùng ví dụ đó thay schema. Các trạng thái SDK gồm `PENDING`, `PROCESSING`, `UNDERPAID`, `PAID`, `CANCELLED`, `EXPIRED`, `FAILED`. [Kiểu dữ liệu payment requests](https://github.com/payOSHQ/payos-lib-python/blob/main/src/payos/types/v2/payment_requests/payment_requests.py).

### Chữ ký và webhook

Create ký HMAC-SHA256 trên năm trường theo thứ tự: amount, cancelUrl, description, orderCode, returnUrl; nối từng cặp bằng `&`, không dùng ký JSON nguyên body. Webhook/response ký đối tượng `data` sau khi sắp khóa. Thuật toán payout khác payment requests; không dùng lẫn. [Hướng dẫn signature](https://payos.vn/docs/tich-hop-webhook/kiem-tra-du-lieu-voi-signature/).

Mã Python SDK hiện xử lý UTF-8, boolean thành chữ thường, null và chuỗi `null`/`undefined` thành chuỗi rỗng; danh sách giữ thứ tự phần tử, sắp khóa object trong phần tử, JSON gọn và giữ Unicode. Payment-request canonicalization không URL-encode giá trị. Các ví dụ ngôn ngữ trên trang hướng dẫn có khác biệt ở boolean/null; test adapter cần bám hợp đồng SDK đã chọn và fixture xác minh, không ghép nhiều ví dụ. [Crypto provider của SDK](https://github.com/payOSHQ/payos-lib-python/blob/main/src/payos/_crypto/provider.py).

Webhook có envelope `code`, `desc`, `success`, `data`, `signature`; dữ liệu chứa mã đơn/link, số tiền, tiền tệ, tài khoản nhận, tham chiếu giao dịch và thời điểm giao dịch. HTTP 2xx xác nhận bên nhận đã tiếp nhận. [Webhook chính thức](https://payos.vn/docs/du-lieu-tra-ve/webhook/).

`webhooks.verify()` kiểm schema/chữ ký rồi trả `data`; mã đã đọc **không đối chiếu đơn ParkingAI, số tiền mong đợi hoặc tính hợp lệ để cấp vé**, cũng không kiểm `success`/mã kết quả để tự quyết định hoàn tất nghiệp vụ. Những kiểm tra đó thuộc service ứng dụng. [Mã xác minh SDK](https://github.com/payOSHQ/payos-lib-python/blob/main/src/payos/resources/webhooks/webhooks.py).

`returnUrl`/`cancelUrl` nhận query để giao diện xử lý điều hướng; `cancel=false` còn có thể là đang chờ. Thiết kế ParkingAI chỉ dùng chúng để mở trang trạng thái rồi đọc backend, không làm chứng từ thu tiền. [Return URL](https://payos.vn/docs/du-lieu-tra-ve/return-url/).

Các trang đã đối chiếu không chốt lịch retry webhook, thời gian lưu giao dịch, bảo đảm thứ tự/giao đúng một lần, phạm vi duy nhất của `reference`, hoặc múi giờ của chuỗi `transactionDateTime` không có offset. Không tự gán các bảo đảm này. Chính sách duplicate/late bên dưới là **thiết kế đề xuất của ParkingAI**, không phải cam kết của payOS.

## 2. Nền tảng hiện có và khoảng thiếu

| Mã hiện có | Kết quả đối chiếu | Ý nghĩa cho P5 |
|---|---|---|
| [gateway.py](../../backend/expansion/gateway.py) | `DemoGateway` không gọi mạng, phát token/QR DEMO; cờ mặc định tắt | Giữ nguyên công dụng; không đổi nhãn DEMO thành payOS |
| [portal_schemas.py](../../backend/expansion/portal_schemas.py) | `payment_mode` chỉ `demo`/`manual`; số tiền lấy từ gói phía server | Thêm provider là thay đổi schema có chủ đích, không nhận amount từ browser |
| [portal_models.py](../../backend/expansion/portal_models.py) | Order khóa số tiền/kỳ/bãi; event unique `(provider, reference)`; thiếu orderCode/paymentLinkId/currency/transaction time/provider account | Cần mapping bền vững và dữ liệu đối soát, không dùng UUID order trực tiếp làm orderCode số |
| [portal_service.py](../../backend/expansion/portal_service.py) | `simulate()` commit inbox trước fulfillment; `process_event()` hardcode `method="demo"`; đơn fulfilled bỏ qua việc cấp lại | Tái dùng ý tưởng inbox/transaction; tách processor thật, kiểm giao dịch thứ hai thay vì bỏ qua |
| [portal_worker.py](../../backend/expansion/portal_worker.py) | Có worker retry event và hết hạn đơn | Có chỗ nối reconciliation, nhưng phải phân nhánh provider rõ |
| [payment_service.py](../../backend/services/payment_service.py) | Receipt một lần/source, amount chính xác, phương thức transfer hỗ trợ collector null; ledger theo bãi/source | Thu online không gán ca hay nhân viên giả; cần provenance nối đến giao dịch đã xác minh |
| [payment.py](../../backend/models/payment.py) | Receipt chỉ có nguồn parking_session/monthly_pass; số tiền phải khớp nguồn | Tiền đã vào nhưng chưa cấp vé không thể tạo receipt khống để vượt ràng buộc |
| [requirements.txt](../../backend/requirements.txt) | Có `httpx==0.28.1`; chưa có payos | Adapter nhỏ không cần thêm thư viện HTTP |

Luồng `process_event()` hiện dùng thời điểm **nhận** event để phát hiện trễ và chỉ phục vụ DEMO. Với giao dịch thật cần lưu riêng thời điểm provider báo giao dịch và thời điểm nhận; chậm giao webhook khác với khách trả tiền sau hạn. Ngoài ra, `cancel_order()` chỉ đổi trạng thái local; review/refund hiện giới hạn DEMO. Không đưa payOS vào các nhánh này bằng cách thay chuỗi tên provider. Nguồn: [portal_service.py](../../backend/expansion/portal_service.py).

## 3. Adapter và hợp đồng đề xuất

Đây là lựa chọn thiết kế cho một bãi, chưa phải API đã triển khai.

**Chọn `httpx` + `hmac`/`hashlib`/`json`**, với client được inject để test bằng `httpx.MockTransport`. Bốn thao tác runtime đủ dùng: `create_link(order_snapshot)`, `get_link(provider_order_code)`, `cancel_link(identity, reason)`, `verify_webhook(raw_payload)`. Hàm verify không gọi mạng. `confirm-webhook` là thao tác cấu hình riêng, không chạy tự động khi app khởi động.

Lựa chọn SDK `payos==1.1.0` vẫn phù hợp nếu muốn giảm mã HTTP/chữ ký: bọc trong cùng interface, khóa phiên bản, cấu hình timeout/retry và test adapter. SDK cung cấp client HTTP tùy biến, timeout và max_retries theo request. [README SDK](https://github.com/payOSHQ/payos-lib-python). SDK không thay thế validation/ledger/inbox của ParkingAI. Với phạm vi nhỏ hiện tại, adapter HTTP giúp thấy rõ payload, chính sách retry và kiểm thử offline; đổi sang SDK sau này không đổi service nghiệp vụ.

Quy tắc adapter:

- Chỉ server đặt amount, TTL, orderCode, mô tả và return/cancel URL từ cấu hình cố định. Đề xuất mô tả ASCII tối đa 9 ký tự cho phạm vi tương thích; không nhét biển số hay PII.
- Sinh orderCode số duy nhất bằng sequence bền vững; không dùng `int(time.time())` làm cơ chế duy nhất. Lưu mapping trước khi gọi mạng; đề xuất miền integer dương an toàn cho JSON của ParkingAI. Giới hạn chính xác của provider phải xác nhận khi nghiệm thu.
- Tách DTO snake_case nội bộ và camelCase trên wire. Parse JSON raw trước xác minh; không bỏ trường lạ hoặc ép số/string trước khi tính chữ ký. Từ chối JSON trùng key, số bool/float ở trường tiền và hình dạng ngoài hợp đồng.
- So sánh chữ ký bằng `hmac.compare_digest`; thiếu chữ ký/không khớp đều không được cấp quyền. Kiểm HMAC response create/get/cancel như SDK, sau đó kiểm envelope mã thành công và schema.
- Timeout hữu hạn; response không hợp lệ hoặc timeout là **chưa biết kết quả**, không tự kết luận thất bại/đã hủy. Trước retry tạo, tra cùng orderCode; không sinh đơn/mã mới sau lỗi mạng chưa rõ.
- Không giữ transaction khóa SQL trong lúc chờ HTTP. Dùng trạng thái tạo link đang xử lý, finalize có khóa và so lại snapshot; nếu webhook đến trước finalize vẫn tra được mapping orderCode đã lưu.
- Giữ API key/checksum tại backend; không log headers, QR payload đầy đủ hoặc tài khoản đối ứng. Chỉ DTO public được trả cho chủ đơn.

Hợp đồng dữ liệu tối thiểu đề xuất:

| Bản ghi/DTO | Trường cần có |
|---|---|
| Mapping provider ↔ order | local order UUID, provider/channel identity, unique numeric orderCode, unique paymentLinkId khi có, amount/currency snapshot, expiry, tạo/hủy/tra cứu gần nhất, trạng thái provider tách trạng thái local |
| Link public của chủ đơn | provider label, checkout URL/QR, amount, expiry, local status; không có secret hay dữ liệu đối ứng |
| Event đã xác minh | provider/channel, reference, orderCode, paymentLinkId, amount, currency, tài khoản nhận đã đối chiếu, provider transaction time/raw timezone metadata, received_at, digest của nội dung đã xác minh |
| Xử lý event | trạng thái received/processed/review, lý do, attempts/next_attempt_at; mapping đến receipt khi đã phân bổ |
| Đối soát | event và tiền thực nhận bất biến; lịch sử quyết định, actor, lý do; trạng thái chờ phân bổ/đã cấp quyền/đang hoàn/đã hoàn có bằng chứng |

Ưu tiên mở rộng event hiện có nếu đủ guard; event lạ không có local order cần inbox quarantine riêng hoặc FK order nullable có ràng buộc trạng thái. Không được mất giao dịch chỉ vì FK order bắt buộc. Provider account/channel là snapshot định danh, không lưu API key trong bảng nghiệp vụ.

## 4. Xác nhận tiền, trùng và trễ

Các bước này là chính sách ứng dụng đề xuất:

1. Webhook kiểm kích thước/JSON/schema/chữ ký; envelope thành công và `data.code` thành công phải nhất quán. Envelope không nằm trong `data` được ký, nên không tin chỉ `success=true`.
2. Đối chiếu provider/channel đang cấu hình, orderCode **và** paymentLinkId, currency VND, tài khoản nhận, amount với snapshot server. Không so bằng substring mô tả hoặc dữ liệu do khách cung cấp.
3. Commit inbox trước trả 2xx. Chữ ký sai trả 4xx; DB chưa lưu được trả lỗi để có thể nhận lại. Event hợp lệ nhưng mismatch/unknown được lưu review rồi ACK; không retry vô hạn một xung đột nghiệp vụ.
4. Khóa order/context theo thứ tự hiện có; unique reference trong phạm vi channel. Gửi lại cùng reference và cùng dữ liệu: ACK, không thêm receipt/kỳ. Cùng reference nhưng khác order/amount/link: review, giữ bản gốc và ghi xung đột.
5. Giao dịch có **reference mới** trên order đã fulfilled vẫn là khoản tiền cần kiểm tra, không âm thầm coi là duplicate. Không tạo kỳ hay receipt thứ hai cho cùng nguồn; ghi khoản chưa phân bổ để quản lý xử lý.
6. Auto-fulfill tối thiểu chỉ khi dữ liệu đã xác minh khớp hoàn toàn, tra cứu authoritative xác nhận paid đúng số tiền, order còn đủ điều kiện và không có khoản thu khác. UNDERPAID/overpaid/nhiều transaction cộng dồn đi review ở bản đầu; không tự triển khai ví hay split payment.
7. Event đến sau TTL, đơn đã hủy, bãi/xe thay đổi hoặc chỗ hết giữ: ghi tiền vào review. Không khôi phục booking đã nhả sức chứa. Lưu cả hai thời điểm để người quản lý phân biệt trả đúng hạn nhưng webhook trễ; chưa tự dựa vào chuỗi thời gian thiếu timezone để bỏ qua TTL.
8. Sau khi xác nhận tiền và điều kiện, cấp quyền + receipt + liên kết event trong cùng transaction, dùng `method="transfer"`, collector/shift null và source site từ snapshot. Nếu cấp quyền lỗi, inbox còn để retry, tiền không biến mất.
9. Hủy local phải yêu cầu hủy link/tra cứu kết quả. Cancel trả không rõ kết quả thì giữ trạng thái cần đối soát, vẫn xử lý webhook về sau. Hủy link **không được ghi là hoàn tiền**; bản P5 đầu không gọi payout tự động.

Do ledger hiện yêu cầu có monthly_pass/parking_session trước receipt, khoản nhận nhưng chưa cấp được vé cần sổ giao dịch provider chưa phân bổ và màn hình đối soát riêng. Báo cáo phải phân biệt tổng tiền provider xác nhận, tiền đã phân bổ thành receipt và tiền đang chờ xử lý; không cộng inbox lẫn receipt vào cùng doanh thu hai lần. Đây là thay đổi nghiệp vụ bắt buộc để giữ ràng buộc hiện có, không phải lý do bỏ guard ledger.

Worker đối soát tra đơn pending/unknown có giới hạn và backoff, đưa kết quả về cùng processor idempotent. Không để browser polling trực tiếp gọi provider mỗi lần. Quầy thu tiền và online xác nhận phải dùng cùng khóa/source receipt: một nhánh phân bổ trước; khoản còn lại vào review. Thu phí lượt đang mở còn phụ thuộc thiết kế `paid_through`/phụ trội P4–P5 trong [kế hoạch mở rộng](EXTENSION_PLAN.md), không thể tái dùng receipt của lượt completed để tự mở cổng.

## 5. Bộ test contract cần triển khai

Các test dưới đây chưa được viết/chạy trong nghiên cứu; tất cả test tự động phải dùng secret giả và HTTP giả.

| Nhóm | Ca phải kiểm | Kết quả cần giữ |
|---|---|---|
| Create | Header/body/5 trường ký, TTL epoch, UTF-8, dấu `&`/`=` trong URL, mô tả ngắn, response signature | Gửi đúng contract; không dùng form URL encoding để ký |
| Get/cancel | Hai kiểu identity, body lý do + ký như SDK, response id/orderCode/paid/remaining/transactions | Không coi HTTP 200 hoặc CANCELLED một mình là xác nhận tiền/hoàn tiền |
| Canonicalization | Hoán thứ tự key; null/undefined, Unicode, bool, mảng; known vectors và so với SDK đã khóa phiên bản | Không tự tạo test chỉ lặp lại cùng hàm ký đang kiểm |
| Schema/HMAC | Thiếu/sai signature, amount float/bool/string, duplicate JSON key, trường lạ/tampered, envelope lệch data.code | Không ghi receipt/cấp vé; không làm rơi trường trước HMAC |
| Đối chiếu tiền | Sai amount/currency/account/orderCode/link; order không tồn tại; sự kiện mẫu đăng ký webhook | Review/ACK bền vững khi đã xác minh, không cấp quyền nhầm đơn |
| Trạng thái provider | Pending/processing/underpaid/paid/expired/cancelled/failed, unknown status, thiếu/thừa/nhiều khoản | Auto-fulfill chỉ đúng hợp đồng bản đầu; còn lại review |
| Idempotency | Duplicate tuần tự/song song; cùng ref khác dữ liệu; ref mới sau fulfilled; webhook và worker cùng chạy | Một kỳ/receipt, không mất khoản thứ hai |
| Mạng/crash | Create timeout sau provider đã nhận; webhook trước finalize; crash sau inbox và trước fulfillment; 429/5xx | Dùng lại mapping, reconciliation, không tạo link/receipt đôi |
| Trễ/race | TTL đúng biên; webhook trễ; cancel vs paid; hết giữ chỗ; owner/site thay đổi; quầy thu đồng thời | Không khôi phục quyền sai, giữ tiền vào review |
| Tài chính/quyền | Collector/shift null online; source site đúng; staff không xem aggregate tiền; khách chỉ xem đơn mình | Giữ guard ledger, ownership và role matrix |
| Hoàn tiền | Cancel link, từ chối review, yêu cầu hoàn, xác nhận hoàn thực tế là các việc khác nhau | Không báo đã hoàn chỉ từ thao tác local |
| DEMO | Demo off; nhãn rõ; payOS không dùng simulate token/processor demo | Dữ liệu mô phỏng không trở thành tiền thật |

Cần kiểm mẫu confirm-webhook: provider gửi dữ liệu mẫu có thể có mã đơn dạng số đơn giản. Thiết kế không hardcode “bỏ qua mọi orderCode=123”; dùng mapping và validation để mẫu không cấp vé, đồng thời lưu/ACK an toàn sự kiện đã xác minh không khớp đơn.

## 6. Giới hạn kết luận và bước tiếp theo

Chưa xác minh bằng Merchant API thật: hạn mức orderCode/amount, timezone transactionDateTime, lịch retry và thời gian đối soát, quy tắc tài khoản nhận/virtual account cho kênh ngân hàng cụ thể, cancellation race, giao dịch thiếu/thừa và payload confirm-webhook thực tế. Khi cấu hình kênh phải kiểm những điểm này bằng tài liệu/support của provider và đợt nghiệm thu riêng; không dùng giả định để bật auto-fulfill.

Triển khai theo thứ tự: migration mapping/inbox/provenance → adapter + vector test → worker/transaction/review → UI QR và trạng thái → đối soát với thu tại quầy → nghiệm thu tiền thật được cấu hình riêng. Tài liệu nghiên cứu này không thay đổi trạng thái hoàn thành P5 và không thay thế cổng nghiệm thu lõi P0–P3.
