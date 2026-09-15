# P4 — Vé giờ/ngày, giữ chỗ và quyền gửi trả trước

Ngày chốt thiết kế: 15/09/2026. Phạm vi: một bãi cho đồ án, tiếp nối [PROPOSAL.md](PROPOSAL.md) và [EXTENSION_PLAN.md](EXTENSION_PLAN.md).

**Trạng thái tài liệu:** hợp đồng triển khai đã được chấp thuận; chưa phải bằng chứng tính năng P4 đã hoạt động. Backend đang giữ nguyên trong khi bộ kiểm thử P1 chạy. Không kết nối provider hoặc giao dịch ngân hàng thật trong P4.

## 1. Các khái niệm và chính sách sản phẩm

| Khái niệm | Ý nghĩa và giới hạn |
|---|---|
| Gói vé (`SubscriptionPlan`) | Danh mục sản phẩm; thay đổi gói chỉ tác động đơn tạo sau đó. |
| Đơn mua (`PortalOrder`) | Giá, xe, chủ mua, bãi và quyền sử dụng đã chốt trước thanh toán. Một đơn giờ/ngày gồm cả quyền gửi và đặt chỗ, không cộng phí đặt chỗ riêng. |
| Giữ chỗ tạm (`ParkingCapacityHold`) | Cam kết sức chứa có hạn cho đơn chưa hoàn tất. Chưa phải đặt chỗ đã xác nhận và không cho xe vào miễn phí. |
| Đặt chỗ (`ParkingReservation`) | Cam kết đã xác nhận trong khoảng thời gian; vẫn chưa phải xe đang trong bãi. |
| Vé giờ/ngày (`TimedParkingPass`) | Quyền đã cấp cho đúng xe/chủ/bãi; chỉ sử dụng cho một lượt liên tục. |
| Lượt gửi (`ParkingSession`) | Xe thực sự vào/ra; quyết định trạng thái chiếm ô và phí phụ trội. |
| Chứng từ (`Payment`) | Khoản thu/hoàn đã xác nhận, bất biến. Đã nhận tiền và đã cấp quyền là hai sự kiện cần kiểm tra riêng. |

- `monthly`: giữ kỳ ngày hiện có, nhiều lượt, không tự giữ ô cố định. Gói 30 ngày vẫn ghi đúng 30 ngày.
- `hourly`: thời lượng nguyên giờ của gói, một lượt trong cửa sổ cố định đã chọn; giới hạn đầu tiên 1–24 giờ.
- `daily`: một lượt trong 24 giờ từ `start_at` đã công bố.
- Với giờ/ngày, server tính `end_at = start_at + duration_minutes`. Khách không gửi số tiền hoặc giờ kết thúc tùy ý.
- Đến muộn không dịch giờ kết thúc. Ví dụ gói 10:00–12:00, xe đến 10:10 vẫn được bao phủ đến 12:00.
- Khoảng đặt là `[start_at, end_at)`. Hạn đến là `min(start_at + 15 phút, end_at)` và không nhận xe tại đúng hạn cuối.
- P4 không kết hợp ngầm vé tháng và vé giờ/ngày để tính một lượt. Khi nhận đúng đặt chỗ giờ/ngày đã thanh toán, lượt dùng quyền và chính sách phụ trội của đơn đó; màn hình phải nói rõ gói được áp dụng. Gói bảo đảm chỗ riêng cho người có vé tháng chưa nằm trong hợp đồng này.
- Giờ nghiệp vụ dùng `Asia/Ho_Chi_Minh`. API nhận datetime có offset, chuẩn hóa bằng cơ chế thời gian hiện có. Mốc quyết định hạn được lấy sau khi có đủ khóa liên quan; không dùng giờ đã chốt trước một lần chờ khóa lâu. Replay đã thành công trả kết quả cũ trước kiểm thời hạn mới.

## 2. Schema dự kiến

