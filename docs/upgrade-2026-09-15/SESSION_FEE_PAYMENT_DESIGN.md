# Thanh toán phí lượt đang gửi qua payOS

Trạng thái: đã triển khai backend đề nghị, ghi có, đối soát và tích hợp thu khi xe ra; đang nghiệm thu tích hợp P8. Phạm vi một bãi, mặc định `PAYOS_ENABLED=false`. Không có tài khoản payOS nên kiểm thử provider dùng HTTP giả lập có chữ ký; không gọi ngân hàng, không đăng ký webhook, không chuyển tiền thật. Bằng chứng kiểm thử từng nhóm nằm cuối tài liệu và không thay thế nghiệm thu provider thật.

## Quy tắc nghiệp vụ

- `ParkingSession.parking_fee` tiếp tục là **tổng phí danh nghĩa F**, tính từ chính sách bất biến của lượt gửi. Không đổi nó thành số dư để né kiểm tra sổ thu.
- `C` là tổng tiền online đã được xác minh và phân bổ cho lượt này. Số cần thu khi ra là `D=max(F−C,0)`.
- Một lần thanh toán online tạo khoản ghi có cho lượt, không xác nhận xe đã ra, không trả chỗ và không thay đổi giờ vào.
- `quoted_at` là thời điểm tính phí. `paid_through` là **cuối khối phí đã trả**: `billable_from + billable_blocks × (1 giờ hoặc 1 ngày)` từ `snapshot_basis`. Không cộng thêm 10 phút miễn phí.
- TTL của đề nghị thanh toán là 5 phút, độc lập với `paid_through`. Thanh toán đúng tiền trong TTL vẫn được ghi có nếu sang khối mới trong khi trả tiền; phần phát sinh được hiển thị để thu khi ra.
- Ví dụ: đơn giá 5.000đ/giờ, đã ở 1 giờ 10 phút thì F=10.000đ, C=0, đề nghị thu 10.000đ, `paid_through=giờ vào+2 giờ`. Ra trước hoặc tại mốc này không thu thêm. Ra muộn một microsecond thì F=15.000đ, C=10.000đ, D=5.000đ.
- Vé tháng chỉ miễn phí đến `monthly_coverage_end` đã chốt lúc vào. Vé giờ/ngày trả trước chỉ miễn phí đến `prepaid_end_at`. Ghi có online không gia hạn các quyền này.
- Lượt cũ chưa có `entry-v1`/`prepaid-window-v1` không được tự suy chính sách bất biến; luồng online trả 409 có hướng dẫn dùng thu tại bãi. Nghiệp vụ thu tại bãi hiện có vẫn hoạt động.
- Khoản phí bằng 0 không tạo QR. Không ghép tiền thiếu, nhiều giao dịch, tiền dư hoặc một tham chiếu mới sau khi đã phân bổ; chuyển sang đối soát như luồng payOS mua vé.

## Mô hình dữ liệu

### `SessionFeeQuote` — `session_fee_quotes`

| Trường | Kiểu / quy tắc |
|---|---|
| `id` | UUID, khóa chính |
| `session_id` | FK lượt gửi; có chỉ mục |
| `site_id` | FK bãi, bất biến |
| `created_by_id` | FK người tạo; tạo từ danh tính đã xác thực |
| `owner_customer_id` | FK khách hoặc NULL cho xe vãng lai; lấy từ dữ liệu xác nhận sở hữu, không nhận từ trình duyệt |
| `request_id` | Mã yêu cầu; unique theo người tạo và lượt; phát lại đúng nội dung, khác nội dung trả 409 |
| `session_state_hash` | SHA-256 của danh tính lượt, biển/loại xe, giờ vào, chỗ, snapshot bảng giá, quyền vé đã chốt |
| `credit_snapshot_hash` | SHA-256 của danh sách khoản ghi có đã phân bổ và tổng C, sắp xếp ổn định |
| `gross_fee` | F, số nguyên VND an toàn |
| `credited_amount` | C tại thời điểm tạo, số nguyên VND an toàn |
| `amount` | F−C, phải >0 |
| `quoted_at` | Giờ nghiệp vụ khi tính phí |
| `paid_through` | Cuối khối phí trong snapshot, không phải TTL |
| `expires_at` | `quoted_at + TTL`, mặc định 5 phút |
| `billing_basis` | Snapshot JSON các khối phí và xuất xứ, không nhận từ client |
| `status` | pending / fulfilled / cancelled / expired / review |
| `review_reason` | Mã lý do ổn định, nullable |

Toàn bộ trường giá, nguồn, thời gian và danh tính bất biến. Chỉ trạng thái được chuyển theo luật. Unique có điều kiện bảo đảm tối đa một đề nghị pending cho một lượt; không tạo đề nghị khác khi liên kết cũ còn có thể nhận tiền. Hủy phải xác minh trạng thái provider trước, không chỉ đổi trạng thái local.

### `SessionFeeCredit` — `session_fee_credits`

