# Minh chứng sử dụng AI trong SDLC — phần mở rộng đồ án

## 1. Yêu cầu và quyết định phạm vi

Yêu cầu của người dùng trong phiên làm việc: mở rộng cổng khách hàng, thanh toán, camera/biển số và đặt chỗ; sau đó xác định mục đích đồ án, muốn QR ngẫu nhiên để thử và dùng điện thoại chụp biển số, hỏi về YOLO. Từ đó bản triển khai chọn QR DEMO, dữ liệu mẫu riêng, YOLO ONNX + OCR trên CPU và bước nhân viên xác nhận. Không thay yêu cầu này bằng kết nối ngân hàng hoặc mua camera thật.

Kế hoạch được lưu tại `plan.md`. Lộ trình vận hành thật được giữ riêng trong `docs/DEVELOPMENT_ROADMAP.md`; kết quả đã kiểm tra nằm trong `docs/EXPANSION_IMPLEMENTATION_STATUS.md`.

## 2. Liên kết yêu cầu, code và kiểm thử

| Giai đoạn | AI hỗ trợ | Minh chứng có thể kiểm tra |
| --- | --- | --- |
| KT1 — phân tích | Phân biệt tài khoản/khách/chủ xe, vé tháng/quyền giữ vị trí; xác định đơn và tiền mô phỏng | `backend/expansion/portal_models.py`, `site_models.py`, `docs/PORTAL_PAYMENTS.md`, `docs/SITES_RESERVATIONS.md` |
| KT2 — triển khai | Sinh và rà soát API/giao diện, chống xử lý lặp và giao dịch đồng thời, nâng cấp DB cũ | `portal_service.py`, `reservations.py`, `frontend/src/pages/Expansion`, migration `20260907_02`; `test_portal_concurrency.py`, `test_expansion_sites_concurrency.py`, `test_expansion_migration.py` |
| KT3 — AI và dữ liệu lỗi | Tách phát hiện vùng/đọc chữ, xử lý no_plate/lỗi ảnh, dự báo thiếu dữ liệu và tránh dùng tương lai | `vision_service.py`, `forecast.py`, `tests/test_expansion_vision_api.py`, `test_expansion_forecast.py`, `test_expansion_insights_api.py` |
| Kiểm tra sản phẩm | Phát hiện QR mất sau refresh, dữ liệu cũ khi đổi bãi, UUID không chạy trên HTTP LAN, nhãn vé hết hạn, bỏ sót nhắc vé sau batch đầu | `portalState.test.js`, `requestId.test.js`, `test_expansion_legacy_boundary.py`, `test_portal_api.py`, bằng chứng trình duyệt trong artifact UAT |
| Cuối kỳ | Viết hướng dẫn cài/chạy/trình diễn, cập nhật Word theo bố cục gốc, ghi rõ phạm vi và hạn chế | `docs/DEMO_GUIDE.md`, `docs/VISION_FORECAST.md`, hai tài liệu Word của dự án |

Đường dẫn rút gọn trong bảng được hiểu tương đối với `backend/expansion`, `frontend/src/pages/Expansion` hoặc `tests` theo tên file. Các test dùng mock không phải bằng chứng model nhận đúng biển số.

## 3. Prompt tái lập để bảo vệ đồ án

Các prompt dưới đây là mẫu tái lập quy trình, không được trình bày như bản chép nguyên văn mọi lần gọi AI trong phiên triển khai.

**KT1:** “Phân tích cổng khách hàng cho hệ thống bãi xe. Tài khoản chỉ xem các lượt thuộc hồ sơ đã xác minh. Phân biệt quyền sử dụng vé tháng và quyền giữ vị trí. Đề xuất bảng dữ liệu và những tình huống đổi chủ xe có thể làm lộ lịch sử.”

**KT2:** “Thiết kế luồng QR thanh toán DEMO: server chốt giá và kỳ vé, xử lý kết quả lặp an toàn, cấp vé và ghi phiếu trong một giao dịch. Không gọi ngân hàng, không ghi DEMO thành cash/transfer, không cộng vào doanh thu thật. Viết kiểm thử hai request đồng thời và lỗi giữa tiếp nhận kết quả với cấp vé.”

**KT3:** “Thiết kế API nhận ảnh biển số bằng YOLO và OCR. Khi không nhận được phải báo no_plate hoặc cho nhập tay, không sinh biển giả. Ảnh có quyền theo bãi và thời hạn lưu. Kiểm tra MIME sai, ảnh lớn, quyền chéo bãi và hai nhân viên duyệt cùng ảnh.”

