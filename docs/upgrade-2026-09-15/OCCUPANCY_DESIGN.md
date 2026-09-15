# P7 — Quan sát chỗ đỗ bằng ảnh tham chiếu

Ngày: 15/09/2026. Hợp đồng đã được root duyệt; kết quả kiểm thử và nghiệm thu thiết bị sẽ được ghi riêng. Đây là thuật toán nền chạy CPU, chưa có kết quả đo độ chính xác trên bãi thực tế.

## Phạm vi và quyền

Quản lý chọn một ảnh có các chỗ trống, xác nhận đã kiểm tra ảnh, khoanh các vùng chỗ đỗ và lưu phiên bản cấu hình. Nhân viên đọc kết quả và yêu cầu phân tích một ảnh đã nhận qua luồng camera hiện có. Cả hai cần quyền hiện tại tại đúng bãi; quản lý cấu hình cần cả vai trò tài khoản lẫn membership quản lý.

Không cập nhật `ParkingSlot.is_occupied`, lượt gửi, giữ chỗ hoặc thanh toán. Quan sát CV và trạng thái nghiệp vụ luôn hiển thị riêng. `unknown` không được hiểu là chỗ trống. Độ thay đổi điểm ảnh không phải độ tin cậy hoặc độ chính xác nhận diện xe.

Ảnh đi qua `VisionObservation` và endpoint ảnh riêng tư hiện có. P7 không lưu thêm BLOB, không tải ảnh mạng, không mở camera/RTSP tự động và không cần trọng số model mới. Tên và hướng vào/ra của camera vẫn thuộc P6; P7 chỉ gắn một cấu hình vùng quan sát với camera đó.

## Dữ liệu

- `occupancy_calibrations`: UUID, bãi/camera, phiên bản duy nhất theo camera, tham chiếu ảnh nền, bản sao UUID/hash/kích thước/thời điểm nhận/hạn lưu, vùng `{slot_id, polygon}`, settings, engine và settings schema version; người tạo/thời điểm; request ID và hash body chống gửi lặp khác nội dung.
- `occupancy_observations`: UUID, calibration, tham chiếu ảnh nguồn và bản sao UUID/hash, `measured_at` lấy từ thời điểm chụp, `received_at` từ server nhận ảnh, `analyzed_at`; người phân tích; hạn lưu gốc; quality và readings JSON. Một calibration chỉ phân tích một source UUID một lần.
- `occupancy_calibration_slots`: khóa ghép calibration/chỗ, hai FK giữ danh tính vị trí. Chỗ đã được tham chiếu không thể bị xóa rồi tái dùng ID; quản lý có thể ngừng sử dụng chỗ. Tạo link cùng giao dịch với calibration. Regions lưu tên chỗ/khu ID/loại xe ID/ngày tạo; thay đổi ánh xạ trả `unknown` và yêu cầu cấu hình lại.
- Hai FK tới `vision_observations` dùng `ON DELETE SET NULL`. Metadata lịch sử giữ lại khi ảnh bị xóa; không có bản sao ảnh khác vượt chính sách lưu.
- Các FK còn lại: calibration → parking_sites/vision_cameras/users; observation → calibration/users. Schema chính xác nằm trong `backend/expansion/occupancy_models.py`; registry/migration do owner rollout tích hợp.

Mỗi phiên bản có tối đa 64 chỗ, mỗi chỗ đúng một polygon gồm 3–12 đỉnh hữu hạn trong `[0,1]`. Vùng không tự cắt, không trùng đỉnh, có diện tích hợp lệ và không chồng lấn đáng kể. Các chỗ phải hoạt động, thuộc đúng bãi và khu của camera nếu camera đã gắn khu. Tạo phiên bản mới thay cho sửa lịch sử phiên bản cũ; khóa camera và unique constraint bảo vệ thao tác đồng thời.

## Thuật toán `reference-diff-v1`

Module `occupancy_engine` nhận bytes hai ảnh, vùng và settings; trả quality/readings, không truy cập DB. Kiểm giới hạn bytes/pixel trước giải mã; thu ảnh về cạnh dài tối đa 640 pixel. Dùng ảnh xám, độ biến thiên Laplacian để kiểm ảnh mờ, mức sáng/bão hòa để kiểm ảnh tối hoặc bị che. Chênh lệch sáng quá lớn hoặc gần toàn cảnh đổi khác trả `unknown`.

Sau điều chỉnh độ sáng toàn ảnh trong giới hạn cho phép, tính tỷ lệ pixel thay đổi trong mỗi vùng. Mặc định: delta pixel 30, trống khi tỷ lệ ≤0,06, có vật chiếm vùng khi ≥0,25; khoảng giữa là `unknown`. Đây là quy tắc so sánh ảnh, không nhận diện loại vật hoặc chứng minh vật đó là xe. Đổi góc camera, bóng đổ, người đi qua và ánh sáng vẫn cần kiểm chứng bằng dữ liệu riêng.

Settings có giới hạn: delta 10–80; empty ratio 0,01–0,20; occupied ratio 0,15–0,80 và cách empty ít nhất 0,05; giới hạn đổi sáng 10–80; blur variance 0–200; tuổi ảnh 5–300 giây; số ảnh xác nhận 1–3. Mặc định cần 2 source UUID khác nhau, cùng calibration, thời điểm chụp tăng và còn mới, có cùng raw state. Gửi lại cùng source không tăng số ảnh xác nhận. Ảnh chất lượng kém hoặc trạng thái khác nhau ngắt chuỗi xác nhận.

