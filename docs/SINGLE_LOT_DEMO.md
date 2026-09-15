# Bản đồ án một bãi

Profile `single-lot-academic-v1` tạo một **SQLite mới hoàn toàn**, đúng một bãi và các tài khoản quản lý, nhân viên, admin, khách. Không ghi đè hoặc chuyển đổi DB đang dùng. Bộ demo hai bãi cũ vẫn giữ nguyên tại `expansion.demo_seed` / `scripts/start_demo.ps1`.

## Khởi động trên Windows

Từ thư mục Git root `ParkingAI`, sau khi cài thư viện theo [DEMO_GUIDE.md](DEMO_GUIDE.md):

```powershell
./scripts/start_single_lot_demo.ps1 -NoVision
```

Mặc định tạo `backend/artifacts/demo/single-lot-20260915.db` với schema mở rộng (48 bảng, gồm phí lượt online), build frontend hợp nhất vào `frontend/dist` (đã gồm giao diện phí lượt F/C/D; không cần bundle riêng) và mở server tại `http://localhost:8766`. Đọc mật khẩu từ tệp **cục bộ** `backend/artifacts/demo/single-lot-20260915.db.demo-credentials.json`; mỗi tài khoản có mật khẩu ngẫu nhiên riêng. Script chỉ in đường dẫn, không in mật khẩu. Các tệp trong `backend/artifacts` và tệp `*.demo-credentials.json` được Git bỏ qua.

| Tài khoản | Mục đích |
|---|---|
| `manager_demo` | Cấu hình lõi, báo cáo, tài chính |
| `staff_demo` | Vận hành vào/ra, tra cứu theo quyền |
| `admin_demo` | Cài đặt và kiểm tra quyền |
| `customer_demo` | Cổng khách, xe sở hữu, lượt gửi đang hoạt động |

Bộ `single-lot-live.db` là mốc P1/P2 cũ chứa kết quả Gemini đã nghiệm thu, không phải DB trình bày mở rộng hiện hành. Giữ nguyên bộ này. Để chạy bộ mới với AI đã cấu hình, dùng:

```powershell
./scripts/start_single_lot_demo.ps1 -NoVision -EnableAI -Database ./backend/artifacts/demo/single-lot-20260915.db -Port 8766
```

DB `single-lot.db` cũ được giữ làm mốc trước nâng cấp P1. Không dùng DB cũ trực tiếp với schema mới hoặc reset để khắc phục; chọn DB mới, hoặc chạy migration trên bản sao có backup đã kiểm chứng. Readiness từ chối schema không khớp trước khi phục vụ giao dịch.

Chạy lại launcher giữ DB và mật khẩu hiện có. Muốn bộ dữ liệu mới, truyền **tên DB khác**, ví dụ:

```powershell
./scripts/start_single_lot_demo.ps1 -NoVision -Database ./backend/artifacts/demo/single-lot-uat.db -Port 8767
```

Cần chỉ tạo dữ liệu mà chưa build/chạy server:

```powershell
Push-Location backend
../.venv/Scripts/python.exe -m expansion.single_lot_seed --database ./artifacts/demo/single-lot-20260915.db
Pop-Location
```

Lệnh seed từ chối nếu DB, marker `.demo.json` hoặc tệp mật khẩu đã tồn tại. Không có tùy chọn force/reset. Nếu tạo mới lỗi, bộ dựng dọn các artifact nó vừa tạo; tệp của người dùng được giữ lại. Bộ dựng dùng DB trung gian, migration và readiness check, rồi publish bằng hard link không ghi đè.

Server kiểm tra marker với ID bãi thực trong DB, yêu cầu đúng một bãi khi có `--single-lot`. `/config.js` truyền `SINGLE_SITE_ID` theo marker đã kiểm tra và dùng API cùng origin. Không dùng ID 2 hardcode của bản website cũ. Quyền vẫn do backend và membership quyết định.

## Bộ dữ liệu

| Dữ liệu | Nội dung |
|---|---|
| Khu/vị trí | 3 khu, 40 vị trí: 24 xe máy đang dùng, 12 ô tô đang dùng, 4 dự phòng ngừng dùng |
| Chỗ hiện tại | 2 xe đang gửi; 36 vị trí hoạt động, 34 còn trống. Bốn vị trí ngừng dùng không tính vào sức chứa khả dụng |
| Bảng giá minh họa | Xe máy 5.000đ/giờ; ô tô 20.000đ/giờ, làm tròn giờ theo service tính phí hiện hành |
| Lịch sử | 14 ngày trọn vẹn trước ngày tạo, gồm ngày thường/cuối tuần; 476 lượt đã hoàn tất, cao điểm giả lập lúc 17:00 |
| Thu/ca | 476 phiếu thu tiền mặt **giả lập**, tổng 3.280.000đ, và 3 biên nhận vé tháng DEMO 0đ (tổng 479 chứng từ); 14 ca đóng, chênh lệch bằng 0; phí từng lượt khớp phiếu thu |
| Vé tháng | Ba ví dụ miễn phí, mỗi vé có thẻ và biên nhận mẫu 0đ: còn hạn 24 ngày, sắp hết hạn sau 2 ngày và hết hạn 11 ngày trước thời điểm tạo |
| Kỳ rỗng | Một tuần kết thúc ngay trước ngày đầu lịch sử; ngày cụ thể trong `empty_period` của marker |
| Cổng khách | Hồ sơ và quyền sở hữu cho khách demo; xe vé tháng và ô tô có lượt active được cấp quyền tra cứu |
| Camera | Hai cấu hình cổng vào/ra; không tự kết nối thiết bị |