| Model | Thay đổi |
|---|---|
| `SubscriptionPlan` | Thêm `product_kind: monthly\|hourly\|daily`, `duration_minutes` nullable; cho `duration_days` nullable theo loại. CHECK tháng yêu cầu 1–366 ngày và không có phút; giờ yêu cầu 60–1.440 phút, chia hết cho 60; ngày yêu cầu 1.440 phút. Giá vẫn nguyên VND dương trong giới hạn chính xác. |
| `PortalOrder` | Chốt loại/tên gói, thời lượng, cửa sổ gửi, khu yêu cầu, giá và năm giá trị nguồn giá phụ trội. Giữ `start_date/end_date` cho tháng; thêm `start_at/end_at` cho giờ/ngày. Thêm `timed_pass_id` nullable/unique; CHECK trạng thái hoàn tất yêu cầu chứng từ và đúng một loại quyền. |
| `ParkingCapacityHold` mới | UUID; `order_id UNIQUE`; site/slot/customer/vehicle; `start_at/end_at`; `expires_at`; `held\|converted\|released\|expired`; `reservation_id` nullable/unique; thời điểm tạo. Danh tính, khoảng giữ và hạn giữ bất biến. Chỉ `held` được chuyển sang trạng thái kết thúc. |
| `TimedParkingPass` mới | UUID; `order_id UNIQUE`; site/customer/vehicle và loại xe; `reservation_id UNIQUE`; cửa sổ sử dụng/hạn đến; giá và chính sách phụ trội đã chốt; `ready\|consumed\|expired\|revoked`; `session_id` nullable/unique. Quyền đã dùng không trở lại `ready`. |
| `ParkingReservation` | Giữ bộ trạng thái `confirmed/arrived/cancelled/expired`; thêm `order_id` nullable/unique và bất biến cho đặt chỗ thuộc đơn trả trước. Không nhét hold chưa trả tiền vào `confirmed`. |
| `ParkingSite` | Thêm `customer_booking_mode: legacy\|paid_packages`, default/migration `legacy` để giữ hành vi cũ. Fresh seed một bãi dùng `paid_packages`. |
| `ParkingSession` | Thêm nullable `timed_pass_id UNIQUE`, `prepaid_start_at`, `prepaid_end_at`; hỗ trợ policy `prepaid-window-v1`. Năm trường giá hiện có lấy từ quyền đã mua thay vì bảng giá tại lúc vào. Snapshot mới được bảo vệ như P1, kể cả chống UPDATE/REPLACE/DELETE. |
| `Payment` | Thêm nguồn `portal_order` cho đơn giờ/ngày. Giữ nguồn `monthly_pass` cho vé tháng và `parking_session` cho phí khi ra. Không tạo một hệ thống thu tiền song song. |

Giá phụ trội trên đơn gồm phiên bản tính phí, `rate_config_id`, `rate_ticket_type`, `rate_unit_price`, `rate_effective_date`. Đây là bản sao dùng để tính tiền; sửa hoặc xóa cấu hình nguồn không làm đổi đơn đã chốt.

Các liên kết order–hold–reservation–pass–session phải đồng nhất xe, chủ, bãi, chỗ và cửa sổ. UNIQUE chống cấp quyền/lượt/chứng từ lặp; trigger kiểm tra tham chiếu và chuyển trạng thái. Không xóa các bản ghi đã có giao dịch hoặc sử dụng.

Không suy diễn tên gói hoặc giá phụ trội lịch sử từ cấu hình hiện tại. Đơn cũ theo hợp đồng tháng được nhận diện `monthly`; những thông tin chưa từng được chốt giữ NULL. Dữ liệu session P1 và legacy giữ nguyên phiên bản, giá trị và chứng từ cũ.

## 3. Tạo đơn và giữ sức chứa

`POST /api/v2/me/orders` tiếp tục là điểm tạo đơn chung. Body giờ/ngày gồm:

```json
{
  "plan_id": 123,
  "vehicle_id": 456,
  "start_at": "2026-09-20T10:00:00+07:00",
  "zone_id": 7,
  "idempotency_key": "client-generated-request-key",
  "payment_mode": "demo"
}
```

`zone_id` tùy chọn; server gán một ô phù hợp. `product_kind`, giá, thời lượng, quyền sở hữu, trạng thái và giờ kết thúc không do khách quyết định. Đơn tháng giữ body hiện có, không yêu cầu giờ/khu.

