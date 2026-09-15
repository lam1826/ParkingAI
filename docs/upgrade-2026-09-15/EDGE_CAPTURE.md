# Lấy ảnh tại máy edge — phần nền P6

`edge/capture_agent.py` đã có bộ lấy frame từ video cục bộ, webcam được chọn hoặc URL RTSP(S) trong biến môi trường. Bộ này gửi ảnh vào inbox OCR hiện có; không nhận/trả xe, sửa chỗ hoặc thu tiền. Nhân viên vẫn đối chiếu ảnh và xác nhận biển trong giao diện.

## Chạy thử

Cài môi trường vision theo `backend/requirements-vision.txt`. Tạo camera đúng bãi/làn và cấp token bằng tài khoản quản lý. Đặt token trong biến môi trường `PARKINGAI_CAMERA_TOKEN` của máy edge, không đưa vào command line, Git hay tài liệu. Bật vision trên server nếu cần chạy detector/OCR; cờ `-NoVision` chỉ phù hợp kiểm đường nhận ảnh khi không cần nhận diện.

Replay bằng video do người dùng chuẩn bị, trên camera có tên rõ là DEMO:

```powershell
./.venv/Scripts/python.exe edge/capture_agent.py --video ./backend/artifacts/camera/sample.avi --camera-id 1 --api-origin http://127.0.0.1:8766 --interval 5 --max-events 20
```

Webcam phải được chọn tường minh, ví dụ thay `--video ...` bằng `--device 0`. Không tự mở webcam khi khởi động server. Dùng `--max-events 0` để chạy liên tục và Ctrl+C để dừng. Mặc định chỉ nhận tối đa 20 ảnh đã được server xác nhận.

Đối với camera IP, đặt URL RTSP(S) vào biến môi trường riêng, ví dụ `PARKINGAI_RTSP_SOURCE`, rồi dùng `--stream-env PARKINGAI_RTSP_SOURCE`. URL có thể chứa thông tin đăng nhập nên không in ra log. Nguồn camera chỉ được mở ở tiến trình con tại máy edge. API nhận token bắt buộc HTTPS nếu ở máy khác; HTTP chỉ cho loopback.

Không hardcode bãi/camera của website cũ: lấy ID từ cấu hình hiện tại. Mốc `captured_at` của video replay là thời điểm frame được lấy khi phát lại, không phải ngày quay video gốc. Giữ camera DEMO riêng và không mô tả replay là quan sát bãi hiện tại.

## Giới hạn tải và phục hồi

- Chu kỳ 3–30 giây, mặc định 5 giây; ảnh giữ tỷ lệ và cạnh dài tối đa 1.600 pixel, JPEG tối đa 2 MB.
- Một ảnh đang gửi và tối đa một frame chờ. Khi mạng/OCR chậm, frame chờ cũ bị bỏ; không tích hàng trăm ảnh hoặc gửi video liên tục qua API nghiệp vụ.
- Thử lại tối đa bốn lần với cùng UUID, thời điểm và byte ảnh. Timeout, phản hồi xác nhận không hợp lệ, 429 và lỗi tạm thời không tạo mã ảnh mới. Tôn trọng `Retry-After` trong giới hạn 30 giây.
- 401/403, xung đột dữ liệu, ảnh sai/hết hạn hoặc redirect dừng vòng gửi. Token chỉ tới đúng origin cấu hình, không đi theo redirect.
- Nếu kết quả vẫn chưa rõ hoặc người dùng dừng lúc đang gửi, log trả `unconfirmed_event_id` để kiểm inbox. Bộ lấy ảnh chưa có hàng đợi bền trên đĩa: khởi động lại là lần lấy ảnh mới, không tự phát lại nội dung đã mất. Không tuyên bố exactly-once xuyên qua việc tắt tiến trình.
- Đọc thiết bị nằm trong tiến trình con; khi không có frame đúng hạn, tiến trình được dừng. Không treo request thu tiền hay giữ connection SQL.
- Log chỉ ghi mã ảnh/kết quả và lỗi chung, không ghi token, URL camera, ảnh hoặc biển. Stderr native của OpenCV/FFmpeg trong tiến trình con bị chuyển vào null vì thư viện có thể in URL nguồn khi mở lỗi.