**Báo cáo phân tích:** “Bạn là trợ lý phân tích bãi đỗ xe. Không tự tạo số liệu, chỉ nhận xét dữ liệu cung cấp. Nếu dữ liệu rỗng hoặc thiếu, nêu rõ giới hạn. Tóm tắt lưu lượng, khung giờ cao điểm và phương án nhân sự kèm các giả định.”

## 4. Đánh giá kết quả và trách nhiệm kiểm tra

YOLO/OCR đã chạy độc lập trên hai ảnh CC0: ảnh xe có khung biển nhưng OCR đọc sai, ảnh cận biển trả no_plate. Kết quả và nguồn được lưu trong hướng dẫn camera. Vì vậy hệ thống giữ bước đối chiếu thủ công, chưa công bố độ chính xác biển Việt Nam.

Dự báo trong phần mở rộng là thuật toán thống kê có backtest theo thời gian; OCR là mô hình thị giác; QR là mô phỏng trạng thái thanh toán. Không gọi tất cả các phần này là LLM. Gemini trong sản phẩm hiện có vẫn được dùng cho báo cáo/hỏi đáp khi quản trị bật, nhưng bộ chạy đồ án mặc định tắt gọi dịch vụ AI bên ngoài.

Mã do AI hỗ trợ phải qua kiểm thử và rà soát. Những lỗi phát hiện trong quá trình tích hợp được sửa ở nguyên nhân và có bằng chứng tương ứng; không dùng việc “AI đã sinh code” làm bằng chứng chức năng đúng.

## 5. Đối chiếu review độc lập ngày 07/09/2026

Người dùng cung cấp bản review của Claude và yêu cầu kiểm chứng rồi sửa các lỗi đã xác nhận. Quá trình xử lý đối chiếu từng nhận định với mã đang có, tái hiện trên database riêng hoặc trình duyệt riêng, ghi kết quả lỗi trước sửa rồi chạy lại sau sửa. Không sửa dữ liệu trình diễn để làm cho kiểm thử đạt.

Minh chứng mã và hồi quy: `tests/test_review_waitlist_regressions.py` (clock, hạn đến, giao dịch và tranh chấp phạm vi bãi), `tests/test_review_zone_regressions.py` (khu vực/API cũ/readiness), `tests/test_review_portal_legacy_regressions.py` (vé portal và tương thích API cũ), `tests/browser/remote_hook_regression.py` (mutation kết thúc sau khi đổi bộ lọc). Bài trình duyệt cuối dùng React thật và hook của sản phẩm; trước sửa nhận dữ liệu rỗng và trạng thái tải không kết thúc, sau sửa giữ đúng bộ lọc hiện tại.

Kết quả đối chiếu, đường dẫn bằng chứng và những nhận định chưa đủ cơ sở nằm tại [Phản hồi review](CLAUDE_REVIEW_RESPONSE.md). Các đề xuất PostgreSQL thực, thanh toán thật hoặc luồng video liên tục vẫn là công việc triển khai tiếp, không được đánh dấu đã nghiệm thu bằng kiểm thử SQLite.

## 6. Nghiệm thu độc lập bốn nâng cấp

Người dùng gửi lại prompt yêu cầu review sâu, sửa lỗi đã xác nhận và hoàn thành A–D. Khi đọc workspace, mã nâng cấp đã có nên AI giữ chúng làm đầu vào và tìm bằng chứng mới. Kết quả phát hiện thêm khoảng lọc không hợp lệ, quyền bảo đảm chỗ theo chủ xe, phản hồi ảnh bãi đóng và những API còn ghép khiến phần không liên quan mất dữ liệu. Các bài test được chạy lỗi trước sửa, sau đó giữ hồi quy trong `test_acceptance_booking_fleet.py`, `test_acceptance_security.py` và hai runner React thật.

Với nghi vấn chủ xe đổi giữa lần đọc và lần ghi, bài thử dùng hai kết nối SQLite và handler chuyển chủ thật. Guard chặn yêu cầu cũ, trả 409 và không ghi đặt chỗ; không sửa theo suy đoán. UAT dùng Chrome/profile và DB mới, kiểm tra cả YOLO/OCR cục bộ, QR DEMO, đổi tài khoản và viewport điện thoại. Phân biệt rõ lỗi bộ chọn DOM của harness với lỗi ứng dụng; chi tiết RED/GREEN và vòng chạy cuối ở [nghiệm thu độc lập](ACCEPTANCE_REVIEW_2026-09-07.md).
