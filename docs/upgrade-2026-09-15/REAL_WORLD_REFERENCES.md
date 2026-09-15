# Tham khảo hệ thống bãi đỗ xe thực tế

Ngày truy cập: **15/09/2026**. Phạm vi áp dụng: **một bãi duy nhất, phục vụ đồ án**; giữ đầy đủ quản lý nghiệp vụ và AI phân tích theo đề bài, sau đó thêm cổng khách hàng, QR thanh toán, camera đọc biển số và computer vision.

Đã mở các trang chính thức dưới đây và đọc nội dung công khai. Đây là khảo sát luồng sản phẩm/tài liệu hướng dẫn; chưa đăng nhập tài khoản khách hàng, mua vé, thực hiện thanh toán hoặc thử thiết bị tại bãi. Tính năng do nhà cung cấp công bố không phải kết quả đo kiểm độc lập. Những quyết định thiết kế dành cho ParkingAI được ghi riêng ở phần 2–4.

## 1. Năm hệ thống được tham khảo

| Hệ thống / loại nguồn | Chức năng có trong nguồn chính thức | Bài học áp dụng cho ParkingAI |
|---|---|---|
| **JustPark** — website khách hàng và trung tâm trợ giúp | Tìm chỗ theo thời gian; lựa chọn giờ/ngày hoặc tháng; nhận hướng dẫn vào bãi; xem và sửa đặt chỗ qua tài khoản. [Hướng dẫn đặt chỗ](https://www.justpark.com/how-it-works). Đặt tháng yêu cầu thêm xe, chọn gói, trả tiền và quản lý đơn tại My Bookings. [Hướng dẫn vé tháng](https://support-uk.justpark.com/hc/en-gb/articles/360026638014-Monthly-Rolling-Booking-how-it-works-how-to-book). | Tổ chức luồng rõ ràng: chọn gói → xe → thời gian → xem giá → trả tiền → vé/đơn của tôi. Bỏ tìm kiếm nhiều địa điểm vì đồ án chỉ có một bãi. |
| **Q-Park** — nhà khai thác bãi xe; website hướng dẫn khách | Hướng dẫn thêm tài khoản, biển số và phương thức thanh toán; ANPR hỗ trợ vào/ra ở bãi tương thích; ứng dụng nhận biên nhận điện tử. [Q-Park App](https://www.q-park.co.uk/en-gb/products/q-park-app/rewards-mobile-app/). My Q-Park cho phép cập nhật hồ sơ, xem và trả hóa đơn; vé dài hạn liên kết biển số. [Hướng dẫn Season Ticket](https://www.q-park.co.uk/en-gb/season-ticket-how-to/london/). | Một tài khoản quản lý xe, vé, đặt chỗ và hóa đơn. Mỗi vé gắn quyền sử dụng cụ thể; ứng dụng cần biểu diễn quan hệ xe–vé–lượt gửi. |
| **SKIDATA** — trang giải pháp cho đơn vị vận hành | Công bố khả năng kết hợp nhận dạng biển số với vé hoặc RFID, phục vụ nhiều nhóm khách; bổ sung LPR vào hệ thống vé có sẵn. [Access Control & LPR](https://www.skidata.com/en-gb/solutions/mobility-parking/access-control-lpr). | Camera là kênh nhập liệu bổ sung. Giữ thao tác vé/nhập biển số và xử lý ngoại lệ cho nhân viên. |
| **Futech iParking** — trang giải pháp của nhà cung cấp Việt Nam | Mô tả camera chụp biển số/toàn cảnh ở cổng, đối chiếu lúc ra và cảnh báo sai biển số; phí theo lượt/tháng; xuất báo cáo Excel; kiosk hỗ trợ QR, ví điện tử hoặc thẻ. [Giải pháp iParking](https://www.futech.vn/blogs/giai-phap-1/bai-xe-thong-minh-iparking). | Màn hình cổng cần ảnh vào/ra, biển số, phí và cảnh báo; hồ sơ lượt gửi liên kết giao dịch thu tiền. |
| **Parquery** — trang sản phẩm computer vision và hướng dẫn kỹ thuật | Phân tích ảnh để nhận biết xe trong vị trí đỗ, trả kết quả qua API/dashboard. [Cách hoạt động](https://parquery.com/how-it-works/). Tài liệu camera đề cập góc nhìn, che khuất, điện và mạng; có thể xử lý tại máy chủ cục bộ. [Camera particulars](https://parquery.com/camera-particulars/). | Tách mô-đun nhận biết ô có xe khỏi OCR biển số; demo một camera cố định và các ô đã đánh dấu là phạm vi hợp lý. |

### Những chi tiết đáng học thêm

- **Vé tháng có điều kiện sử dụng:** JustPark phân biệt gói cả tuần, ngày làm việc hoặc số ngày chọn trước; nguồn cũng mô tả thời hạn và cơ chế hủy. Với đồ án, chọn một gói tháng đơn giản, công khai thời điểm bắt đầu/kết thúc và quy tắc gia hạn. Không mặc nhiên sao chép tự động trừ tiền. [JustPark Monthly](https://support-uk.justpark.com/hc/en-gb/articles/360026638014-Monthly-Rolling-Booking-how-it-works-how-to-book).
- **Xe trong hồ sơ và quyền vào bãi là hai khái niệm:** Q-Park hướng dẫn tài khoản có nhiều biển số nhưng một vé được phân cho một biển số tại thời điểm sử dụng; đổi xe có điều kiện khi xe trước không ở trong bãi. [Q-Park Season Ticket](https://www.q-park.co.uk/en-gb/season-ticket-how-to/london/).
- **Góc camera ảnh hưởng dữ liệu:** Parquery khuyên góc nhìn cao, nhìn phía trước/sau xe để giảm việc xe che nhau. Vì vậy phải đo chất lượng với góc camera và dữ liệu demo của đồ án, thay vì dùng chỉ số quảng cáo làm kết quả nghiệm thu. [Parquery camera particulars](https://parquery.com/camera-particulars/).

## 2. Phương án áp dụng cho một bãi đồ án

Các mục dưới đây là **đề xuất thiết kế cho ParkingAI**, không phải tuyên bố rằng mọi nhà cung cấp đều hoạt động theo cách này.

### Lõi phải giữ nguyên và hoàn thiện trước

- Hai vai trò nội bộ: quản lý và nhân viên, được kiểm soát ở API và giao diện.
- Khu vực, vị trí, loại xe, phương tiện, bảng giá, vé và lượt vào/ra.
- Ghi giờ vào/ra; tính phí theo loại xe và thời gian; tra cứu theo biển số/khoảng thời gian.
- Chỗ trống theo khu; vé tháng hoặc hồ sơ khách quen; thống kê lưu lượng/doanh thu/cao điểm.
- AI sinh báo cáo ngày/tuần, trả lời quản trị từ dữ liệu đã tổng hợp, gợi ý nhân sự theo cao điểm. Camera/OCR không thay thế ba chức năng AI này.
- Kiểm thử xe vào/ra, phí, chỗ trống và AI; minh chứng prompt → code → test trong KT1–KT3 và tài liệu cuối kỳ.

### Mở rộng thành ba khu vực sử dụng

| Khu vực | Màn hình chính | Luồng nghiệm thu cần nhìn thấy |
|---|---|---|
| **Khách hàng** | Thông tin bãi/bảng giá/chỗ trống; đăng nhập; xe của tôi; mua vé giờ/ngày/tháng; đặt chỗ; đơn/vé; hóa đơn/biên nhận | Chọn xe và khoảng gửi → xem giá → giữ chỗ tạm → thanh toán → nhận vé/đơn xác nhận → vào/ra → tra cứu chứng từ |
| **Nhân viên** | Bảng cổng vào/ra; camera; tra cứu vé/biển số; sơ đồ bãi; thu tiền; ngoại lệ | OCR gợi ý biển số → xác nhận nhận xe → cấp/chọn ô → xuất phí → xác nhận thanh toán → kết thúc lượt và trả ô |
| **Quản lý** | Cấu hình danh mục/bảng giá/quyền; lượt gửi; vé tháng/khách hàng; thu–hoàn; báo cáo; AI; nhật ký | Đối chiếu lượt gửi, chỗ và tiền → lọc báo cáo → hỏi AI với phạm vi ngày/tuần → xem căn cứ và gợi ý nhân sự |

### Phân biệt các trạng thái trước khi bổ sung chức năng

1. **Vé/gói:** quyền sử dụng, thời hạn và điều kiện. Vé tháng không tự động giữ một ô cố định nếu gói không ghi điều đó.
2. **Đặt chỗ:** giữ quyền đỗ trong khoảng thời gian tương lai; có hạn thanh toán, hạn đến và quy tắc hủy. Nếu sản phẩm cho chọn ô cụ thể, phải khóa lịch của đúng ô đó.
3. **Lượt gửi:** xe đã thực sự vào bãi; kết thúc khi xe ra. Một vé tháng có thể tạo nhiều lượt, nhưng không cho cùng quyền sử dụng chiếm nhiều ô ngoài điều kiện gói.
4. **Hóa đơn nội bộ/biên nhận:** khoản phải thu và khoản đã thu. Tách chúng khỏi một lần hiển thị QR. Phạm vi đồ án cần gọi đúng là phiếu tính phí/biên nhận nếu chưa tích hợp dịch vụ hóa đơn điện tử thuế.
5. **Quan sát camera:** dữ liệu nhận dạng/chiếm chỗ có thời điểm và độ tin cậy; có thể khác trạng thái nghiệp vụ. Chênh lệch tạo cảnh báo và quy trình xác nhận.

## 3. Luồng mở rộng và ranh giới cần kiểm thử

| Mở rộng | Phương án đồ án đề xuất | Tình huống lỗi quan trọng |
|---|---|---|
| **QR nhận tiền** | Mỗi khoản thu có mã đơn/số tiền/trạng thái. Chỉ ghi đã thanh toán sau thông báo được xác thực từ phía cung cấp hoặc thao tác xác nhận có quyền trong chế độ đối soát thủ công. Thể hiện rõ mô phỏng và kết nối thật. | QR hết hạn; trả thiếu/thừa; thông báo lặp hoặc đến muộn; tải lại trang; khách bấm “đã trả” nhưng hệ thống chưa nhận được tiền |
| **Đặt chỗ trước** | Giữ chỗ trong thời gian ngắn để thanh toán; xác nhận xong mới thành đặt chỗ hợp lệ; có đến nhận chỗ, hủy và không đến. Số chỗ có thể đặt trong tương lai tính theo lịch, không lấy trực tiếp số ô trống hiện tại. | Hai khách đặt cùng ô/cùng thời gian; khách cũ ra muộn; đơn hết hạn nhưng thanh toán tới sau; khách vãng lai dùng ô đang được giữ |
| **Vé giờ/ngày/tháng** | Công bố rõ gói tính theo giờ, theo 24 giờ hay theo ngày lịch; áp dụng một múi giờ; lưu giá đã chốt. Bắt đầu từ gia hạn chủ động. | Giao ngày/tháng; hết hạn khi đang đỗ; gửi vượt thời gian; đổi xe; thay bảng giá sau khi mua |
| **Camera OCR tại cổng** | Chụp ảnh hoặc nhận khung hình; trả biển số gợi ý + mức tin cậy + ảnh; nhân viên sửa/xác nhận; lưu kết quả cuối và người sửa. | Biển mờ/che/ký tự gần giống; đọc lặp cùng xe; mất camera; hai xe sát nhau; biển ra không khớp biển vào |
| **Computer vision chỗ đỗ** | Camera cố định → vùng đa giác của từng ô → nhận biết có xe/không rõ/trống → quan sát có timestamp. Đối chiếu trạng thái hệ thống trước khi xác nhận điều chỉnh. | Che khuất; mất khung hình; ánh sáng yếu; xe đỗ lệch ô; quan sát cũ; camera mất kết nối |
| **AI phân tích** | Backend tính số liệu; AI diễn giải dữ liệu có phạm vi thời gian và nguồn. Gợi ý nhân sự phải nêu giả định, không tự sinh lịch phân ca thật. | Dữ liệu rỗng/sai; doanh thu âm do hoàn tiền; hỏi ngoài dữ liệu; yêu cầu bịa số; mô hình timeout hoặc không khả dụng |

## 4. Thứ tự triển khai phù hợp

1. **Hoàn thiện lõi và chứng minh không hồi quy:** một bãi, đầy đủ quản lý, bảng giá, vào/ra, chỗ trống, vé tháng, thống kê và ba chức năng AI.
2. **Portal khách hàng + đơn/phiếu tính phí + QR:** cùng một nguồn dữ liệu với màn hình nhân viên; có luồng mua vé giờ/ngày/tháng và lịch sử giao dịch.
3. **Đặt chỗ theo thời gian:** đồng bộ giữ chỗ, thanh toán, đến bãi, phân ô, hủy và hết hạn.
4. **OCR tại cổng:** đưa kết quả nhận dạng vào luồng đã ổn định; vẫn cho vận hành khi camera lỗi.
5. **CV chỗ đỗ:** một khu demo có bộ dữ liệu kiểm thử riêng; hiển thị quan sát camera và sai lệch; chỉ mở rộng sau khi có kết quả đo thực tế.
6. **Nghiệm thu tổng thể:** demo cả ba vai trò; chuẩn bị dữ liệu tái lập, test ngoại lệ, minh chứng SDLC, hướng dẫn chạy và phương án sao lưu/khôi phục.

Chưa cần cho mục tiêu này: marketplace nhiều chủ bãi, tìm bãi toàn thành phố, giá động theo thị trường, chia doanh thu nhiều đối tác, ví tiền tự quản, điều khiển phần cứng barrier thương mại hoặc ứng dụng di động riêng. Một website responsive với ba khu vực sử dụng đủ thể hiện hệ thống hoàn chỉnh trong phạm vi đã chọn.

## 5. Giới hạn của khảo sát

- Website JustPark/Q-Park cung cấp luồng và hướng dẫn cho khách; SKIDATA/Futech/Parquery chủ yếu là trang sản phẩm/giải pháp. Không coi trang giới thiệu của nhà cung cấp là màn hình quản trị đã được thử sử dụng.
- Chỉ dùng nội dung đọc được ở các trang chính thức đã dẫn. Chưa xác nhận cấu hình, giá, điều kiện hợp đồng hay chất lượng của bất kỳ hệ thống nào cho bãi cụ thể tại Việt Nam.
- Không đánh giá thư viện OCR/model, API thanh toán hay phần cứng cụ thể trong tài liệu này. Cần kiểm tra riêng trước khi chọn công nghệ; kết quả OCR/CV phụ thuộc dữ liệu và thiết bị của đồ án.
- Không dùng các tuyên bố quảng cáo về độ chính xác, chống thất thoát tuyệt đối hoặc tốc độ làm tiêu chí đã đạt của ParkingAI.
- Tài liệu này không khẳng định tính năng tương ứng đã tồn tại hay hoàn tất trong repository. Phải đối chiếu code và kiểm thử hiện tại trong kế hoạch triển khai.
