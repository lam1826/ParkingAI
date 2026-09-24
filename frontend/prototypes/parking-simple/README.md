# ParkingAI — demo đầy đủ luồng theo đề tài

Bản xem trước để người dùng duyệt giao diện và nghiệp vụ trước khi triển khai. Phạm vi một bãi, HTML/CSS/JavaScript tự chứa. Không sửa hoặc kết nối ứng dụng thật.

## Mở demo

- Đang phục vụ tại `http://127.0.0.1:8790/`. Nếu đang mở bản cũ, tải lại trang.
- Có thể mở trực tiếp `index.html`, không cần cài đặt. Mọi dữ liệu trở về mẫu khi tải lại.
- Màn đăng nhập có nút xem nhanh **Admin / Manager / Customer**, cùng lựa chọn thử quyền **Nhân viên**. Ba giao diện chính vẫn giữ nguyên; Staff dùng màn vận hành với quyền hạn chế.
- Có thể mở thẳng `#admin`, `#manager`, `#customer` hoặc `#staff` để thử vai trò. Đây là tiện ích xem trước, không phải cơ chế xác thực bảo mật.
- Đăng nhập thủ công bằng tên mẫu `admin_demo`, `manager_demo`, `customer_demo`, `staff_demo`; mật khẩu công khai dành riêng cho mô phỏng là `demo123`. Tài khoản bị khóa trong demo không đăng nhập được. Không dùng thông tin này cho ứng dụng thật.

## Đối chiếu đề tài

| Yêu cầu | Nơi thao tác trong demo | Cách thể hiện |
|---|---|---|
| Đăng nhập/đăng xuất/phân quyền | Màn đăng nhập, nút tài khoản/đăng xuất | Sai mật khẩu/tài khoản khóa bị từ chối; Admin có Manager; Staff vận hành, Customer luồng riêng |
| Khu vực | Bãi đỗ → Khu vực | Thêm/sửa tên, loại xe, sức chứa, trạng thái; xóa khu chưa có chỗ |
| Vị trí đỗ | Bãi đỗ → Vị trí đỗ | Thêm/sửa/xóa chỗ chưa dùng, ngừng phục vụ; phân biệt có xe/giữ trước/trống/tạm ngừng |
| Loại xe/bảng giá | Loại xe & bảng giá | Thêm/sửa/ngừng/xóa khi không được tham chiếu; giá theo giờ và loại xe; Admin và Manager cùng quản lý |
| Phương tiện/khách quen | Khách & vé → Khách hàng / Phương tiện | Tạo/sửa hồ sơ, liên kết xe, trạng thái hoạt động |
| Nhận xe/trả xe/thời gian | Vận hành → Nhập tay | Nhận khách vãng lai không cần đặt trước; chống nhận trùng; xem phí/thu tiền/trả xe |
| Tính phí | Vận hành hoặc Customer → Phí gửi xe | Giá lúc vào; làm tròn giờ bắt đầu, tối thiểu một giờ; vé tháng bao phủ thì miễn phí, phần quá hạn tính thêm |
| Chỗ trống theo khu | Bãi đỗ, Tổng quan, báo cáo | Tự cập nhật theo thao tác; không cộng chỗ đang giữ/ngừng phục vụ vào chỗ nhận được |
| Tra cứu biển và thời gian | Lịch sử gửi xe | Biển/mã xe/mã vé, ngày vào từ–đến bao gồm cả ngày VN, trạng thái/loại; chi tiết phí và chứng từ |
| Vé tháng | Khách & vé → Vé tháng | Cấp, sửa theo điều kiện, gia hạn thành kỳ mới, còn hạn/chưa đến hạn/hết hạn/ngừng; Customer xem vé của mình |
| Lưu lượng/doanh thu/cao điểm | Thu chi & báo cáo → Thu chi / Lưu lượng | Khoảng ngày, hôm nay/7 ngày, vào/ra/tổng, tiền đã thu và CSV, cao điểm, chỗ hiện tại theo khu |
| AI báo cáo ngày/tuần | Thu chi & báo cáo → AI | Chọn Báo cáo lưu lượng và kỳ, tạo kết quả mô phỏng kèm số liệu nguồn, xem lại lịch sử |
| AI hỏi đáp | Tab AI hoặc chatbot góc phải | Hỏi cao điểm/chỗ trống từ thống kê; Customer chỉ giá/chỗ trống/hướng dẫn, Staff không xem tài chính |
| AI gợi ý nhân sự | Tab AI → Gợi ý nhân sự | Dựa vào tổng lượt vào/ra theo giờ; nói rõ chưa đủ năng suất xử lý để chốt số người |
| AI SDLC + test | Nút Đối chiếu chức năng với đề tài, tài liệu đi kèm | KT1/KT2/KT3, prompt dự kiến, Node tests vào/ra/phí/chỗ/AI và kiểm tra trình duyệt |

