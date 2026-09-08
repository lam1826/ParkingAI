# Hướng dẫn chạy và trình diễn ParkingAI

## 1. Mục đích

Bản mở rộng phục vụ đồ án: khách đăng ký vé tháng, thử thanh toán bằng QR ngẫu nhiên, đặt chỗ và dùng điện thoại chụp biển số. Không cần tài khoản ngân hàng, payOS/VNPAY, camera mạng hoặc GPU. Lịch sử mẫu được tạo riêng và đánh dấu DEMO; không phải số liệu thu thập từ bãi xe thật.

## 2. Chuẩn bị và khởi động

Mở PowerShell tại thư mục `ParkingAI`. Cần Python 3.11–3.12 và Node.js 22.12 trở lên.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Set-Location frontend
npm.cmd ci
Set-Location ..
```

Cài nhận diện trên CPU nếu cần trình diễn YOLO/OCR:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-vision.txt
.venv/Scripts/python.exe edge/download_vision_model.py
.venv/Scripts/python.exe edge/download_demo_images.py
```

Khởi động:

```powershell
./scripts/start_demo.ps1
```

Truy cập `http://localhost:8765`. Script build giao diện và tạo DB mới ở `backend/artifacts/demo/parking-demo.db` nếu chưa có. Những lần sau giữ lại kết quả bạn đã thử. Cơ sở dữ liệu phải có tệp `.demo.json` đi kèm; máy chủ demo từ chối DB không được đánh dấu. Không sửa `backend/.env` và không dùng DB vận hành. Nhấn `Ctrl+C` để dừng.

| Tài khoản | Vai trò trong demo |
| --- | --- |
| `admin_demo` | Quản trị toàn hệ thống, xem và cấu hình cả hai bãi |
| `manager_demo` | Quản lý bãi A, duyệt hồ sơ và đơn của bãi A |
| `staff_demo` | Nhân viên bãi A, vận hành vào/ra và camera |
| `customer_demo` | Khách đã liên kết hồ sơ và có hai xe mẫu |

Mật khẩu khi tạo bằng `start_demo.ps1`: **`DemoParkingAI!2026`**. Đây là tài khoản thử nghiệm. Tham số `-DemoPassword` đổi mật khẩu lúc tạo DB mới, không đổi mật khẩu DB đã tồn tại. CLI `python -m expansion.demo_seed` dùng cùng mật khẩu mặc định này nếu không truyền `--password`.

Tạo bộ dữ liệu mới mà vẫn giữ bộ cũ:

```powershell
./scripts/start_demo.ps1 -Database "$PWD/backend/artifacts/demo/buoi-bao-ve.db"
```

Bộ mẫu có hai bãi, 32 vị trí, bốn gói vé, bốn camera điện thoại và 56 ngày lịch sử tổng hợp. Các lượt lịch sử mẫu có phí bằng 0; không tạo doanh thu giả để trình bày là doanh thu thật. Có một xe máy mẫu đang đỗ để thử cho xe ra. Kết quả bạn thao tác được lưu vào chính DB demo này.

## 3. Trình diễn cổng khách và QR

1. Đăng nhập `customer_demo`, mở **Bãi xe của tôi**. Xem biển số đã được duyệt, vị trí hiện tại, lịch sử và vé tháng.
2. Chọn **Đăng ký & QR**, chọn xe và gói đúng loại xe/bãi, bấm **Tạo đơn và mã QR**. Máy chủ quyết định giá và kỳ hiệu lực; mỗi đơn có mã ngẫu nhiên.
3. Dùng camera/ứng dụng quét QR để thấy chuỗi bắt đầu bằng `PARKINGAI-DEMO`. Chuỗi này là dữ liệu thử, không phải VietQR chuyển khoản.
4. Bấm **Giả lập thanh toán thành công**. Kiểm tra trạng thái đã cấp vé, vé tháng mới, chứng từ và thông báo. Thử gửi lại cùng kết quả không cấp thêm vé hoặc thu thêm tiền.
5. Tạo các đơn riêng để thử **Giả lập thất bại** và **Hủy thanh toán**. Các trạng thái này không kích hoạt vé. Đơn chờ quá hạn được xử lý bởi bảo trì tự động.
6. Trong **Lịch sử & chứng từ**, tải PDF. Chứng từ mô phỏng có nhãn DEMO. Giao dịch mô phỏng không cộng vào doanh thu thực hoặc tiền phải có khi chốt ca.
7. Mở đơn đã cấp vé và gửi lý do yêu cầu hoàn. Đăng nhập `manager_demo` hoặc `admin_demo`, mở **Khách & đơn vé → Yêu cầu hoàn**, xem thông tin và duyệt/từ chối. Duyệt hoàn mô phỏng ngừng kỳ vé; nếu xe đang dùng kỳ vé trong bãi, hệ thống yêu cầu xử lý lượt gửi trước.