Toàn bộ tên, biển số, email và chứng từ là dữ liệu tổng hợp có nhãn DEMO. Phiếu thu dùng cùng service/ledger tiền mặt để kiểm tra doanh thu và chốt ca trong **DB đồ án riêng**. Các số tiền không đại diện tiền thật, không gọi ngân hàng. Marker ghi riêng `synthetic_cash_revenue` và `real_money_received: 0`; server bật `PARKINGAI_SHOWCASE_MODE` để màn hình/báo cáo/đầu vào AI ghi nhận chế độ dữ liệu mẫu. Không trộn các phiếu thu này vào DB vận hành.

Giá trị `monthly_examples` và khoảng lịch sử tính tương đối theo thời điểm tạo. DB được giữ nguyên khi khởi động lại nên vé sẽ tiếp tục hết hạn theo thời gian thật. Chọn tên DB mới khi cần tái tạo kịch bản.

## Kịch bản kiểm tra

1. Đăng nhập quản lý; mở khu/vị trí, loại xe, bảng giá và khách/vé tháng. Kiểm tra đúng một bãi, 3 khu và 40 vị trí.
2. Đăng nhập nhân viên; xem hai xe đang gửi, cho thêm xe vào/ra. Số chỗ trống thay đổi tương ứng; API từ chối ghi danh mục ngoài quyền.
3. Đăng nhập quản lý; chọn tuần kết thúc ngày `history_end` của marker. Có lượt vào/ra, doanh thu và cao điểm 17:00. Xem 14 ca đã đóng cùng phiếu thu.
4. Chọn tuần có ngày cuối `empty_period.anchor_date`. Lưu lượng/doanh thu bằng 0; chỗ hiện tại vẫn là trạng thái hiện tại và không phải số đo của tuần rỗng.
5. Xem ba vé tháng; xe vé còn hạn đang gửi có snapshot quyền lợi. Xe ô tô còn lại không có vé tháng và tính phí theo thời gian gửi.
6. Đăng nhập khách; chỉ xem hồ sơ/xe và lượt gửi được cấp quyền của mình.

Launcher cục bộ mặc định **AI tắt**. Để dùng Gemini với số liệu tổng hợp của DB đồ án, cấu hình `GEMINI_API_KEY` trong môi trường hoặc `backend/.env`, rồi bật rõ ràng:

```powershell
./scripts/start_single_lot_demo.ps1 -NoVision -EnableAI -Database ./backend/artifacts/demo/single-lot-ai.db -Port 8767
```

Cờ này chỉ bật AI cho profile một bãi đã kiểm chứng; khóa không đủ thì server từ chối khởi động ở chế độ bật AI. Không đưa API key vào frontend hoặc tài liệu. Các lần sinh dùng mạng và quota của provider; mặc định không tự sinh báo cáo khi khởi động.

Runner `scripts/verify_single_lot_ai.py` gọi thật năm ca (báo cáo ngày/tuần, hỏi đáp, nhân sự, kỳ rỗng), rồi kiểm replay/lịch sử/quyền và lưu đầu vào tổng hợp cùng câu trả lời ở artifact cục bộ. Kết quả HTTP thành công vẫn cần đối chiếu nội dung với số liệu, không tự chứng minh AI nhận xét đúng.

Các test AI mock/provider kiểm soát là bước riêng; dữ liệu seed và giao diện không chứng minh AI live, QR ngân hàng hay camera thật đã chạy. Gói giờ/ngày, adapter payOS, trả phí lượt và CV ô đỗ đã có mã trong bản nâng cấp. Theo dõi bằng chứng và giới hạn tại [nghiệm thu tích hợp](upgrade-2026-09-15/FINAL_ACCEPTANCE.md).

## Trình diễn phần mở rộng