Luồng ghi:

1. Kiểm liên kết tài khoản và quyền sở hữu xe đã xác minh; không nhận quyền chỉ từ biển số.
2. Khóa dữ liệu liên quan, làm mới quyền xe/loại xe, đọc gói và giá phụ trội hợp lệ. Lấy shared lock loại xe và giá như P1; thao tác sửa giá dùng cùng thứ tự khóa, không chốt giá từ cache cũ.
3. Kiểm khóa idempotency trước khi cấp thêm tài nguyên. Cùng khóa nhưng khác gói, xe, giờ, khu hoặc phương thức trả 409.
4. Server tính cửa sổ và hạn đến; kiểm horizon tối đa 30 ngày và giới hạn tối đa 5 cam kết đang hiệu lực mỗi khách, tính cả hold.
5. Khóa ô ứng viên, xử lý hold/đặt chỗ hết hạn và kiểm lại sức chứa. Tạo đơn + hold cùng transaction.

Hold mặc định 10 phút, giới hạn bởi hạn đến: `expires_at = min(now + hold_ttl, arrival_deadline)`. Link/mã thanh toán không dài hơn hold. Khi `now >= expires_at`, hold không còn hiệu lực.

Sức chứa phải tính cùng lúc: xe đang chiếm ô, reservation, guaranteed allocation và hold còn hạn. Xe vãng lai không biết giờ ra bị chặn nếu ô có cam kết tương lai; không giả định xe đó sẽ tự rời bãi. Khách không xem được biển/chủ của cam kết khác.

Không dựa vào worker để bảo đảm hết hạn: các query availability chỉ tính hold còn hạn; mỗi thao tác ghi khóa ô rồi kiểm/expire lại. Worker chỉ hoàn thiện trạng thái, thông báo và phục hồi công việc tồn đọng.

### Không đi vòng qua đặt chỗ miễn phí

Khi bãi ở `paid_packages`, khách vãng lai tạo đặt chỗ mới qua đơn giờ/ngày. `POST /me/reservations` và nhánh khách hàng của waitlist không được tự cấp reservation confirmed để bỏ qua đơn. Service trả 409 với hướng dẫn mở luồng mua gói; không chỉ ẩn form trên UI.

Ngoại lệ chỉ khi DB chứng minh khách/xe có `GuaranteedAllocation` còn hiệu lực, bao trùm đúng khoảng và đúng chỗ. Vé tháng thông thường không đủ điều kiện ngoại lệ. Luồng staff/manager có quyền, dữ liệu reservation đã tồn tại, lịch sử và hủy reservation legacy được giữ nguyên. Bãi `legacy` giữ hành vi trước nâng cấp.

Guard reservation mới phân biệt thao tác staff/manager, quyền guaranteed hợp lệ và conversion từ order có chứng từ + hold hợp lệ. `order_id` chỉ được gán bởi service conversion, không nhận từ body đặt chỗ độc lập. Khi loại trừ hold của chính đơn khỏi kiểm tra trùng, vẫn phải kiểm liên kết/tiền/xe/chỗ/cửa sổ; không bỏ qua mọi hold của cùng chủ.

## 4. Nhận tiền và cấp quyền

Dùng lại `PaymentService`, `PortalPaymentEvent`, gateway giả lập và luồng thu tại quầy. P4 giữ phân quyền thu/xét duyệt hiện có; staff tiếp nhận xe theo reservation, manager quản lý gói/đối soát/hoàn theo quyền bãi.

