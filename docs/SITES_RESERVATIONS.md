# Nhiều bãi, đặt chỗ và đội xe — bản đồ án

Module phục vụ một đơn vị quản lý nhiều bãi. Quản trị viên hệ thống nhìn toàn bộ; nhân viên/quản lý cần thành viên tại từng bãi. Đây không phải mô hình SaaS cách ly các pháp nhân: khách hàng, bảng giá, xe và sổ thu hiện vẫn dùng chung trong một đơn vị.

`expansion.site_router.router` có sẵn prefix `/api/v2`. Đăng ký `expansion.site_models` trước `Base.metadata.create_all`. Migration phải tạo các bảng mới và thêm `zones.site_id` nullable; dữ liệu khu cũ được gắn bãi mặc định. Khi có nhiều bãi, kể cả bãi đã ngừng hoạt động còn lịch sử, chặn API vận hành cũ với người dùng không phải global admin. Không chỉ ẩn menu frontend. Trường hợp chỉ còn một bãi cũng kiểm tra thành viên và quyền tại bãi trước khi cho phép dùng API cũ.

## Hợp đồng cho giao diện

Mọi request cần Bearer token. JSON thời gian nghiệp vụ bắt buộc có múi giờ;
`start_at`, `end_at`, giờ vào/ra và hạn đến được trả theo UTC+7. Metadata
`created_at`/`updated_at` do PostgreSQL/SQLite tạo bằng `CURRENT_TIMESTAMP` giữ
đúng offset UTC để trình duyệt quy đổi, không gắn nhầm UTC+7. Lỗi nghiệp vụ dùng
HTTP 403/404/409/422 và `detail` tiếng Việt. Các danh sách trả mảng, trừ
availability/fleet. Danh sách lịch sử mặc định tối đa 100 mục.

Khoảng lọc được chuẩn hóa múi giờ rồi kiểm tra; `to_at <= from_at` trả 422. Chuyển chủ xe không tự chuyển quyền bảo đảm chỗ: chỉ miễn xung đột khi cả xe và hồ sơ khách đều khớp. Quy tắc này áp dụng ở tạo đặt chỗ và nhận xe, kể cả đặt chỗ cũ đã tồn tại; cùng chủ vẫn dùng quyền đã cấp bình thường.

