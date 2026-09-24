# Sửa tài khoản/camera và kiểm thử tổng thể — 24/09/2026

Đợt sửa tiếp theo cho nút **Bật tự động bị mờ** có biên bản riêng tại [CAMERA_AUTOMATION_FIX_2026-09-24.md](CAMERA_AUTOMATION_FIX_2026-09-24.md). Các số liệu dưới đây thuộc đợt kiểm toàn hệ thống trước phản hồi này; không được hiểu là đã chạy lại toàn bộ suite sau mọi thay đổi mới.

**Đã sửa lỗi tài khoản, luồng gửi ảnh từ webcam và các lỗi phát hiện trong kiểm thử. Kết quả đạt và phần chưa đạt được ghi riêng dưới đây; chưa thể kết luận mọi ảnh biển số, thiết bị vật lý và dịch vụ bên ngoài đều hoạt động ổn định.**

Phạm vi là ứng dụng React/FastAPI thật tại `http://127.0.0.1:8793`, chạy trên DB tổng hợp một bãi được đánh dấu riêng. Giao diện mẫu ở cổng 8790 được giữ nguyên. Không sửa DB người dùng, chuyển tiền ngân hàng, push hay triển khai website trong đợt này.

## Lỗi đã tìm được và sửa

1. **Nút “Sửa hồ sơ” mất chữ:** CSS anchor của mẫu ghi đè màu nút MUI thành xanh trên nền xanh. Sửa bộ sinh CSS để không áp quy tắc màu anchor thông thường lên `MuiButtonBase`. Kiểm tra Chrome trước sửa có tương phản 1,00:1; sau sửa 5,658:1 và hover 9,202:1, chữ trắng hiển thị rõ. Review phát hiện bản sửa đầu dùng `:not(...)` tăng specificity làm nút native “Vào vận hành” xanh trên xanh (1,00:1); đã giữ bằng chứng lỗi này và đổi sang `a:where(:not(...))` để giữ độ ưu tiên ban đầu. Giữ bố cục trang, kiểm lại cả hai loại nút.
2. **Webcam có hình nhưng không gửi OCR:** vòng gửi ảnh chỉ chạy khi tự động được cho phép/bật. Thêm **Quét biển số** độc lập, trạng thái đang đọc/đọc được/không thấy biển/lỗi, và hướng dẫn kiểm tra. Ảnh quét một lần luôn đi qua xác nhận thủ công, không tự nhận/trả xe. Ngưỡng tự động và quyền không bị hạ.
3. **Sửa biển trên ảnh đã xác nhận nhưng giá trị mới bị bỏ qua:** trường biển của ảnh đã duyệt chuyển thành chỉ đọc, có hướng dẫn quét/chọn ảnh mới. Không âm thầm gửi giá trị cũ khi giao diện cho người dùng sửa.
4. **Xe đặt trước vào đúng ranh giới thời hạn có thể không liên kết đặt chỗ:** nhận xe đọc đồng hồ hai lần. Giờ dùng một thời điểm cho chọn đặt chỗ, chỗ trống, vé tháng, bảng giá và ghi lượt. Regression thực tế qua ranh giới đã thất bại trước sửa và đạt sau sửa.
5. **Khó chẩn đoán AI trả 503:** thêm metadata lỗi provider được lọc an toàn; không ghi nội dung lỗi, khóa, URL, prompt hoặc traceback. Đây là khả năng chẩn đoán, không được gọi là đã sửa lỗi sẵn sàng của provider.
6. **Trùng tiền tố mã loại xe nhưng báo trùng tên:** tái hiện được cả thêm và sửa qua API; sửa ánh xạ lỗi để chỉ đúng tiền tố mã. Hai test mới thất bại trước sửa; 36 test liên quan đạt sau sửa, giữ HTTP 409, ràng buộc duy nhất và bản ghi ban đầu. Sửa này phát sinh trong lúc lượt toàn bộ đang chạy, nên có kiểm tra riêng sau đó, không giả vờ nó đã có trong 2.043 ca được thu thập từ đầu.

## Kiểm thử và giới hạn