- Event đã xác nhận được ghi bền trước khi xử lý cấp quyền; unique provider/reference và kiểm nội dung chống phát lại khác đơn/kết quả/số tiền.
- Tiền phải đúng đơn, số tiền và phương thức. QR/redirect/nút của khách không phải bằng chứng nhận tiền thật.
- Khi hold còn hợp lệ, dưới cùng khóa ô: chuyển hold thành `converted`, tạo reservation `confirmed`, cấp `TimedParkingPass ready`, ghi receipt nguồn `portal_order`, gắn chứng từ/quyền vào đơn và chuyển `fulfilled` trong một transaction nghiệp vụ.
- `Payment.source_type='portal_order'` tham chiếu đơn và số tiền đã chốt; không yêu cầu đã có session. Khoản thu có thể tồn tại khi đơn cần đối soát nhưng quyền chưa cấp.
- Event thành công đến trễ, xử lý lại sau khi hold đã mất, sai quyền xe hoặc mất điều kiện cấp chỗ: ghi nhận sự kiện tiền và chuyển `review`; không tự lấy lại ô đã giải phóng. Một event đúng hạn nhưng worker xử lý muộn cũng không được vượt kiểm tra sức chứa hiện tại.
- Retry cùng xác nhận trả cùng đơn/quyền/chứng từ. Một thành công khác sau khi đơn đã thu không cấp thêm vé; giữ event để đối soát, không bỏ mất dấu vết khoản nhận thêm.
- Thu tại quầy kiểm hạn và sức chứa dưới khóa trước khi chấp nhận xác nhận. Nếu đã có bằng chứng nhận tiền mà không cấp quyền được, đi vào đối soát thay vì xóa bằng chứng hoặc giả vờ hoàn tiền.

Hủy đơn pending chưa có kết quả nhận tiền giải phóng hold cùng transaction. Đơn đã có tiền dùng quy trình xử lý/hoàn có lưu vết. P4 duy trì hoàn mô phỏng; tích hợp trả tiền qua ngân hàng là P5, không suy ra từ trạng thái `cancelled` hoặc một click phê duyệt.

## 5. Từ vé đã trả tiền đến lượt vào

Resolver quyền giờ/ngày phải được gọi trước INSERT session tại mọi đường nhận xe: legacy theo ID, biển số, scoped, reservation và vision. Không chỉ thêm một endpoint riêng cho vé mới.

Điều kiện nhận: đơn có chứng từ hợp lệ; vé `ready`; reservation `confirmed`; đúng xe/chủ/bãi/chỗ; loại/khu/ô hoạt động; `start_at <= now < arrival_deadline`; chưa có lượt active/checking_out; xe trước đã ra thực tế.

Resolver khóa và chốt quyền trước INSERT. Session, đánh dấu vé `consumed`, reservation `arrived`, chiếm ô và `PortalSessionGrant` cùng commit hoặc rollback. Unique `ParkingSession.timed_pass_id` chặn dùng lại kể cả lượt trước đã completed. Retry arrival đã thành công trả cùng session; retry thông thường của check-in vẫn giữ hợp đồng chống trùng hiện có.

Khi có reservation giờ/ngày phù hợp tại thời điểm vào, phải nhận đúng ô và áp dụng đúng vé. Không được nhận vào ô khác rồi để quyền mua tiếp tục ở trạng thái chưa dùng. Quyền đã mua không tự tạo xe đang trong bãi và không tự mở barrier.

Đổi chủ xe không chuyển đơn/vé sang người mới. Trước nhận xe phải kiểm lại chủ hiện tại và quyền đã chốt; sai khác yêu cầu xử lý, không cấp ngầm quyền lịch sử.

## 6. Phí khi ra và lịch sử

Ví dụ đơn 10:00–12:00 đã trả 30.000đ, phụ trội 10.000đ/giờ: vào 10:10, ra 11:50 thu thêm 0đ; ra 12:30 thu thêm 10.000đ. Đổi bảng giá sau khi mua không đổi hai kết quả này.

```text
billable_from = max(check_in_time, prepaid_end_at)
billable_seconds = ceil(max(0, check_out_time - billable_from), đơn vị giây)
billable_blocks = ceil(billable_seconds / số giây mỗi đơn vị phụ trội)
parking_fee = billable_blocks × rate_unit_price_đã_chốt
```

Dùng số nguyên microsecond như P1, không dùng float để quyết định biên. Đúng cuối gói thu 0; vượt một microsecond bắt đầu đơn vị phụ trội thứ nhất. Tiền phải nằm trong giới hạn VND chính xác.