| API | Quyền / nội dung |
| --- | --- |
| GET `/sites` | Customer: danh mục bãi hoạt động; staff/manager: bãi được cấp quyền; admin: mọi bãi |
| POST `/sites` | Admin; `{ "name": "Bãi A", "address": "Địa chỉ" }` |
| GET `/sites/{site_id}/zones` | Nhân viên bãi; chỉ khu vực thuộc bãi |
| POST `/sites/{site_id}/zones` | Quản lý bãi; `{ "name": "Bãi A - Khu mới", "capacity": 20 }`; bãi được lấy từ URL |
| POST `/sites/{site_id}/slots` | Quản lý bãi; `{ "slot_name": "A-001", "zone_id": 3, "vehicle_type_id": 1 }`; kiểm tra khu thuộc bãi, loại xe hoạt động và sức chứa |
| GET `/sites/{site_id}/vehicles?q=51A&limit=20` | Nhân viên bãi; tìm xe đã gắn hồ sơ khách để đặt chỗ, chỉ trả mã xe, biển số, loại xe; không trả liên hệ hoặc lịch sử khách |
| GET `/sites/{site_id}/availability` | Customer được xem sức chứa công khai; nhân viên chỉ xem bãi của mình |
| GET/POST `/sites/{site_id}/members` | Đọc: quản lý bãi; cấp/cập nhật: admin; `{ "user_id": 7, "role": "staff" }` |
| GET `/sites/{site_id}/sessions?limit=100&offset=0` | Nhân viên bãi; mảng phiên có `license_plate`, `slot_name` và các cột phiên; lọc trước phân trang bằng `license_plate` chính xác và `status=active/completed` |
| POST `/sites/{site_id}/check-in` | Nhân viên bãi; `{ "license_plate": "51A12345", "vehicle_type_id": 1, "parking_slot_id": 2 }` |
| GET `/sites/{site_id}/sessions/{id}/checkout-quote` | Quote có chữ ký, không cache; cùng contract đã phát hành |
| PUT `/sites/{site_id}/sessions/{id}/check-out` | `{ "quote_token": "...", "payment_confirmed": true, "payment_method": "cash" }`; trả phiên |
| GET/POST `/me/reservations` | Khách đã xác minh liên kết và quyền xe. GET lọc tại server: `site_id`, `status`, `from_at`/`to_at` (giữ bản ghi giao với khoảng), `limit` 1..100 (mặc định 50), `offset`; sắp theo `start_at` giảm dần rồi `id` giảm dần |
| POST `/me/reservations/{id}/cancel` | Chủ đặt chỗ; body rỗng |
| GET/POST `/sites/{site_id}/reservations` | Nhân viên bãi; xe phải có khách hàng. GET lọc `status`, `vehicle_id`, `from_at`/`to_at`, `limit`/`offset`; cùng thứ tự ổn định như `/me/reservations` |
| POST `/sites/{site_id}/reservations/{id}/arrive` | Nhân viên xác nhận; thực hiện check-in và trả đặt chỗ có `session_id`; retry trả kết quả cũ |
| POST `/sites/{site_id}/reservations/{id}/cancel` | Nhân viên; không hủy được đặt chỗ đã đến |
| POST `/sites/{site_id}/reservations/expire` | Nhân viên; đánh dấu no-show, trả `{ "expired": 2 }`; gọi lặp an toàn |
| GET/POST `/sites/{site_id}/allocations` | Đọc: nhân viên; tạo: quản lý bãi; cùng body đặt chỗ nhưng bắt buộc `slot_id`. GET lọc `status` (`active`/`cancelled`), `vehicle_id`, `from_at`/`to_at`, `limit`/`offset` |
| POST `/sites/{site_id}/allocations/{id}/cancel` | Quản lý bãi; không thực hiện checkout hoặc hoàn tiền |
| GET/POST `/me/waitlist` | Khách; body như đặt chỗ nhưng không có `slot_id`. GET lọc `site_id`, `status` (`waiting`/`offered`/`cancelled`), `from_at`/`to_at`, `limit`/`offset`; mới nhất trước (`created_at`, `id` giảm dần) |
| GET/POST `/sites/{site_id}/waitlist` | Nhân viên; cùng body danh sách chờ. GET cùng bộ lọc nhưng theo thứ tự hàng đợi (`created_at`, `id` tăng dần) |
| POST `/sites/{site_id}/waitlist/{id}/offer` | Nhân viên; cấp một đặt chỗ nếu có vị trí; trả reservation; lặp trả đặt chỗ đã cấp |
| GET/POST `/sites/{site_id}/organizations` | Nhân viên đọc, quản lý tạo; `{ "name": "Đội xe ABC" }` |
| GET `/me/organizations` | Danh sách nhóm được cấp quyền xem |
| POST `/organizations/{id}/members` | Quản lý bãi; `{ "user_id": 9 }` |
| GET/POST `/organizations/{id}/fleet` | Thành viên nhóm/nhân viên bãi đọc; quản lý thêm `{ "vehicle_id": 3 }` |

Ví dụ đăng ký chỗ (`request_id` mới cho mỗi yêu cầu nghiệp vụ; giữ nguyên khi retry):

```json
{
  "site_id": 1,
  "vehicle_id": 3,
  "slot_id": 2,
  "start_at": "2026-09-08T09:00:00+07:00",
  "end_at": "2026-09-08T11:00:00+07:00",
  "request_id": "booking-request-0001"
}
```