Để thể hiện xác minh khách mới: đăng ký tài khoản khách, tạo hồ sơ mới hoặc yêu cầu liên kết hồ sơ có sẵn, gửi yêu cầu thêm xe. Quản lý mở **Khách & đơn vé → Xác minh khách & xe**, đối chiếu thông tin rồi duyệt. Không thể tự nhập ID khách khác để xem dữ liệu của họ. Chỉ những lượt được xác định quyền tại lúc xe vào mới được đưa vào lịch sử tự phục vụ; liên kết một xe không tự cấp quyền xem mọi lượt cũ của xe.

Khi gia hạn vé đã mua qua portal, tiếp tục tạo đơn tại **Đăng ký & QR** với gói đúng bãi. Luồng gia hạn vé tháng cũ sẽ từ chối vé này để tránh cấp kỳ mới sai phạm vi bãi.

## 4. Đặt chỗ, vào/ra và nhiều bãi

1. Khách mở **Đặt chỗ của tôi**, chọn bãi, xe, khoảng giờ và vị trí phù hợp. Đặt chỗ có hạn đến, có thao tác hủy. Vé tháng là quyền tính phí; quyền giữ vị trí được quản lý riêng.
2. Nhân viên bãi mở **Vận hành bãi → Đặt chỗ**, xác nhận **Xe đã đến**. Đây là thao tác ghi xe vào cho đặt chỗ đã có. Không ghi thêm lượt vãng lai cho cùng xe.
3. Thử hai xe cùng đặt một vị trí trong khoảng trùng nhau: hệ thống từ chối yêu cầu xung đột. Xe đang chiếm vị trí không bị tự giải phóng khi lịch đặt hết hạn.
4. Nếu chưa có chỗ, khách vào danh sách chờ. Nhân viên cấp vị trí khi phù hợp; lời mời tạo một đặt chỗ thực, gửi lại không tạo thêm đặt chỗ.
5. Với xe vãng lai, chọn **Xe vào / ra**, điền biển số, loại xe và vị trí còn nhận được. Khi ra, tìm lượt, bấm **Xem phí / xe ra**, đọc báo phí và xác nhận phương thức đã thu. Báo phí thay đổi hoặc hết hạn phải được kiểm tra lại.
6. Quản lý có thể cấp **Bảo đảm chỗ**, tạo đội xe và liên kết thành viên/xe. Đây là quản lý phạm vi đội xe và số liệu hoạt động; chưa phải hệ thống xuất hóa đơn doanh nghiệp.
7. Admin có thể tạo bãi, khu vực, vị trí và thành viên theo bãi. Nhân viên bãi A không xem hoặc xử lý dữ liệu bãi B. Khi có nhiều bãi, chức năng quản trị cũ có dữ liệu toàn hệ thống chỉ mở cho admin.

Chi tiết nghiệp vụ và giới hạn: [Bãi, đặt chỗ và đội xe](SITES_RESERVATIONS.md), [Cổng khách và thanh toán](PORTAL_PAYMENTS.md).

Tạo khu vực bằng **Vận hành bãi → Cấu hình bãi** để chọn đúng bãi; API tạo khu cũ bị chặn khi có nhiều bãi. Khi đã có bãi trong hệ thống, API v1 nhận xe cũng yêu cầu chọn vị trí. Với danh sách chờ đã qua giờ bắt đầu nhưng chưa hết giờ kết thúc, nhân viên vẫn có thể cấp chỗ từ thời điểm hiện tại; yêu cầu đã hết hạn phải tạo lại với khoảng giờ mới.