`parking_fee` trên session là khoản phát sinh lúc ra; khoản đã mua nằm ở receipt của order. Không trừ giá gói khỏi một lần tính lại toàn bộ lượt. Quote 120 giây, xác nhận nhân viên, thanh toán/ra xe atomic và replay giữ nguyên cơ chế P1.

Policy và snapshot prepaid được ký trong quote, được giữ khi session completed và dùng để giải thích lịch sử. Không đọc lại đơn giá hiện tại để dựng hóa đơn cũ.

## 7. Hết hạn, no-show, quá giờ và hoàn

- Pending hết hold: order expired, hold expired; không cấp vé và không có reservation confirmed mới.
- Đã trả tiền nhưng không tới trước hạn: reservation expired/no-show, vé chưa dùng expired; receipt và đơn giữ lại. Không tự hoàn tiền.
- Xe đã vào: không expire session, không trả ô về trống, kể cả quá `end_at`. Reservation kế tiếp chỉ được nhận khi xe trước đã checkout thực tế; xung đột phải hiển thị cho nhân viên.
- Yêu cầu hoàn phần chưa dùng trước giờ hẹn được xét theo quyền manager. Khi duyệt hợp lệ: revoke vé chưa dùng, hủy reservation và tạo chứng từ hoàn; không sửa receipt gốc. Vé đã dùng không được hồi sinh để sử dụng lần hai.
- API hủy reservation độc lập trả 409 nếu có `order_id`; UI mở đơn để xử lý quyền và tiền cùng luồng. Không hủy riêng chỗ mà vẫn để vé giờ/ngày ở trạng thái dùng được.
- Hủy/hoàn và nhận xe phải tranh cùng khóa và chỉ một kết quả được commit. Các nghiệp vụ hủy/sửa biển P1 phải nhận diện ràng buộc vé trả trước, không xóa hoặc chuyển quyền đã mua bằng luồng sửa xe vãng lai.

## 8. Hợp đồng DTO với frontend

`GET /api/v2/plans` thêm `product_kind`, `duration_minutes`, `duration_days`, `customer_booking_mode` của bãi và `eligible_zones: [{id,name}]`. Giờ/ngày chỉ liệt kê khu có loại ô hoạt động phù hợp tại đúng bãi; tháng trả mảng rỗng. Dùng query theo nhóm, không mở API zones dành cho staff cho khách hàng.

DTO order giữ các trường cũ, bổ sung:

| Trường | Nội dung |
|---|---|
| `product_kind`, `plan_name` | Loại và tên đã chốt. Tên lịch sử không biết là NULL, UI có thể dùng mã gói. |
| `duration_minutes`, `duration_days` | Thời lượng đúng loại sản phẩm. |
| `start_at`, `end_at` | Cửa sổ giờ/ngày có offset; NULL cho tháng. Tháng giữ `start_date/end_date`. |
| `hold_expires_at`, `arrival_deadline` | Hai hạn khác nhau, có offset; NULL khi không áp dụng. |
| `reservation_id`, `timed_pass_id`, `entitlement_status` | Liên kết và trạng thái quyền; không dùng `order.status` một mình để suy ra được vào bãi. |
| `slot` | `{id,name,zone_id,zone_name}` hoặc NULL; chỉ thông tin chỗ của chính khách. |
| `overstay_basis` | `{policy_version:'prepaid-window-v1',rate_id,ticket_type,unit_price,effective_date}` hoặc NULL. |
| `allowed_actions` | Mảng con của `cancel`, `simulate`, `request_refund` dành cho chủ đơn. Collect/review thuộc API quản trị riêng. Chỉ giúp UI; service vẫn kiểm lại toàn bộ điều kiện. |
| `server_now` | Giờ server để hiển thị thời gian còn lại. UI không tự đổi trạng thái nghiệp vụ khi đồng hồ đếm hết. |

