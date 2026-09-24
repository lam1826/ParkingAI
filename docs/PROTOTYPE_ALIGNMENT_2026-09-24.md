# Đối chiếu giao diện với bản mẫu8790 — 24/09/2026

Người dùng yêu cầu ứng dụng thật theo đúng `http://127.0.0.1:8790/?v=full-demo`; bản tích hợp trước chưa đạt bố cục. Đợt này sửa React, giữ nguyên prototype và backend nghiệp vụ. Bản thật tại `http://127.0.0.1:8793/` dùng DB tổng hợp riêng.

## Đã thay đổi

- Tái sử dụng CSS/SVG của mẫu, giới hạn trong `.prototype-ui`: header, menu vai trò, sidebar và điều hướng ngang trên điện thoại, lưới1.17/.83, form46px, nút44px, bảng gọn theo nội dung và chatbot tròn.
- Tổng quan có4 chỉ số, thu tiền hôm nay, phí đang gửi từ quote server và trạng thái theo loại xe. Thu ròng/chứng từ thu-hoàn được ghi nhãn đúng hợp đồng server.
- Vận hành Nhập tay/Camera, khối phí và bảng xe; các trang khách Phí/Đặt trước/Vé/Hỗ trợ; danh mục, sơ đồ, lịch sử, vé tháng, báo cáo/AI, tài khoản và nhật ký dùng bố cục mẫu.
- Admin có nhóm QUẢN TRỊ: Tài khoản & quyền, Cấu hình bãi, Nhật ký. Cấu hình dùng API public-profile hiện có; thêm route SPA `/site-settings`.
- Sửa nhãn ẩn của header bảng thoát khỏi vùng cuộn làm viewport điện thoại rộng420px. Đặt parent header tương đối, giữ nhãn cho trình đọc màn hình; kiểm lại390px/scale1.
- Sửa hai wrapper trong hộp thoại thanh toán/hỗ trợ kế thừa min-height100dvh. Chỉ wrapper lồng đặt minHeight0; hộp thoại gọn trên máy tính/điện thoại.

## Kiểm chứng

| Nhóm | Bằng chứng |
|---|---|
| Frontend |274/274 Node test; ESLint toàn frontend đạt; sau điều chỉnh menu cuối,14 test mục tiêu đạt; Vite build đạt. Logs `backend/artifacts/prototype-final-node.log`, `prototype-final-targeted.log`, `prototype-final-build.log` |
| Máy chủ demo |10/10 test `tests/test_demo_server.py`, gồm mở trực tiếp route cấu hình và giữ giới hạn DB tổng hợp |
| Giao dịch và UI thật |103/103 kiểm tra,36 ảnh desktop1440×1000/mobile390×844, không lỗi runtime; `backend/artifacts/prototype-real-comparison/003cd220b0/result.json` |
| Xác nhận bản build cuối |67/67 kiểm tra chỉ đọc Customer/Manager/Staff,32 ảnh; `backend/artifacts/prototype-real-comparison/3843fc5a6b/result.json` |
| Admin |Đã xem đủ7 trang desktop/mobile từ `prototype-admin-comparison/ac813de69d` (88 kiểm tra thực đạt; lượt chạy dừng ở selector tham chiếu cũ). Sau sửa nút cấu hình/menu và harness,42/42 kiểm tra xác nhận đạt,12 ảnh; `backend/artifacts/prototype-admin-comparison/78eee23556/result.json` và `review.md`. Không có lỗi API/runtime/tràn trang |
| Dữ liệu / an toàn kiểm thử |Nhận xe vãng lai không đặt trước; khách xác minh mã vé riêng, tra phí dương, mở luồng thanh toán; Manager phải xác nhận nhận tiền trước checkout; trạng thái hoàn tất đọc lại từ server. Đặt/hủy chỗ và hỗ trợ tạo/trả lời/đóng qua API. Không gọi ngân hàng/provider; không lưu proof/password trong ảnh/log; profile trình duyệt được xóa |
| So sánh mẫu |Ảnh nguồn `backend/artifacts/prototype-reference/634db8c26b/`; root đã xem các màn khách, tổng quan, vận hành, hộp thoại và trang quản trị. CSS/lưới/SVG cùng mẫu; dữ liệu API có thể khác mẫu |

Các lần đầu có lỗi viewport và chiều cao dialog được giữ làm bằng chứng trước sửa, không dùng để tuyên bố đạt. Lỗi đồng bộ selector/list response trong harness đã sửa riêng, không thay hợp đồng sản phẩm. Hai reviewer phụ trách UI/browser thực hiện đối chiếu độc lập theo phạm vi, root xem lại ảnh; không tuyên bố đối chiếu pixel tuyệt đối.

## Khác biệt cần giữ khi chuyển mô phỏng sang ứng dụng

- Vai trò trên header là chỉ báo tài khoản; đăng nhập thật quyết định quyền. Không dùng nút đổi vai trò của prototype để cấp quyền.
- Khách tra phí riêng cần quyền xe hoặc mã riêng trên vé. Đặt trước không cấp quyền sở hữu.
- Báo cáo chọn ngày/tuần theo API; bảng loại xe và giá có tab riêng; các trường và xác nhận nghiệp vụ thật vẫn giữ.
- Khi chưa bật payOS, thanh toán online báo chưa khả dụng; chưa có nghiệm thu chuyển tiền thật. Camera dùng video/ảnh thật hoặc vùng trống; chưa chứng minh độ chính xác trên webcam/điện thoại. Loại xe camera theo hồ sơ, chưa có bộ phân loại ảnh độc lập.
- AI dùng provider thật khi cấu hình khả dụng. Lỗi Gemini503 ở đợt trước vẫn là giới hạn nghiệm thu; đợt giao diện này chặn gọi provider trong browser, không tạo câu trả lời giả.
- Không push/deploy, không migrate hoặc thay DB người dùng. Các thay đổi backend cũ trong working tree thuộc đợt trước, được giữ nguyên.