| Nhóm | Bằng chứng trong đợt này | Trạng thái |
| --- | --- | --- |
| Backend toàn bộ | Baseline: 2.013 đạt, 5 lỗi, 20 bỏ qua sẵn có. Chạy lại: **2.024 đạt, 0 lỗi, 19 chưa chạy**, 625,19 giây; 125 warning được giữ trong log | ĐẠT các ca đã chạy; có 36 ca mục tiêu đạt sau sửa thông báo prefix |
| Frontend Node | 279/279, không skip; bản nguồn cuối sau sửa camera | ĐẠT |
| ESLint/Vite | Lượt cuối cả lint và build đều exit 0 | ĐẠT |
| Trang theo vai trò và màn hình nhỏ/lớn | 277/277 kiểm tra, 67 trường hợp role/route | ĐẠT phạm vi render/quyền trang; không tự suy thành đã chạy mọi giao dịch |
| Màu các nút liên kết sau sửa cuối | 15/15 kiểm tra cả MUI/native primary/secondary và trạng thái hover thật | ĐẠT; [ảnh tài khoản sau sửa](../backend/artifacts/comprehensive-uat/a9734fca28/admin-account-desktop.png) |
| Luồng giao dịch UI | 97/97 lượt kiểm hành trình cuối; 34/34 kiểm bổ sung vé tháng/lịch sử/prefix/tài khoản, cùng bằng chứng CRUD ở các lượt trước | ĐẠT các ca ghi trong ma trận browser; không gộp trang chỉ mở thử thành giao dịch đã kiểm |
| Camera UI → API OCR thật → đối chiếu → nhập thủ công | 27/27 kiểm tra; có ảnh đầu vào chuẩn qua luồng webcam giả lập | ĐẠT luồng, chưa kết luận độ chính xác trên thiết bị thật |
| Hai ảnh OCR quốc tế | 1/2 khớp toàn biển; Colorado không được detector tìm thấy | CHƯA ĐẠT cả hai ảnh; giữ `ocr_accuracy_passed=false` |
| Ảnh Việt Nam có sẵn | YOLO→OCR đúng 20/20 ảnh toàn xe, nhưng chỉ 64/500 crop; xe máy crop 0/250. OCR riêng trên crop có sẵn đúng 457/500 | Giữ đủ 520 mẫu; ảnh toàn xe chỉ là pilot một camera, chưa nghiệm thu thiết bị người dùng |
| Gemini thật | 9 yêu cầu nghiệp vụ: 6 thành công đã đọc nội dung, 3 lần 503 | Đã có output cho đủ 6 loại ca; sẵn sàng chưa ổn định trong phiên |
| Ngân hàng/payOS | Không có tài khoản/cấu hình; runner mẫu cố định tắt | CHƯA KIỂM CHỨNG giao dịch tiền thật |
| PostgreSQL/POSIX | Môi trường Windows không có PostgreSQL thử nghiệm | Không gộp các skip này vào số đạt |

Các lượt kiểm thử API/provider/ảnh có phạm vi khác nhau; không cộng tổng để công bố tỷ lệ bao phủ toàn bộ sản phẩm. Bộ backend hiện thu thập 2.045 ca: đối chiếu lượt toàn bộ 2.043 ca và 36 ca mục tiêu cho 2.026 ca đạt duy nhất + 19 chưa chạy, không có test ID còn thiếu. Đây **không phải** tuyên bố một lần chạy 2.045 ca cùng lúc. Lượt sau sửa prefix kiểm đúng phần mã thay đổi cuối.

## Minh bạch với lỗi kiểm thử ban đầu

Năm lỗi backend ban đầu được lưu nguyên trong XML/log: hai ca đồng hồ chỉ ra lỗi nghiệp vụ thật; hai ca concurrency dựa vào thứ tự khóa cũ; một ca còn so response cũ thiếu trường `total_reserved`. Hai harness concurrency được đồng bộ trước lần ghi đầu tiên và vẫn yêu cầu chính xác một 201/một 400, một xe/một lượt/một chỗ bị chiếm, không 500. Expected availability thêm đúng `total_reserved: 0`, không xóa assert về khu vực ngừng hoạt động. Không thêm skip/xfail hoặc đổi output production để che lỗi.

Các lượt browser đầu cũng được giữ lại, kể cả lỗi selector/harness. Chỉ sửa đồng bộ chờ render, selector trường nhập và cách lấy dữ liệu theo hợp đồng API hiện có; không thay lỗi của ứng dụng bằng PASS. Báo cáo UI chi tiết liệt kê các lượt và phạm vi giao dịch đã thực hiện.

## Tài liệu/bằng chứng

- [Backend: nguyên nhân, red/green và giới hạn](../backend/artifacts/comprehensive-20260924/backend-findings.md).
- [Ma trận F01–F13, phần mở rộng và kết quả từng module](../backend/artifacts/comprehensive-20260924/backend-full-final-report.md).
- [Browser: ma trận giao diện và giao dịch](COMPREHENSIVE_BROWSER_UAT_2026-09-24.md).
- [Camera: nguyên nhân, độ chính xác và giới hạn](CAMERA_SCAN_DIAGNOSIS_2026-09-24.md).
- [AI thật: từng lần gọi và đối chiếu nội dung](AI_LIVE_RETEST_2026-09-24.md).
- Toàn bộ log/XML/JSON chính: `backend/artifacts/comprehensive-20260924/`; profile Chrome riêng được dọn sau kiểm thử. Harness browser không lưu mật khẩu/token/mã vé bí mật của tài khoản demo.

## Thử lại camera trên máy người dùng

Mở bản 8793, tải mới trang, vào **Vận hành → Camera → Dùng webcam → Quét biển số**. Khi có gợi ý, đối chiếu/sửa ở ô biển trước khi chuyển sang thao tác thủ công. Khi báo chưa đọc được, thử ảnh có cả xe và vùng biển đủ lớn, đủ sáng; lỗi nhận diện vẫn được hiển thị và không tự tạo lượt gửi. **Bật tự động** là chức năng khác, cần chính sách được quản lý cho phép và ảnh đạt điều kiện.