`slot_id` có thể bỏ để hệ thống chọn. Các trường `customer_id`, `status`, `price`, `is_occupied` không được khách gửi. Phản hồi:

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "site_id": 1,
  "slot_id": 2,
  "customer_id": 5,
  "vehicle_id": 3,
  "start_at": "2026-09-08T09:00:00+07:00",
  "end_at": "2026-09-08T11:00:00+07:00",
  "arrival_deadline": "2026-09-08T09:15:00+07:00",
  "status": "confirmed",
  "request_id": "booking-request-0001",
  "session_id": null,
  "created_at": "2026-09-07T10:00:00+07:00"
}
```

Availability trả `{site_id,total,occupied,available_now,reserved_slots,slots:[{id,slot_name,zone_id,zone_name,vehicle_type_id,is_occupied,available_now,reserved}]}`. Không trả biển số hoặc danh tính người đang đỗ cho customer. `available_now` là khả năng nhận xe vãng lai không có giờ ra dự kiến; dùng API đặt chỗ để kiểm tra chính xác một khoảng giờ.

Danh sách `/sites` của nhân sự có trường `role` là quyền tại chính bãi đó (`staff`, `manager`, hoặc `admin`), để giao diện hiện đúng thao tác quản lý. Khách hàng không nhận trường quyền này. Việc kiểm tra quyền vẫn được thực hiện lại trong từng API. Tên khu vực và mã vị trí hiện duy nhất trong toàn đơn vị; nên thêm mã bãi vào tên để tránh trùng.

Fleet trả `{organization,vehicles:[{id,vehicle_id,license_plate,vehicle_type_id,joined_at}],total_sessions,active_sessions,completed_sessions,parking_fees,fee_note,limit,offset,sessions:[{id,vehicle_id,license_plate,slot_name,check_in_time,check_out_time,status,parking_fee}]}`. Mỗi phần tử `sessions` chỉ có đúng các trường trên (không có mã nhân viên, vé tháng, dữ liệu xác nhận thanh toán hay cột nội bộ khác). `sessions` sắp theo `check_in_time` giảm dần rồi `id` giảm dần, phân trang bằng `limit` (1..100, mặc định 50) và `offset` (>= 0); các tổng `total_sessions`/`active_sessions`/`completed_sessions`/`parking_fees` luôn tính trên toàn bộ phạm vi được phép, không phụ thuộc trang. `parking_fees` là tổng phí các phiên hoàn tất trong phạm vi đội xe, chưa trừ hoàn tiền và không gồm thanh toán vé tháng (chứng từ DEMO là chứng từ vé tháng, không xuất hiện ở đây); `fee_note` nhắc lại điều này cho giao diện. Chỉ bao gồm phiên bắt đầu sau khi xe tham gia nhóm và thuộc bãi của nhóm.

## Quy tắc nghiệp vụ

- Vé tháng miễn/điều chỉnh phí theo kỳ. Phân bổ bảo đảm chỗ là quyền sử dụng một vị trí trong khoảng giờ, không tự cấp vé tháng hoặc tạo chứng từ. Bản đồ án cấp phân bổ qua quản lý.
- Khoảng giữ chỗ là `[start_at, end_at)`, cho phép hai yêu cầu tiếp giáp. Tới hạn `min(start+15 phút, end)` mà chưa vào thì hết quyền đến; thao tác nghiệp vụ tự loại no-show khỏi khả năng giữ chỗ. API expire lưu trạng thái hết hạn rõ ràng và gọi lặp an toàn.
- Khách chỉ được đặt trước tối đa 30 ngày và có tối đa 5 đặt chỗ còn hiệu lực.
  Phân bổ do quản lý tạo không dùng hạn mức khách này.
- Mọi đặt chỗ/phân bổ và hai đường xe vào dùng thứ tự khóa `vehicle → slot`.
  Hai yêu cầu đồng thời không thể cùng giữ vị trí trong khoảng giao nhau hoặc
  giữ hai vị trí cho cùng một xe.
- Không thể ngừng khu hoặc vị trí khi còn đặt chỗ/phân bổ tương lai. API trả
  409 và trigger SQLite/PostgreSQL bảo vệ cả đường ghi ngoài API.
- Chỗ đang có xe không được bán cho thời điểm tương lai, vì chưa có giờ ra thực tế. Xe vãng lai cũng không được vào vị trí đã có cam kết tương lai: không giả định xe sẽ ra trước giờ khách đến. Chính sách này ưu tiên chắc chắn còn chỗ, có thể giảm khả năng khai thác trong bản đồ án.
- Xe đến theo đặt chỗ được vào trước yêu cầu sau. Nếu ở quá giờ, `is_occupied` và phiên đang hoạt động tiếp tục chặn xe mới; không giải phóng vị trí hoặc cho xe mới vào tự động. Nhân viên xử lý xung đột tại bãi, chọn chỗ thay thế hoặc hủy; không có cam kết giải quyết vật lý tự động.
- Nếu xe theo đặt chỗ ra sớm, vị trí hết trạng thái có xe nhưng đặt chỗ vẫn giữ quyền trong cửa sổ `[start_at, end_at)`. Vì vậy, chỗ trống vật lý chưa chắc nhận được xe vãng lai; hãy chọn vị trí có `available_now=true`. Một mã đặt chỗ chỉ ghi nhận một lần đến, không hỗ trợ xe quay lại bằng cùng mã. Chính sách trả lại phần thời gian còn dư hoặc nhiều lần vào/ra là hướng mở rộng sau.
- Arrive ghi phiên thật bằng luồng check-in hiện có, chụp quyền vé tháng và quyền truy cập lịch sử. Customer không được tự đổi trạng thái chỗ hoặc xác nhận xe đã đến.
- Danh sách chờ không chiếm sức chứa. Nhân viên offer tạo đặt chỗ thật trong
  giao dịch và tạo đúng một thông báo trong cổng khách với hạn đến; bản đồ án
  chưa gửi email/SMS tự động.
- Đội xe là nhóm phục vụ báo cáo/vận hành của cùng một đơn vị. Quyền xem được cấp bởi quản lý; không tự tuyên bố quyền sở hữu chỉ từ biển số, không chuyển lịch sử trước lúc tham gia nhóm.

Sau đợt kiểm chứng review ngày 07/09/2026, cấp chỗ từ danh sách chờ lấy một thời điểm ở server sau khi khóa yêu cầu và dùng xuyên suốt bước kiểm tra/tạo đặt chỗ. Nếu giờ bắt đầu đã qua, giờ bắt đầu mới là thời điểm đó; yêu cầu đã hết toàn bộ cửa sổ vẫn bị từ chối. Client không được gửi đồng hồ thay thế.

Xác nhận đến cũng dùng một thời điểm sau khi khóa vị trí để kiểm tra hạn đến, ghi giờ vào và liên kết phiên. Đúng hạn đến hoặc muộn hơn thì từ chối. Phiên, vị trí, quyền xem lịch sử và trạng thái đặt chỗ được ghi trong cùng giao dịch; nếu liên kết phiên thất bại thì tất cả được rollback. Phạm vi bãi được kiểm tra lại khi chiếm vị trí, ngăn nhận xe sai bãi khi cấu hình thay đổi đồng thời.

## Các điểm tích hợp

`expansion.site_scope.require_site_access(db,user,site_id,minimum_role='staff')`, `allowed_site_ids(db,user)` và `scoped_zone_ids(db,user)` dùng chung cho camera/portal. Customer xác minh bằng `expansion.portal_service.require_owned_vehicle`.

`crud.parking_session.claim_parking_slot` gọi `reservations.admission_allowed` trước conditional UPDATE trong cùng giao dịch. Sau flush phiên, cả hai luồng check-in gọi `record_admission` và `capture_session_ownership` trước commit. Checkout tiếp tục dùng dịch vụ quote/xác nhận hiện có.

Khi đã có ít nhất một bãi trong dữ liệu, API v1 nhận xe yêu cầu `parking_slot_id` (thiếu trả HTTP 422); dùng màn hình **Vận hành bãi** để chọn bãi/vị trí. Database cũ chưa có bãi vẫn giữ luồng tương thích. API tạo khu cũ tự gắn bãi nếu chỉ có một bãi; khi có nhiều bãi, kể cả bãi đã đóng, trả HTTP 409 và yêu cầu tạo khu trong cấu hình bãi cụ thể.

## Luồng trình diễn trên giao diện

- Quản trị viên mở **Vận hành bãi** (`/sites`), tạo bãi; chọn **Cấu hình bãi** để thêm khu vực, vị trí và cấp quyền cho tài khoản nhân sự. Quản lý bãi có thể thêm khu/vị trí và xem phân công; quyền nhân sự do quản trị viên cấp.
- **Xe vào / ra** chọn loại xe và vị trí còn nhận xe; tra cứu biển số chính xác để mở hộp xem phí và xác nhận thu tiền. Checkout dùng cùng chữ ký, hạn hiệu lực và cơ chế thử lại yêu cầu đã gửi như luồng hiện có.
- **Đặt chỗ**, **Bảo đảm chỗ**, **Danh sách chờ** dùng ô tìm biển số của xe đã đăng ký khách hàng. Mỗi yêu cầu có mã chống gửi lặp. Nếu mạng gián đoạn, kiểm tra lịch trước khi chọn **Nhập yêu cầu mới**.
- Khách mở **Đặt chỗ của tôi** (`/reservations`), chọn bãi và xe đã duyệt. Khách được hủy đặt chỗ hoặc rời danh sách chờ của mình; không tự xác nhận xe đến.
- **Đội xe** hiển thị nhóm và lịch sử trong phạm vi đã cấp quyền. Quản lý thêm xe bằng ô tìm biển số; cấp/thu hồi quyền xem bằng mã tài khoản. Đây là báo cáo lượt gửi của nhóm, không phải công nợ doanh nghiệp.
- Sau khi nhân viên xác nhận ảnh tại `/vision`, trang bãi chỉ điền sẵn biển số và chế độ tìm xe vào/ra. Người dùng kiểm tra rồi mới xác nhận nghiệp vụ.