1. Quản lý mở quản trị portal: tạo gói giờ/ngày/tháng, chọn loại xe, giá và thời lượng. Bãi demo dùng chế độ gói trả trước; đặt chỗ giờ/ngày được tạo từ đơn đã thanh toán. Vé tháng thông thường không giữ riêng một ô.
2. Khách đăng nhập, chọn xe đã được xác minh, chọn gói và thời điểm. Kiểm tra giá, hạn giữ chỗ, thời điểm phải đến và phần phí quá giờ. Mua thử bằng phương thức **DEMO**, xác nhận mô phỏng rồi xem vé, đặt chỗ và biên nhận PDF.
3. Nhân viên nhận xe vào trong cửa sổ đã mua. Tới muộn không kéo dài thời điểm kết thúc gói; mỗi vé giờ/ngày dùng một lượt. Khi xe ra, phần đã mua được trừ và chỉ thu tiền quá giờ nếu có. Ra sớm trả lại sức chứa ngay; xe ở quá giờ vẫn chiếm chỗ.
4. Khách mở chi tiết lượt đang gửi. Bảng phí hiển thị tổng phí, đã trả online và còn thu. Khi payOS chưa bật, giao diện thông báo rõ và vẫn cho nhân viên thu tại quầy. Không có nút mô phỏng nhận tiền ngân hàng cho phí lượt.
5. Quản lý/nhân viên mở camera: tạo cấu hình, nhận ảnh, xem biển gợi ý và sửa/xác nhận trước khi nhận xe. Dùng nhập biển tay khi OCR không nhận đúng. Việc nhận ảnh/xác nhận biển không tự cho xe vào hoặc ra.
6. Mở **Chỗ đỗ qua camera**: quản lý chọn ảnh nền đã kiểm tra trống, khoanh ô và lưu cấu hình. Nhân viên phân tích ảnh mới; mặc định cần hai ảnh mới khác nhau cùng kết luận. So sánh quan sát với trạng thái nghiệp vụ. Ảnh cũ, tối/mờ hoặc ánh xạ thay đổi có thể trả “chưa xác định”.

Vé giờ theo số giờ được công bố; vé ngày là 24 giờ liên tục. Đề nghị thanh toán phí lượt có hạn 5 phút, khác thời điểm `paid_through`: thời điểm này là cuối khối phí đã trả, không phải tự cộng 10 phút miễn phí. Trả online không tự đánh dấu xe đã ra. Nếu xe ra sau khối đã trả thì báo lại phần phát sinh; lịch sử lượt đã hoàn tất ghi “đã thu khi ra”.

Server demo luôn tắt payOS thật dù môi trường có cấu hình. Người dùng hiện chưa có tài khoản payOS; QR DEMO chỉ dùng để trình diễn đơn vé. [Hướng dẫn payOS](upgrade-2026-09-15/P5_OPERATIONS.md) mô tả môi trường API/worker riêng khi có tài khoản; biên nhận PDF là chứng từ của đồ án, chưa phải tích hợp hóa đơn điện tử thuế.

## Webcam và điện thoại

Với điện thoại cùng Wi-Fi, chạy launcher thêm `-Lan` rồi truy cập địa chỉ IP máy tính và cổng đã chọn. Màn hình camera hỗ trợ chọn ảnh/chụp bằng điều khiển của trình duyệt; việc xin quyền và khả năng chụp còn phụ thuộc trình duyệt/thiết bị. Bỏ `-NoVision` để dùng YOLO/RapidOCR khi đã có model cục bộ; thiếu model thì hệ thống vẫn cho nhập tay.

Webcam dùng tiến trình hữu hạn `edge/capture_agent.py`, đọc token camera từ biến môi trường cục bộ, không ghi token vào lệnh hoặc tài liệu. Xem [hướng dẫn capture](upgrade-2026-09-15/EDGE_CAPTURE.md) cho lệnh, giới hạn số ảnh và thu hồi token. Dùng ảnh nền cố định cho CV; thay đổi góc camera cần cấu hình lại. Kiểm thử AVI tổng hợp không thay cho thử webcam/điện thoại ở bãi.

## Sao lưu và khôi phục

```powershell
./.venv/Scripts/python.exe scripts/verify_single_lot_recovery.py --database ./backend/artifacts/demo/single-lot-20260915.db --output ./backend/artifacts/demo/recovery-latest.json
```

Runner chỉ nhận DB tổng hợp có marker, sao lưu bằng SQLite online backup rồi khôi phục vào thư mục mới. Nó so sánh mọi bảng, integrity/FK và readiness, không ghi đè DB nguồn. Sau khi có đơn/ghi có/chứng từ mới, giữ backend hiểu schema mới; không hạ schema hoặc xóa chứng từ để rollback.

## Kiểm chứng tự động

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_single_lot_demo_seed.py tests/test_demo_server.py tests/test_expansion_demo_seed.py
```

Kiểm tra: tạo mới/migration/readiness; từ chối ghi đè; lỗi giữa chừng không làm mất tệp khác; bộ dữ liệu và vé tháng; không trùng xe/ô trong lịch sử; số chỗ khớp lượt active; phí/phiếu thu/ca khớp; manager/staff được mở workspace một bãi; báo cáo có dữ liệu/kỳ rỗng; runtime config nhận ID thực và từ chối marker sai. Demo hai bãi cũ cũng được kiểm lại.