| Trường | Kiểu / quy tắc |
|---|---|
| `id` | UUID, khóa chính |
| `session_id` | FK lượt gửi |
| `quote_id` | FK đề nghị, unique: một đề nghị chỉ được phân bổ một lần |
| `amount` | Bằng đúng `quote.amount`, nguyên VND dương |
| `paid_through` | Bằng đúng `quote.paid_through` |
| `created_at` | Thời điểm phân bổ đã xác minh |
| `receipt_id` | Chứng từ `Payment` nguồn `session_credit`; chỉ được gắn một lần |

Không sửa/xóa/thay thế khoản ghi có. Dữ liệu và chứng từ được tạo trong cùng giao dịch. Trước phân bổ, tổng ghi có hiện tại phải bằng `quote.credited_amount`; tổng sau phân bổ phải bằng `quote.gross_fee`. Không chấp nhận hai đề nghị song song có cùng C cũ.

### Dùng chung mapping, inbox và quyết định đối soát

`OnlinePaymentLink` bổ sung `session_quote_id` FK unique; `order_id` chuyển nullable. CHECK bắt buộc đúng một trong `order_id` hoặc `session_quote_id`. Mapping cũ không đổi nguồn, mã số hay số tiền. Có đúng một mã provider cho mỗi đề nghị, lưu trước HTTP, không gửi lại POST create sau lỗi mơ hồ.

`OnlinePaymentInbox` và `OnlinePaymentProcessing` dùng lại. Dispatcher chọn đúng dịch vụ nguồn từ mapping; không gọi `portal_service.process_event` của DEMO. DB guard liên kết receipt mở thêm nhánh `session_credit`; vẫn đòi khớp tham chiếu, số tiền, bãi, tài khoản, VND và receipt thật. Quyết định hoàn ngoài hệ thống hiện có chỉ dành cho khoản chưa phân bổ; khoản đã tạo credit phải qua nghiệp vụ hoàn chứng từ.

## Sổ thu, xe ra và báo cáo

1. Khi payOS trả đúng tiền: tạo credit + `Payment(source_type='session_credit', source_id=credit.id, amount=credit.amount, method='transfer', collected_by_id=NULL, shift_id=NULL)`.
2. Khi nhân viên xác nhận xe ra: tính lại F, đọc C dưới khóa lượt, xác nhận token có đúng snapshot ghi có và D. Lưu `parking_fee=F` rồi ghi receipt nguồn `parking_session` bằng D.
3. **Khi C>0 và D=0 vẫn phải có receipt cân bằng 0đ nguồn `parking_session`**. Nó đánh dấu lượt đã đi qua sổ thu, tránh nhánh doanh thu dữ liệu cũ cộng lại F. Không gán tiền online vào ca thu của nhân viên.
4. Guard nguồn receipt `parking_session` kiểm tra `amount = parking_fee − SUM(credit.amount)`; không có credit thì giữ điều kiện cũ. Guard nguồn `session_credit` kiểm tra quote/credit đã được xác minh và liên kết đúng lượt.
5. Báo cáo xếp `session_credit` vào doanh thu gửi xe. Tổng thu là C+D=F, không cộng lại số danh nghĩa trong lượt đã có receipt. Bộ lọc bãi/ngày dựa trên `Payment.site_id/created_at` như hiện tại.
6. Phiếu thu online và phiếu tất toán cùng được hiển thị trong cổng khách hàng theo quyền sở hữu lượt; giao diện xe ra hiển thị tổng phí, đã trả online, còn thu và đã trả đến mốc nào.
7. Không hoàn credit khi lượt còn active. Sau xe ra, nếu được phép hoàn thì dùng receipt gốc và giới hạn hoàn hiện có; không sửa lịch sử F/C/D. Khoản online đến sau khi lượt đã thu tiền và kết thúc chuyển sang đối soát, không tạo credit tự động.

## Khóa và giao dịch

- Dựa trên thứ tự hiện có của CheckoutService/SessionExceptionService: người thao tác (nếu cần) → lượt gửi → đề nghị/mapping/processing → chứng từ. Không khóa chỗ trước rồi chờ lượt vì checkout hiện giữ lượt trước chỗ.
- Callback ghi có không thay đổi vị trí, vì vậy không cần khóa chỗ. Khóa lượt phải ngăn được callback và claim xe ra cùng thay đổi giá trị C.
- Sau khi chờ khóa, đọc lại danh tính/quyền sở hữu, snapshot giá, trạng thái active và danh sách ghi có. Không dựa vào dữ liệu ORM đã đọc trước khóa.
- Tạo mapping và lease rồi commit; HTTP thực hiện bên ngoài transaction. Khi có kết quả, lấy lại khóa và đối chiếu trạng thái nguồn.
- `CheckoutService.confirm` phải so snapshot ghi có **sau** khi claim lượt. Nếu một credit vừa đến, token cũ hết giá trị: yêu cầu xem lại số dư trước khi thu thêm.
- Lượt có credit hoặc liên kết online còn mở phải chặn nghiệp vụ hủy/sửa biển thay thế; không được xóa nguồn đã có tiền hoặc hủy cam kết nhận tiền âm thầm.