Các bảng đặt chỗ, bảo đảm chỗ, danh sách chờ và lượt gửi hiển thị 25 mục mỗi trang, có bộ lọc trạng thái; lọc theo bãi/trạng thái được thực hiện tại máy chủ nên khách có nhiều đặt chỗ ở nhiều bãi vẫn thấy đủ mục của bãi đang chọn. Đổi bộ lọc luôn quay về trang đầu. Mỗi bảng tải và báo lỗi riêng: nếu một API lỗi, các bảng khác vẫn giữ dữ liệu và bảng lỗi có nút **Thử lại**; thao tác ghi chỉ làm mới các phần liên quan (nhận xe → lượt gửi và chỗ trống; thanh toán mô phỏng → đơn, vé, chứng từ, thông báo).

Nếu xe đã đặt chỗ ra trước giờ kết thúc, hệ thống ghi nhận xe đã ra nhưng vẫn giữ khoảng đặt đến giờ kết thúc. Khi nhận xe vãng lai tiếp theo, chọn vị trí được hiển thị còn nhận xe; chỗ trống vật lý có thể vẫn được giữ. Một mã đặt chỗ hiện chỉ dùng cho một lượt đến, chưa hỗ trợ quay lại bằng cùng mã.

## 5. Chụp biển số bằng điện thoại

```powershell
./scripts/start_demo.ps1 -Lan
```

Kết nối điện thoại và laptop cùng Wi-Fi, mở địa chỉ `http://<IP-laptop>:8765` được script in ra. Nếu Windows hỏi mạng cho Python, chỉ cho phép mạng riêng đang dùng để trình diễn. Mạng khách có chế độ cô lập thiết bị có thể chặn kết nối. Không cần mở cổng router ra Internet.

1. Đăng nhập `staff_demo`, chọn **Camera & biển số**, bãi A và camera cổng vào/cổng ra.
2. Bấm **Chụp bằng điện thoại** hoặc **Chọn ảnh từ máy**. Trình duyệt nhận JPEG/PNG/WebP tối đa 20 MB, chuyển thành JPEG cạnh dài tối đa 1.600 pixel và gửi dưới 2 MB. HEIC cần chuyển sang JPEG trước. Việc mở camera hay trình chọn ảnh phụ thuộc điện thoại.
3. Đọc gợi ý OCR và xem khung vùng biển trên ảnh. Sửa ký tự sai rồi xác nhận. Camera cổng vào điền biển số vào biểu mẫu nhận xe; camera cổng ra điền biển số vào tra cứu. Nhân viên vẫn xác nhận nghiệp vụ ở bước kế tiếp.
4. Thử ảnh mờ/không có biển để thấy kết quả cần nhập thủ công; thử từ chối ảnh. Không có biển dự đoán giả khi model không nhận được.

Ảnh lưu riêng theo quyền bãi, loại bỏ EXIF/vị trí GPS và có thời hạn lưu mặc định 24 giờ. Máy chủ demo chạy bảo trì đơn/thông báo/xóa ảnh hết hạn mỗi 30 giây. Muốn trình diễn quy trình nhập tay mà không dùng model, chạy `-NoVision`.

YOLO đã được thử trên ảnh xe thật và tìm được vùng biển, nhưng OCR có trường hợp đọc sai; chưa có số đo độ chính xác biển Việt Nam. Xem [cài đặt, ảnh mẫu, giấy phép và kết quả YOLO/OCR](VISION_FORECAST.md) để trình bày đúng giới hạn khi bảo vệ.

## 6. Dự báo và phương án nhân sự

Mở **Dự báo & điều hành**, chọn bãi và khoảng dự báo. Dữ liệu mẫu có 56 ngày giúp trình diễn biểu đồ, khoảng ước lượng và MAE kiểm tra theo thời gian. Trên bãi mới chưa đủ 42 ngày, hệ thống báo thiếu dữ liệu. Không lấy kết quả trên lịch sử tổng hợp làm bằng chứng mô hình dự báo tốt ở bãi thật.