OpenCV chỉ hỗ trợ timeout đọc/mở qua tham số khởi tạo đối với một số backend; RTSP ở đây chọn FFmpeg và đặt cả hai timeout 5 giây. Tiến trình giám sát vẫn có hạn chờ để xử lý thiết bị không phản hồi. [OpenCV Video I/O flags](https://docs.opencv.org/4.12.0/d4/d15/group__videoio__flags__base.html).

HTTPX phân biệt timeout connect/read/write/pool; retry ứng dụng giữ nguyên event cho cả trường hợp mất phản hồi sau server đã nhận, thay vì chỉ dựa vào retry lỗi kết nối của transport. [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/), [HTTPX transports](https://www.python-httpx.org/advanced/transports/).

## Bằng chứng hiện có

28 test trong `tests/test_edge_capture.py` đạt (2,17 giây): mất ACK/retry một observation, payload không đổi, token bị thu hồi, redirect, lỗi tạm thời/thử lại có hạn, acknowledgement sai, origin/token, hàng đợi một frame, encode/resize và replay file AVI thật được tạo từ frame tổng hợp. Không mở webcam, không gọi server/provider hoặc dùng ảnh bãi thật trong suite này.

Lệnh kiểm độc lập khi backend P4 đang được ghép:

```powershell
./.venv/Scripts/python.exe -m pytest --noconftest -q tests/test_edge_capture.py --tb=short -p no:cacheprovider
```

Test này cũng nằm trong bộ pytest chung sau khi backend ổn định. `--noconftest` ở lượt độc lập chỉ tránh khởi tạo app đang ghép; không dùng fixture/backend hoặc mạng trong các ca capture.

P6 còn tích hợp trạng thái camera/giao diện quản lý, đối chiếu ảnh–biển–vào/ra và nghiệm thu thiết bị thực. P7 quan sát ô đỗ là khối riêng; capture này không nhận biết ô trống và không biến lỗi camera thành ô trống.

## Nhận ảnh và trạng thái camera

API danh sách camera dùng một truy vấn tổng hợp `MAX(observed_at)` theo camera trong đúng bãi, không đọc BLOB ảnh. `last_received_at` có múi giờ Việt Nam; `health` là `unseen`, `recent` (máy chủ nhận ảnh trong 30 giây), `stale` hoặc `disabled`. Đây không phải heartbeat của thiết bị và không đánh giá độ rõ ảnh. Sau khi retention xóa hết ảnh, không còn bằng chứng thời gian nhận nên trạng thái trở về `unseen`.

Sửa/ngừng camera giữ thời gian ảnh cuối; ngừng thu hồi token, bật lại cần cấp token mới. Staff chỉ đọc. Kiểm tra API/health: `tests/test_camera_health.py` + `tests/test_expansion_vision_api.py`, 24 passed trong 7.48 giây (15/09/2026); có biên 30 giây, thời gian tương lai, scope, quyền và không N+1/BLOB.

Người dùng xác nhận có webcam hoặc điện thoại, chưa chọn/kết nối thiết bị cụ thể. 28 kiểm tra capture offline và 24 kiểm tra API không thay cho nghiệm thu thiết bị vật lý.


Cập nhật privacy: giảm retention áp dụng ngay cho GET/list/review và hạn trả về DTO. Cùng PATCH cấu hình clamp `expires_at` của ảnh đã có xuống hạn ngắn hơn, không tải BLOB; tăng lại retention không phục hồi ảnh đã hết hạn. Ba bước regression RED→GREEN gồm lọc ảnh trước phân trang và giảm–tăng trước purge. Bộ camera/API/runtime sau cùng:35 passed,1 skipped,17,54s. Camera vật lý vẫn chưa được kiểm.

Ngày15/09, chương trình capture đã được chạy thành tiến trình thật với AVI tổng hợp và gửi2 ảnh tới máy chủ local8768; nằm trong36 checks P4/P6 đạt tại `backend/artifacts/demo/p4-p6-http-fixed-acceptance/result.json`. API kiểm camera vừa nhận ảnh, quyền xem ảnh, xác nhận biển không tự nhận xe và token bị thu hồi trả401. Máy chủ dùng `--no-vision`, nên bằng chứng này xác nhận đường lấy/gửi/lưu/duyệt ảnh, không đánh giá detector hoặc OCR.