Các phép ảnh dùng [OpenCV absdiff](https://docs.opencv.org/4.x/d2/de8/group__core__array.html) và [mặt nạ polygon](https://docs.opencv.org/4.x/d6/d6e/group__imgproc__draw.html). Các ngưỡng trên là lựa chọn triển khai, chưa phải ngưỡng đã đo trên bãi.

## Hạn ảnh, freshness và đối chiếu

Hạn hữu hiệu của mỗi ảnh là `min(expires_at đã lưu, observed_at + retention_hours hiện tại của camera)`. Giảm thời gian lưu có hiệu lực với ảnh cũ. Không kéo dài hạn nếu sau đó tăng retention. Ảnh nền hết hạn/bị xóa yêu cầu quản lý chọn ảnh nền mới; ảnh nguồn hết hạn/bị xóa không còn được tải.

Freshness dùng `captured_at`, không dùng giờ bấm phân tích hoặc giờ tải video cũ lên. Ảnh chụp ở tương lai hoặc quá tuổi cho phép trả `unknown`. API đọc luôn áp lại hạn ảnh, tuổi ảnh, camera đang bật và phiên bản calibration hiện tại; không biến kết quả cũ thành trạng thái mới chỉ vì đọc lại.

`valid_until` hiển thị thời điểm sớm nhất giữa hạn hữu hiệu ảnh nền, ảnh nguồn và hạn freshness của ảnh nguồn. Khi có cấu hình mới, kết quả của cấu hình cũ không làm kết quả hiện tại. Khác biệt chỉ có giá trị boolean khi cả CV và nghiệp vụ đều có trạng thái có xe/trống; với unknown/inactive trả null.

## HTTP và giao diện

- `GET /api/v2/sites/{site_id}/occupancy?camera_id=...`: engine/status, calibration hiện tại, metadata lần phân tích mới nhất theo thời điểm chụp, readings và `valid_until`. Không trả BLOB/biển số/chủ xe.
- `POST .../occupancy/calibrations`: manager gửi `{camera_id, reference_observation_id, regions, settings, empty_reference_confirmed:true, request_id}`. Khác bãi hoặc ảnh hết quyền không được xem; body ngoài whitelist bị từ chối.
- `POST .../occupancy/analyze`: staff gửi `{camera_id, calibration_id, observation_id}`. Lặp lại nguồn và phiên bản trả cùng bản ghi; không chạy lại inference hoặc tạo dữ liệu nghiệp vụ.
- CPU có một tác vụ đồng thời mỗi process; bận trả 429, không xếp hàng vô hạn. Giải phóng transaction trước khi chạy thuật toán, kiểm lại quyền/camera/ảnh/calibration trước khi ghi kết quả.

Trang `Chỗ đỗ qua camera`: chọn camera và ảnh, đọc ảnh qua Blob URL riêng tư, vẽ vùng trên ảnh; đối chiếu bảng kết quả với trạng thái nghiệp vụ. Quản lý có phần chọn ảnh nền, chọn chỗ, thêm/xóa đỉnh, xác nhận chỗ trống và lưu phiên bản. Nhân viên không có phần lưu cấu hình. Thông báo hết hạn và lý do unknown hiện rõ, không dùng nhãn “camera online”.

Xử lý ảnh mới tự động là bước tùy chọn: tác vụ hữu hạn có thể chọn source UUID mới nhất theo camera và gọi cùng interface phân tích với quyền kỹ thuật được kiểm chứng. Bản đầu dùng nút phân tích ảnh cụ thể, không thêm worker tự chạy hoặc truy cập thiết bị.

## Kiểm chứng và giới hạn

Test ảnh tổng hợp kiểm phân loại theo quy tắc, vùng không hợp lệ, ảnh mờ/tối/đổi sáng, khác kích thước, biên ngưỡng và lỗi giải mã. Test HTTP kiểm scope/role, replay, race phiên bản, ảnh cũ/future/retention bị giảm/purge, thứ tự khung hình và đối chiếu không ghi chỗ/lượt/tiền. Đây không phải benchmark độ chính xác ngoài thực tế.

Nghiệm thu thiết bị cần ảnh/clip của webcam hoặc điện thoại người dùng, ở góc lắp ổn định, cùng nhãn độc lập cho chỗ trống/có xe/bị che ở điều kiện sáng khác nhau. Tách dữ liệu chỉnh ngưỡng khỏi dữ liệu đánh giá và báo false-empty/false-occupied/unknown; chưa có dữ liệu này thì không công bố tỷ lệ chính xác.

### Đánh giá ảnh đã gán nhãn, chạy ngoại tuyến

`scripts/evaluate_occupancy.py --manifest <dataset/manifest.json> --output <new-report.json>` nhận manifest theo `occupancy_manifest.example.json`. Đặt ảnh thật trong thư mục dataset riêng tư; ví dụ chỉ là cấu trúc, không kèm ảnh hay kết quả thực. Mỗi vùng cần một nhãn độc lập `empty`/`occupied`; tách tập chỉnh ngưỡng khỏi tập `held_out`. Không dùng chính kết quả model để điền nhãn.

CLI chỉ đọc ảnh cục bộ bên trong thư mục manifest, không truy cập mạng, camera hoặc DB. Báo confusion matrix gồm cột `unknown`, tỷ lệ có kết luận, độ đúng trên các kết luận, số kết luận trống sai/có xe sai và hash nguồn/settings. Mọi ảnh không đủ chất lượng vẫn nằm trong mẫu và tính vào unknown. Công cụ chỉ đánh giá raw state từng ảnh; chưa đánh giá chuỗi xác nhận, freshness hay đối chiếu nghiệp vụ. Manifest tự khai nguồn nhãn, công cụ không chứng minh được tính độc lập của người gán nhãn. Dữ liệu tổng hợp phải có `synthetic:true,label_source:synthetic`; số đo này không phải độ chính xác camera thực.