Thêm `GET /api/v2/me/timed-passes`; giữ `/me/passes` cho vé tháng. Mỗi quyền giờ/ngày trả mã, đơn, xe, bãi/chỗ, cửa sổ, hạn đến, `status: ready|consumed|expired|revoked`, snapshot prepaid/phụ trội, `server_now` và `session_id` nếu đã dùng. DTO reservation trả `order_id` nullable để UI mở đơn thay vì hủy riêng. Bộ lọc dựa trên tài khoản + customer đã xác minh; biết UUID không đủ để đọc hoặc sử dụng.

Quote và lịch sử session thêm:

```text
prepaid: null | {
  order_id, timed_pass_id, amount, start_at, end_at, payment_mode, receipt_id
}
```

`parking_fee` tiếp tục là số cần thu khi ra. `billing_basis.policy_version` hỗ trợ thêm `prepaid-window-v1`, đi cùng `rate_source='prepaid_snapshot'` để phân biệt giá phụ trội chốt lúc mua với `entry_snapshot` P1; `billable_from` thể hiện mốc bắt đầu tính phụ trội. UI hiển thị riêng giá gói đã trả và phí phát sinh, luôn giữ nhãn DEMO khi phương thức mô phỏng. Các list dùng join/batch để không truy vấn thêm từng hàng.

Receipt/PDF của nguồn `portal_order` phải kiểm cả `PortalOrder.user_id` và `customer_id`, không chỉ vehicle_id hoặc quan hệ chủ xe hiện tại. Không thay đổi quyền xem chứng từ tháng/lượt cũ.

## 9. Khóa, bất biến và migration

Các luồng giờ/ngày dùng thứ tự khóa chung: người thu/chủ tài khoản theo thứ tự ổn định → xe → loại xe → ô → đơn → quyền. Tái kiểm quyền sau khi chờ khóa. Expiry chỉ dùng phần tài nguyên cần thiết, không giữ khóa ô rồi đi ngược lại lấy khóa xe/loại.

Không gọi nguyên `_lock_order_context()` đang lấy order trước rồi mới khóa ô. Điều chỉnh nhánh giờ/ngày và `reservations.arrive()` để thống nhất với resolver. SQLite có write serialization; PostgreSQL phải được kiểm cả thứ tự lock và transaction retry, không dựa vào việc SQLite đã chạy tốt.

Bất biến cần guard/check/index ở DB:

- Snapshot đơn/quyền/session bất biến; không nhận giá hoặc quyền tự khai từ client.
- Một hold cho một order, một timed pass cho một order, một session cho một timed pass, một receipt nguồn cho một order.
- Chuyển hold thành reservation chỉ một lần, đúng chủ/xe/bãi/ô/khoảng thời gian.
- Session không thể sử dụng quyền chưa thanh toán, khác chủ, ngoài cửa sổ hoặc đã tiêu thụ.
- Cùng slot không có hai cam kết chồng nhau; reservation/allocation và các đường ghi ngoài API cũng phải xét hold.
- Không xóa chứng từ, quyền đã dùng hoặc lịch sử liên quan; ngừng khu/ô/loại phải xét hold còn hiệu lực cùng các cam kết hiện có.

SQLite: tạo hai bảng mới; rebuild đúng CHECK đã biết của plans/orders/payments trên candidate, bảo toàn dòng/cột, FK, index và trigger ngoài phạm vi. Dùng quy trình copy/kiểm chứng hiện có, không ghi `sqlite_master`. Định nghĩa lạ hoặc dữ liệu không tương thích phải từ chối trước khi công bố bản sao.

PostgreSQL: revision mới sau head P1, thay CHECK/guard và thêm cột/bảng rõ ràng. Readiness kiểm schema và bất biến mới. Không áp migration lên DB canonical trong lúc đang phát triển.

Không backfill timed pass/hold/session prepaid cho dữ liệu cũ. So sánh mọi giá trị lịch sử/receipt trước–sau, kiểm idempotence và các backfill legacy được mô tả riêng. Rollback ứng dụng phải dùng bản vẫn hiểu quyền trả trước; không quay về bản tính toàn bộ thời gian và bỏ qua tiền gói đã nhận.

## 10. Các điểm sửa mã và kiểm chứng

