# Nghiên cứu mở rộng ParkingAI: thanh toán vé tháng và camera ALPR

Ngày đối chiếu tài liệu: **07/09/2026**. Phạm vi: lập kế hoạch, chưa tích hợp nhà cung cấp, chưa thử giao dịch hoặc đo camera thực tế. Phần **Đã xác minh** dựa trên tài liệu chính thức; phần **Đề xuất** là thiết kế cho ParkingAI, chưa phải tính năng đã triển khai. Bảy nguồn được dẫn ngay cạnh nội dung liên quan.

## Thanh toán vé tháng: căn cứ kỹ thuật

| Chủ đề | Đã xác minh từ tài liệu chính thức | Hệ quả cho kế hoạch |
|---|---|---|
| payOS: xác thực | Chữ ký thanh toán dùng HMAC-SHA256 với checksum key và dữ liệu sắp xếp theo tên trường. Ví dụ webhook xác minh `data` với `signature`. Tài liệu phân biệt cách ký `payment-requests` và `payouts`. [payOS — kiểm tra signature](https://payos.vn/docs/tich-hop-webhook/kiem-tra-du-lieu-voi-signature/) | Xác minh tại backend bằng đúng quy tắc của API thanh toán; không chuyển checksum key ra trình duyệt hoặc dùng thuật toán của API chi hộ. |
| payOS: tra cứu, hủy, hoàn | Có API lấy link theo mã đơn hoặc ID, trả `amount`, `amountPaid`, `amountRemaining`, `status`; có API hủy link. Trong trang API đã rà soát, chưa xác minh được API hoàn tiền gắn trực tiếp với giao dịch thu. [payOS — API](https://payos.vn/docs/api/) | Dùng tra cứu máy chủ để đối chiếu. Không coi hủy link là hoàn tiền; khả năng hoàn tự động cần xác nhận riêng với payOS trước khi đưa vào phạm vi cam kết. |
| VNPAY: nhận kết quả | IPN yêu cầu HTTPS; kiểm tra checksum, mã đơn, số tiền và trạng thái trước cập nhật. Mẫu 2.1.0 dùng HMAC-SHA512; `vnp_Amount` bằng số VND nhân 100. Return URL chỉ hiển thị kết quả, không cập nhật giao dịch. [VNPAY — tích hợp PAY](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html) | Adapter phải đổi đơn vị tiền bằng số nguyên. Chỉ thông tin đã xác thực từ máy chủ được phép kích hoạt vé. |
| VNPAY: gửi lại | IPN có cơ chế gọi lại theo mã phản hồi; tài liệu hiện nêu tối đa 10 lần, cách nhau 5 phút. [VNPAY — tích hợp PAY](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html) | Callback lặp phải trả kết quả phù hợp mà không tạo thêm vé hoặc phiếu thu. |
| VNPAY: đối chiếu, hoàn | Có `querydr` và `refund`; hoàn toàn phần/một phần được mô tả. `vnp_RequestId` phải phân biệt các yêu cầu. `vnp_ResponseCode=00` của QueryDr nghĩa là truy vấn thành công; kết quả thanh toán ở `vnp_TransactionStatus`. Tài liệu cũng có trạng thái hoàn đang xử lý và đã gửi ngân hàng. [VNPAY — QueryDr và Refund](https://sandbox.vnpayment.vn/apis/docs/truy-van-hoan-tien/querydr%26refund.html) | Phân biệt tiếp nhận yêu cầu, thanh toán thành công và hoàn tiền hoàn tất; đối chiếu cả phản hồi có chữ ký. |

**Chưa xác minh:** phí, thời gian cấp merchant, điều kiện thương mại của tài khoản ParkingAI, quyền hoàn tiền được cấp, thời gian quyết toán và hạn mức. VNPAY có cấu hình sandbox trong tài liệu PAY; khả năng kiểm thử của tài khoản payOS cụ thể cần kiểm tra riêng. Những thông tin này không được dùng làm giả định cho dự toán hoặc ngày triển khai.

## Thiết kế thanh toán đề xuất cho ParkingAI

1. Tạo **đơn mua/gia hạn vé tháng** riêng, lưu khách hàng, xe, thẻ, kỳ sử dụng và số tiền do server xác định. Chưa cấp quyền lợi vé và chưa ghi nhận đã thu chỉ vì tạo được link. Một mã đơn ánh xạ rõ tới giao dịch nhà cung cấp.
2. Backend nhận webhook/IPN, xác thực chữ ký rồi đối chiếu nhà cung cấp/kênh merchant, mã đơn, mã giao dịch, tiền tệ, số tiền và kết quả. Với thiếu/thừa tiền, đơn hết hạn, kỳ vé xung đột hoặc dữ liệu không khớp: chuyển sang hàng chờ xử lý, không tự cấp vé.
3. Lưu sự kiện nhận được và khóa chống trùng theo nhà cung cấp + mã giao dịch. Dùng giao dịch DB để chuyển đơn sang đã thanh toán, tạo kỳ vé và ghi phiếu thu đúng một lần; callback, tra cứu định kỳ và thao tác quản trị cùng đi qua một hàm chuyển trạng thái.
4. Return URL của cả hai adapter chỉ mở màn hình chờ/tra cứu trạng thái từ backend. Không tin tham số trên trình duyệt hoặc ảnh chụp “đã chuyển khoản” để gia hạn vé. Đây là quy tắc thiết kế của ParkingAI, áp dụng thống nhất với mô hình xác thực và tra cứu nêu trên.
5. Chạy đối chiếu các đơn chưa rõ kết quả bằng API máy chủ; giao dịch timeout được giữ ở trạng thái chưa xác định. So sánh tổng thu/hoàn nội bộ với dữ liệu nhà cung cấp và sao kê theo quy trình được thống nhất khi mở merchant; tra cứu một giao dịch chưa tương đương đối soát quyết toán toàn kỳ.
6. Hoàn tiền có yêu cầu, người duyệt, lý do và trạng thái riêng. Chỉ ghi nhận hoàn tất khi có bằng chứng kết quả; giữ phiếu thu gốc và ghi chứng từ điều chỉnh. Với payOS, để hoàn tiền ở phạm vi xử lý có kiểm soát cho đến khi xác minh được khả năng API phù hợp; không tự thay bằng API chi hộ.

**Bài kiểm thử cần có trước pilot:** chữ ký sai; đúng chữ ký nhưng sai tiền/mã đơn/kênh; webhook lặp và đến trễ; mất callback nhưng tra cứu thấy đã trả; callback chạy đồng thời với job đối chiếu; khách thanh toán sau khi kỳ vé không còn hợp lệ; hoàn một phần, hoàn trùng và timeout khi hoàn. Không chạy các ca này bằng tài khoản production.

**Lựa chọn đề xuất:** chỉ tích hợp một nhà cung cấp trong pilot. payOS là ứng viên cho luồng link/QR và xác nhận chuyển khoản; VNPAY có tài liệu rõ cho cả truy vấn và hoàn tiền. Chốt lựa chọn sau khi xác nhận merchant, phí và quy trình hoàn, không khẳng định bên nào rẻ hơn hay đăng ký nhanh hơn.

## Camera ALPR: căn cứ kỹ thuật

**Đã xác minh:** PaddleOCR tách mô-đun phát hiện vùng chữ và nhận dạng chữ, có điểm tin cậy đầu ra; tài liệu hỗ trợ suy luận CPU/GPU và có các mô hình mobile hướng tới thiết bị tại biên. Đây là OCR tổng quát, không phải bằng chứng một cấu hình đã nhận dạng được biển số ở bãi của ParkingAI. [PaddleOCR — OCR pipeline](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)

Tài liệu PP-OCRv5 đa ngôn ngữ liệt kê Vietnamese với mã `vi`; `latin_PP-OCRv5_mobile_rec` có Vietnamese trong nhóm ngôn ngữ hỗ trợ. Cần ghim phiên bản thư viện và tên model khi thử; không suy ra mọi model mặc định đều hỗ trợ tiếng Việt giống nhau. [PaddleOCR — PP-OCRv5 multilingual](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md)

**Đề xuất pipeline:** camera → chọn khung hình phù hợp → phát hiện vùng biển số → cắt/chỉnh góc → OCR → chuẩn hóa ký tự và kiểm tra định dạng → gom kết quả nhiều khung hình → nhân viên xác nhận → API vào/ra hiện có. Phát hiện biển số là một bước riêng với phát hiện dòng chữ; cần tập ảnh gán nhãn hoặc detector có nguồn gốc, giấy phép và chất lượng được kiểm tra. Chưa chọn một bộ trọng số cụ thể.

**Đề xuất xử lý tại bãi:** chạy dịch vụ suy luận trên máy tại bãi, đóng gói model để không phải tải lại khi mất Internet; ưu tiên gửi kết quả và ảnh biển đã cắt thay vì toàn bộ video lên backend. Chọn CPU/GPU sau benchmark trên camera thật. Dịch vụ có hàng đợi giới hạn, trạng thái camera/model, cơ chế khởi động lại và đường nhập biển số thủ công. Ảnh lưu có thời hạn và phân quyền; thời hạn cụ thể cần được thống nhất.

Giai đoạn đầu chỉ gợi ý biển số cho nhân viên. Kết quả không chắc chắn hoặc nhiều ứng viên phải chuyển sang xác nhận thủ công; OCR không được tự ghi đã thanh toán hoặc bỏ qua bước xác nhận xe ra. Đo độ đúng **toàn bộ biển số**, nhầm xe, sự kiện trùng và độ trễ p95; chia mẫu theo ngày/đêm, mưa/chói, biển một/hai dòng, xe máy/ô tô và góc camera. Chưa có dữ liệu để cam kết phần trăm chính xác, FPS hoặc cấu hình phần cứng.

## Nếu dùng Ultralytics YOLO

**Đã xác minh theo hướng dẫn của nhà cung cấp:** Ultralytics công bố lựa chọn AGPL-3.0 và Enterprise; hướng dẫn hãng yêu cầu Enterprise cho việc sử dụng không công khai dự án theo điều kiện AGPL của họ, gồm hệ thống nội bộ, SaaS và thiết bị edge. Không xem việc chạy tại bãi hay xuất model sang định dạng khác là cách mặc nhiên loại bỏ nghĩa vụ giấy phép. [Ultralytics — Licensing](https://www.ultralytics.com/license)

**Đề xuất:** trước khi chọn Ultralytics cho detector biển số, ghi rõ thư viện, trọng số, dữ liệu huấn luyện và phạm vi phân phối; xác định cách tuân thủ hoặc lấy điều khoản Enterprise phù hợp. Nếu dự án không chọn hướng đó, khảo sát detector khác với giấy phép tương thích. Đây là điều kiện chọn công nghệ, chưa phải quyết định mua giấy phép hoặc triển khai YOLO.
