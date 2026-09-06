# Xem phí và xác nhận thu tiền khi xe ra

Luồng xe ra gồm hai bước: xem báo phí và xác nhận hoàn tất. Nhân viên có thể
mở từ danh sách lượt gửi hoặc từ vé QR. Cả hai dùng cùng một quy trình.

## Thao tác tại bãi

1. Chọn lượt gửi cần cho xe ra. Kiểm tra biển số, giờ vào, thời gian gửi,
   vị trí và thông tin quyền lợi vé tháng trong hộp thoại.
2. Đọc số tiền phải thu do máy chủ tính. Việc mở báo phí hoặc bấm Hủy chưa
   đóng lượt gửi, chưa trả chỗ và chưa ghi phiếu thu.
3. Nếu có phí, chọn Tiền mặt hoặc Chuyển khoản. Chỉ xác nhận đã thu sau khi
   nhận đủ tiền; với chuyển khoản, kiểm tra giao dịch đã nhận theo quy trình
   của bãi. Đây là xác nhận thủ công của nhân viên, chưa phải tích hợp cổng
   thanh toán online.
4. Xác nhận thu tiền và cho xe ra. Hệ thống ghi nhân viên xử lý, giờ ra,
   số tiền, phương thức thu và phiếu thu trong cùng giao dịch với việc trả chỗ.
5. Nếu số tiền bằng 0, dùng xác nhận xe ra miễn phí. Hệ thống lưu việc hoàn
   tất lượt gửi và không tạo phiếu thu tiền mặt 0 đồng mới.

Báo phí có hiệu lực tối đa 120 giây. Khi hết hạn hoặc phí thay đổi do qua
mốc tính giờ/ngày, tải báo phí mới, đọc số tiền và xác nhận lại. Báo phí không
giữ nguyên mức phí qua mốc tính tiền: máy chủ kiểm tra phí tại thời điểm
xác nhận.

## Khi mất mạng hoặc có thao tác đồng thời

Nếu yêu cầu xác nhận bị mất phản hồi, chưa thể kết luận giao dịch thất bại.
Giữ nguyên nội dung và thử lại yêu cầu đã gửi để kiểm tra kết quả; không thu
khách lần thứ hai. Yêu cầu lặp đúng báo phí và phương thức trả lại kết quả đã
lưu, kể cả báo phí hết hạn sau lần xử lý đầu tiên.

Nếu một nhân viên khác đã hoàn tất cùng lượt gửi, tải lại lịch sử và kiểm tra
phiếu thu, người xử lý trước khi tiếp tục. Hệ thống không ghi thêm phiếu thu
cho cùng lượt gửi. Báo phí của tài khoản khác hoặc của lượt gửi khác không
được dùng để xác nhận.

Giao dịch bị từ chối do báo phí hết hạn/thay đổi không làm xe rời bãi trên hệ
thống. Lỗi ghi phiếu thu phải hoàn tác cả việc đóng lượt gửi và trả chỗ.

## Hợp đồng API

- `GET /api/v1/parking-sessions/{id}/checkout-quote`: yêu cầu quyền nhân viên
  trở lên, chỉ đọc dữ liệu. Trả số tiền, thông tin lượt gửi, thời điểm báo
  phí, hạn sử dụng và `quote_token` có chữ ký máy chủ.
- `PUT /api/v1/parking-sessions/{id}/check-out`: bắt buộc gửi `quote_token`,
  `payment_confirmed: true` (boolean thật) và `payment_method` là `cash`
  hoặc `transfer` khi có phí; dùng `null` khi miễn phí.
- `POST /parking/check-out`: vẫn cần các trường xác nhận trên và biển số.
  Token xác định chính xác lượt gửi; gửi lại yêu cầu cũ không được đóng một
  lượt gửi mới của cùng biển số.

Không gửi số tiền, thời gian ra hoặc nhân viên xử lý từ trình duyệt. Máy chủ
xác định các giá trị này. Yêu cầu thiếu xác nhận hoặc có trường ngoài hợp đồng
bị từ chối. Frontend cũ gửi body rỗng cần tải lại bản ứng dụng mới.

## Dữ liệu và triển khai

Hai cột nullable `checkout_quote_hash` và `checkout_payment_method` được thêm
vào lượt gửi để đối chiếu yêu cầu đã hoàn tất. Chỉ lưu SHA-256 của token,
không lưu nguyên token. Lượt gửi cũ giữ nguyên dữ liệu; không tự bổ sung
xác nhận thu tiền cho lịch sử chưa có thông tin này.

Khóa `SECRET_KEY` dùng để ký báo phí phải là chuỗi bí mật ngẫu nhiên tối thiểu
32 byte; dùng cùng cấu hình trên các máy backend của một môi trường. Không
đổi khóa giữa hai bước xem phí và xác nhận. Công cụ kiểm tra phát hành từ chối
cấu hình quá ngắn mà không in giá trị khóa ra log.

Cập nhật cấu trúc bằng công cụ rollout SQLite hoặc Alembic PostgreSQL của
dự án trước khi chạy backend mới. Triển khai frontend tương ứng và kiểm tra
`/ready`, mã phiên bản, mở báo phí, xác nhận thu và tra cứu lại trên môi trường
thử. Quy trình hạ tầng nằm trong [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).