| Phần | Files dự kiến |
|---|---|
| Danh mục, đơn, quyền khách | `expansion/portal_models.py`, `portal_schemas.py`, `portal_service.py`, `portal_router.py` |
| Hold và vé giờ/ngày | Module mới `expansion/timed_parking_models.py`, `timed_parking_service.py`, `timed_parking_guards.py`; tích hợp `reservations.py`, `site_models.py` |
| Nhận/trả xe và phí | `crud/parking_session.py`, `services/parking_service.py`, `checkout_service.py`, `core/billing.py`, `billing_guards.py`, session/checkout schemas |
| Tiền và phân quyền chứng từ | `models/payment.py`, `services/payment_service.py`, `schemas/payment.py`, `site_finance_guards.py`, `expansion_demo_guards.py`, `finance_rollout.py`, receipt/PDF routes |
| Hết hạn/phục hồi | `expansion/portal_worker.py`, dùng cùng service transaction như HTTP |
| Thống kê và AI | `PaymentService.revenue_breakdown`, `expansion/site_analytics.py` và DTO liên quan: thêm doanh thu vé trả trước, giữ riêng phụ trội và vé tháng. Không để nhánh `else` hiện có phân loại mọi nguồn mới thành vé tháng. |
| Rollout | Models registry, SQLite candidate migration, Alembic, `db_rollout.py`, `postgres_readiness.py` và regression tests |

Test bắt buộc:

1. Catalog/create-order tháng, giờ, ngày; giá/thời lượng do server; đổi plan/tariff không đổi đơn cũ; sai/thiếu datetime, khu không phù hợp, loại bị ngừng.
2. Hai khách tranh ô cuối; hold đối đầu walk-in, allocation, reservation; khoảng chạm biên; expiry đúng microsecond; chờ khóa qua hạn; replay thành công sau hạn; đồng hồ client sai không cấp quyền.
3. Giữ chỗ/thu tiền/hủy/worker chạy đồng thời; event lặp, khác nội dung, trễ, hai reference thành công; crash sau durable inbox và retry không cấp/thu lặp.
4. Paid-to-arrival qua tất cả đường vào; đúng/khác chỗ, chưa đến giờ, no-show, đổi chủ, xe đang active, retry và dùng vé lần hai sau completed.
5. Phí trong gói 0, quá giờ/ngày, vượt một microsecond, đổi/xóa bảng giá, hết hạn quote và replay; receipt gói + phụ trội không đếm đôi doanh thu/AI/ca.
6. Xe quá giờ không giải phóng ô; reservation tiếp theo bị chặn khi xe trước chưa ra; hủy/hoàn tranh với admission không tạo quyền đã hoàn mà vẫn dùng được.
7. Khách khác không xem/sửa/dùng order, hold, pass, reservation, session, receipt/PDF; quyền tài khoản và membership hiện tại luôn được xét. Bãi paid_packages chặn API đặt chỗ/waitlist miễn phí, vẫn cho guaranteed hợp lệ và manager; hủy lẻ reservation thuộc đơn bị chặn.
8. Migration giữ dữ liệu P1/legacy, CHECK lạ bị từ chối, chạy lại không tăng chứng từ/quyền; SQLite concurrency thật; PostgreSQL offline contract và integration riêng nếu có DB thử.
9. Chạy lại hồi quy lõi F01–F13 và UAT khách–nhân viên–quản lý. Chỉ cập nhật trạng thái hoàn tất khi có kết quả thực chạy.

## 11. Phân công trong task hiện tại

- Subagent billing: toàn backend P4 và tests sau khi root mở freeze; trước đó chỉ tài liệu này.
- Subagent frontend: UI portal/gói/giữ chỗ/quyền và trình bày phí theo DTO; chưa ghi mã khi freeze còn hiệu lực.
- Root: nghiệm thu HTTP/UI/migration, tài liệu tổng và shared memory; điều phối khi có file giao nhau.

Không mở provider thật, không gửi tiền, không deploy hoặc commit trong giai đoạn này. Tài liệu này là hợp đồng thực hiện P4; QR provider, hóa đơn mở rộng và đối soát ngân hàng tiếp tục theo P5.