## Kịch bản thử nhanh

1. Đăng nhập Manager, mở **Bãi đỗ**. Tạo khu mới hoặc sửa sức chứa khu, thêm vị trí. Thử tạm ngừng một ô trống và xem tổng chỗ giảm.
2. Mở **Loại xe & bảng giá**, thêm Xe tải nhẹ với mã E và đơn giá. Tạo khu phục vụ loại này rồi thêm chỗ E-01. Loại mới không tự sinh sức chứa.
3. **Khách & vé**: thêm khách, liên kết biển và loại xe, cấp vé tháng. Việc cấp/gia hạn ghi phiếu thu tiền mặt mô phỏng. Gia hạn tạo kỳ kế tiếp, không ghi đè kỳ cũ.
4. **Vận hành**: nhận biển vừa có vé tháng, kiểm phí bằng 0; trả xe và kiểm chỗ tăng. Xe mẫu có vé tháng còn hạn: `59A-888.88` / Ô tô. Xe mẫu vé đã hết hạn: `59B1-555.55` / Xe máy.
5. Nhận một xe khác không có vé tháng. Xem giờ vào, thời gian gửi, phí; trong **Cách thử nhanh** tăng đồng hồ thêm một giờ; xác nhận thu rồi cho xe ra. Thử nhận trùng hoặc trả xe còn nợ để xem thông báo.
6. **Lịch sử gửi xe**: nhập biển vừa thử, chọn ngày 23/09/2026 và trạng thái. Mở chi tiết xem phí, đơn giá lúc nhận và phiếu thu.
7. **Thu chi & báo cáo**: chọn 7 ngày để xem dữ liệu mẫu 17–23/09/2026; chọn AI và lần lượt thử Báo cáo ngày, Báo cáo tuần, Hỏi đáp, Gợi ý nhân sự. Mở dữ liệu đầu vào đã chốt và xem lại phân tích cũ.
8. Thử AI kỳ 7 ngày kết thúc **01/07/2026** để thấy dữ liệu rỗng; thử câu hỏi trống để thấy yêu cầu nhập lại. Nội dung mô phỏng không tự tạo cao điểm hoặc số nhân viên.
9. Thử quyền Nhân viên: nhận/trả xe và xem báo cáo vận hành được; không có sửa danh mục/tài khoản/doanh thu tổng. Đổi Admin để thấy toàn bộ khả năng Manager và quản lý tài khoản/nhật ký/cấu hình.
10. Customer: tra xe `59A-123.45`, thanh toán online mô phỏng; hoặc xe `59B1-678.90` và mã vé `VE-4096` để xác minh. Xe đạp dùng `XD-001`. Đặt chỗ trước là tùy chọn, chỉ Customer tạo; không bắt buộc để gửi xe.

## Chạy lại và kiểm chứng

Từ Git root `ParkingAI`:

```powershell
node frontend/prototypes/parking-simple/build.mjs
node --test frontend/prototypes/parking-simple/engine.test.cjs frontend/prototypes/parking-simple/analytics.test.cjs
.venv\Scripts\python.exe -X utf8 frontend/prototypes/parking-simple/review_browser.py
```

Browser harness dùng Chrome Windows riêng, cần server tĩnh cổng 8790; không truy cập API/provider. Nếu chưa có server:

```powershell
.venv\Scripts\python.exe -m http.server 8790 --bind 127.0.0.1 --directory frontend/prototypes/parking-simple
```

Kết quả mới và giới hạn tại [SDLC_EVIDENCE.md](SDLC_EVIDENCE.md). HTML được build chỉ từ các file trong thư mục này.

## Ranh giới

- Đủ các màn/luồng để duyệt yêu cầu ở mức **demo tương tác**. Đây chưa phải nghiệm thu hệ thống FastAPI/CSDL/AI thật hoặc bảo mật.
- Mọi dữ liệu nằm trong RAM của một tab. Khởi đầu 23/09/2026 lúc16:30, lịch sử giả lập nhiều ngày; không có dữ liệu khách thực. “Làm lại” hoặc tải trang sẽ reset.
- Chatbot/phân tích dùng quy tắc JavaScript và dữ liệu mẫu, có nhãn AI mô phỏng. Không gửi dữ liệu tới model. Camera/QR cũng mô phỏng, không dùng QR này để chuyển tiền.
- Các phần mở rộng vẫn được giữ để xem: đặt chỗ, camera mô phỏng, thanh toán mô phỏng, tiếp nhận hỗ trợ. Quy trình hoàn tiền thực chưa nằm trong phạm vi đề gốc này.
- Chỉ chuyển sang sửa/tích hợp ứng dụng thật sau khi người dùng duyệt demo. Các nháp cục bộ ứng dụng thật từ lượt trước không được sửa thêm trong đợt này.