## API

| Nhóm | API |
|---|---|
| Khách đã có grant lượt | `POST /api/v2/me/sessions/{id}/payment-quote` với `request_id`; `GET .../payment-status` |
| Nhân viên đúng bãi | `POST /api/v2/sites/{site_id}/sessions/{id}/payment-quote`; `GET .../payment-status` |
| Đề nghị đã xác thực quyền nguồn | `GET/POST /api/v2/session-fee-quotes/{quote_id}/payment-link`; `POST .../refresh`; `POST .../cancel` |
| Webhook, worker, đối soát | Dùng chung `/api/v2/payments/payos/webhook`, worker payOS và API đối soát theo bãi |

DTO đề nghị gồm `id, session_id, gross_fee, online_paid, balance_due, quoted_at, paid_through, expires_at, server_now, status, billing_basis`. Mốc thời gian có offset +07. DTO liên kết giữ các trạng thái hiện có, thêm `session_id/quote_id`; không có `order_id` giả. Frontend chỉ đọc số tiền do server tính; redirect/QR/trạng thái do người dùng gửi không thể xác nhận thanh toán.

## Quyền sở hữu thay đổi và kiểm thử

- core_permissions: các module mới `session_payment_*`, tổng quát hóa module `online_payment_*`, test mới và hợp đồng API này.
- single_lot_demo: CheckoutService, PaymentService/model/guards, schema checkout, báo cáo nguồn thu, registry/rollout/migration và DB guard chung. Hai agent phối hợp trước khi sửa file giao nhau.
- Root: frontend, bằng chứng tổng hợp, tài liệu kế hoạch và shared memory.

Các ca bắt buộc: đúng biên giờ/ngày và +1 microsecond; tháng/trả trước hết hạn đúng snapshot; tiền đến khi bước sang khối mới; thu đủ online rồi D=0; trả online một phần F rồi thu tiền mặt phần tăng thêm; tài khoản/bãi/grant khác; token checkout cũ sau credit; webhook/callback/checkout đồng thời trên SQLite file; rollback receipt/credit; duplicate/new reference; trả trễ/thiếu/dư; receipt cân bằng 0 chống đếm doanh thu hai lần; hoàn tiền/chỉnh biển/hủy khi có credit; quyền nhân viên và dữ liệu AI không rò tổng doanh thu.

## Kiểm chứng backend ngày 15/09/2026

- Lệnh cuối chạy cùng `tests/test_payos_gateway.py`, `tests/test_online_payments.py`, `tests/test_online_payment_concurrency.py`, `tests/test_session_online_payments.py`, `tests/test_session_payment_concurrency.py`, `tests/test_session_payment_acceptance.py`: **223 passed**, 24,67 giây. Đây là một lệnh kiểm thử thực tế, không cộng các lần chạy trùng nhau.
- Chín ca chạy trên SQLite file và các kết nối độc lập kiểm hai worker chỉ ghi có một lần; thu tiền mặt thắng khi provider GET đang chờ; hai request chỉ tạo một đề nghị pending; tài khoản, grant, trạng thái user, membership, role hoặc bãi bị thu hồi trong HTTP tạo liên kết.
- Các nhánh tạo, kiểm tra và hủy liên kết đều đọc lại quyền sau HTTP, kể cả HTTP thất bại. Kết quả provider vẫn được lưu bền vững nhưng người mất quyền nhận 403/404, không nhận QR mới.
- Hai regression đã thấy lỗi trước sửa: xe đã ra hoặc bãi đóng trong HTTP tạo liên kết vẫn nhận QR. Sau sửa, DTO giữ trạng thái provider đã lưu nhưng ẩn QR, URL và quyền tạo khi nguồn không còn hợp lệ; thông báo yêu cầu không chuyển thêm tiền. Không giả rằng provider đã hủy liên kết.
- Inbox giữ mốc nhận bằng chứng có chữ ký sớm nhất khi cùng một giao dịch được thấy lại qua GET. Worker gặp lỗi mạng không vô tình dùng mốc GET muộn làm mất cửa sổ xử lý; bằng chứng chưa xử lý vẫn chặn đề nghị mới dù provider đã báo hủy hoặc hết hạn.
- Lượt đã hủy không tiếp tục tích lũy phí. Ghi có không cho xe ra tự động; chứng từ tất toán 0đ khi đã trả đủ tránh cộng doanh thu hai lần. Hoàn khoản ghi có bị chặn khi lượt còn active.
- Full P8, migration/recovery và kiểm tra giao diện được tổng hợp riêng bởi tác vụ chính. Các kiểm thử này không đo độ tin cậy mạng ngân hàng, thiết bị camera hoặc PostgreSQL đang chạy thật.
