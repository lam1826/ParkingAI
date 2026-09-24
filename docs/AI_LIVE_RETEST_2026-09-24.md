# Kiểm tra AI thật ngày 24/09/2026

Kiểm tra trên FastAPI thật tại `http://127.0.0.1:8793`, DB một bãi có đánh dấu dữ liệu giả lập. Provider trả về model `gemini-3.6-flash`; không mock, không thay câu trả lời bằng mẫu dựng sẵn. Chỉ gửi số liệu tổng hợp/công khai của DB mẫu. Kết quả này không chứng minh dịch vụ bên ngoài luôn sẵn sàng.

## Kết quả và đối chiếu nội dung

| Ca | Kết quả thực tế | Đối chiếu với dữ liệu cung cấp |
| --- | --- | --- |
| Báo cáo ngày 24/09 | HTTP 201, 14,41 giây | 3 lượt vào, 2 lượt ra, tổng 5; thuần 10.000đ; cao điểm 08:00 có 2 vào/2 ra. Chỗ trống hiện tại 36/42 và 14,29% lấp đầy khớp snapshot 09:14; không gán thành tỷ lệ lịch sử. |
| Báo cáo tuần 18–24/09 | HTTP 201, 19,38 giây | 167 vào, 161 ra, tổng 328; thuần 1.075.000đ. 17:00 có 48 vào/48 ra; gộp 17:00–trước 19:00 có 80 vào/80 ra, ghi rõ cộng dồn cả kỳ. Tổng ngày và các ngày đông nhất khớp JSON. |
| Hỏi đáp quản trị | HTTP 201, 10,20 giây | Trả đúng 167 lượt vào, cao điểm 17:00–trước 18:00 và 36 chỗ trống; khu xe máy/ô tô/xe đạp lần lượt 21/11/4. Có thời điểm hiện tại và nhãn dữ liệu mô phỏng. |
| Gợi ý nhân sự | HTTP 201, 17,06 giây | Các tổng 96, 160, 84, 32 giao dịch khớp từng khoảng giờ. Ưu tiên 08:00 và 17:00–trước 19:00; không biến tổng tuần thành năng suất một ca, không chốt số người tối ưu khi chưa đo năng suất. |
| Kỳ rỗng 01/01/1900 | Lần đầu HTTP 503; lần kiểm lại HTTP 201 | 0 lượt vào/ra/thuần, không tự đoán giờ cao điểm. Phân biệt kỳ năm 1900 với chỗ trống hiện tại ngày 24/09/2026. |
| Chatbot Customer về chỗ trống/giá | Hai lần HTTP 503; lần chẩn đoán sau HTTP 200, 8,53 giây | Đúng 36 chỗ trống/42, giá xe máy 5.000đ/giờ; gói 120 phút 10.000đ, ngày 40.000đ, tháng 180.000đ. Khớp dữ liệu công khai lấy trước yêu cầu; không trả doanh thu hay hóa đơn cá nhân, không cam kết giữ chỗ. |

Các câu trả lời được đọc và đối chiếu với `response.input` đã lưu cùng báo cáo; câu trả lời Customer đối chiếu snapshot công khai trước yêu cầu. Các số trên là **của thời điểm chạy**, không phải tình trạng hiện tại sau các bài kiểm tra tạo dữ liệu khác.

Báo cáo ngày có nêu giả định 30–60 giao dịch/người/giờ và một người trực; đây được ghi rõ là giả định, không phải năng suất được đo. Không dùng đề xuất này làm định biên nhân sự thực tế. Gợi ý nhân sự tuần chỉ đưa ra phân bổ khung giờ và yêu cầu đo theo ca trước khi chốt số người.

## Lỗi giữ nguyên trong bằng chứng

Tổng cộng **9 yêu cầu nghiệp vụ: 6 thành công, 3 lỗi HTTP 503**. Đã có output được đối chiếu cho cả sáu loại ca, nhưng độ sẵn sàng vẫn gián đoạn trong lần chạy này. Không đổi lỗi 503 thành PASS chỉ vì lần sau trả lời được, không lặp vô hạn để chọn kết quả đẹp.

Nguyên nhân upstream chính xác của ba lỗi đầu chưa xác định: phản hồi API đã che thông tin nhạy cảm và phiên server đó chưa ghi code upstream. Một probe tối thiểu ở sandbox bị chặn kết nối (`PermissionError`); probe cùng loại có quyền mạng trả `OK`. Đây là chẩn đoán môi trường, **không** được tính là một ca hỏi đáp nghiệp vụ đạt.

Đã bổ sung nhật ký lỗi chỉ ghi nhóm lỗi, mã số và trạng thái nằm trong danh sách cho phép. Không ghi API key, URL, prompt, nội dung lỗi provider hay traceback. Bốn kiểm thử mới chứng minh metadata vẫn có khi lỗi bị bọc và không rò thông tin; cùng các kiểm thử lỗi/Customer hiện có đạt 31/31 ở lượt kiểm mục tiêu. Lần thử Customer sau khi nạp nhật ký trả 200 nên chưa có bằng chứng mới quy lỗi cho quota hay provider cụ thể.

## Bằng chứng và tái lập

- [Lần đầu: 4 thành công, 2 lỗi](../backend/artifacts/comprehensive-20260924/live-ai.json).
- [Kiểm lại hai ca lỗi: 1 thành công, 1 lỗi](../backend/artifacts/comprehensive-20260924/live-ai-followup.json).
- [Customer sau bổ sung chẩn đoán: thành công](../backend/artifacts/comprehensive-20260924/live-ai-customer-diagnostic.json).
- [Chẩn đoán provider có quyền mạng](../backend/artifacts/comprehensive-20260924/provider-diagnostic-network.json).
- [Script gọi API thật](../scripts/verify_live_ai.py) yêu cầu sidecar tài khoản cục bộ, kiểm marker DB mẫu, không in mật khẩu/token. Script từ chối ghi đè bằng chứng và trả exit 1 nếu có ca HTTP lỗi. HTTP thành công vẫn được đánh dấu cần đọc nội dung; bảng trên là kết quả đọc nội dung riêng.

Pytest dùng provider mock để kiểm tra quyền, prompt, dữ liệu sai/rỗng và lỗi; không dùng số lượng pytest đạt để khẳng định mô hình thật trả lời đúng. Ngược lại, sáu output này không thay thế kiểm thử quyền hay chống rò dữ liệu.