Khối **Độ phủ dữ liệu** cho biết số ngày/giờ có bản ghi xe vào, số giờ được điền 0 và mức đầy đủ quan sát. Hệ thống không có nhật ký hoạt động của nguồn ghi nhận nên mức đầy đủ luôn là "Chưa xác định": không kết luận giờ không có bản ghi là mất dữ liệu hay thật sự vắng xe. Cột "Tuần có bản ghi" trong bảng dự báo cho biết mỗi ước lượng dựa trên bao nhiêu tuần tham chiếu thực sự có xe. Lịch sử thưa được cảnh báo riêng.

Nhập thời gian xử lý mỗi xe, mức sử dụng năng lực và số nhân viên cho phép để tính phương án. Giá trị ban đầu là giả định. Các cảnh báo vận hành có quy tắc và bằng chứng; nhân viên cần kiểm tra trước khi kết luận. Bản demo không gọi LLM trả phí; Gemini có sẵn trong sản phẩm được tắt bởi bộ chạy demo, còn thống kê, dự báo và OCR cục bộ vẫn hoạt động.

## 7. Các lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Sai mật khẩu | Dùng mật khẩu lúc tạo DB; DB cũ không tự đổi mật khẩu |
| Nhận diện chưa sẵn sàng | Cài `requirements-vision.txt`, chạy downloader model rồi khởi động lại |
| OCR đọc sai | Sửa tay sau khi đối chiếu ảnh; thử ảnh rõ nét hơn; không tự xác nhận biển sai |
| Máy chủ từ chối DB | Dùng DB do seeder tạo và giữ `.demo.json`; không gắn marker vào DB thật |
| Hết phiên sau khởi động lại | Đăng nhập lại; khóa phiên demo được tạo mới khi chạy server |
| Điện thoại không vào được | Kiểm tra cùng Wi-Fi, địa chỉ IPv4 đúng, tham số `-Lan`, mạng riêng và firewall |
| Cổng 8765 đang được dùng | Dừng phiên demo cũ nếu đang mở trong terminal, hoặc chạy `./scripts/start_demo.ps1 -Lan -Port 8766` và truy cập cổng mới |
| Không còn chỗ nhận xe | Xem xe đang đỗ, đặt chỗ/bảo đảm chỗ và loại xe; không giải phóng chỗ đang có xe bằng tay |
| Chưa thấy nhắc vé | Nhắc khi còn 7 hoặc 1 ngày hiệu lực; worker chạy mỗi 30 giây, không gửi email/SMS |

## 8. Kiểm tra và đóng gói

```powershell
.venv/Scripts/python.exe -m pytest -q
Set-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
Set-Location ..
.venv/Scripts/python.exe scripts/sync_source_snapshot.py --check
```

Không nộp `.env`, mật khẩu thật, token, DB cá nhân hoặc thư viện `.venv/node_modules`. Model và ảnh tải về nằm trong thư mục bị Git loại trừ; giữ script tải, SHA-256, thông tin nguồn/giấy phép và các tài liệu hướng dẫn. Trạng thái kiểm chứng cuối cùng được ghi tại [bảng trạng thái mở rộng](EXPANSION_IMPLEMENTATION_STATUS.md).

Ba kiểm thử trình duyệt có thể chạy lại từ thư mục dự án sau khi build và tải model/ảnh mẫu:

```powershell
.venv/Scripts/python.exe tests/browser/remote_hook_regression.py
.venv/Scripts/python.exe tests/browser/workspace_sections_regression.py
.venv/Scripts/python.exe tests/browser/expansion_uat.py
```

Cần Chrome cục bộ; mỗi runner dùng profile riêng. Hai bài component tạo lỗi HTTP có kiểm soát để kiểm tra thử lại/phân trang; UAT tạo database mới và chạy API thật tại cổng 18960. Không cần xóa DB demo đang có. Viewport 390×844 mô phỏng kích thước điện thoại, không thay việc thử thiết bị thật.

Khi một phần lỗi, dùng **Thử lại** tại phần đó. Gói vé/loại xe chưa tải được sẽ khóa biểu mẫu phụ thuộc nhưng giữ lịch sử và xe đã xác minh; thông báo lỗi tải không có nghĩa là chưa có gói vé. Khoảng lọc có thời điểm kết thúc không sau bắt đầu bị từ chối. Xe đổi chủ không tự nhận quyền bảo đảm chỗ của chủ cũ; nhân viên phải xử lý quyền cũ trước khi đặt mới.
