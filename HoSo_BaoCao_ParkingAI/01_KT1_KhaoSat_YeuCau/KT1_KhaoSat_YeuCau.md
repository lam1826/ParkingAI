# KT1 - KHẢO SÁT VÀ PHÂN TÍCH YÊU CẦU

## 1. Tổng quan bài toán

ParkingAI là hệ thống quản lý bãi đỗ xe phục vụ nhân viên vận hành, quản lý và quản trị viên. Hệ thống số hóa quy trình xe vào/ra, phân bổ vị trí, tính phí, quản lý vé tháng, theo dõi công suất, lập báo cáo và hỗ trợ phân tích bằng AI.

## 2. Đối tượng sử dụng

- Khách hàng: quản lý hồ sơ cá nhân và thông tin phương tiện được cho phép.
- Nhân viên: tiếp nhận xe, trả xe, quản lý dữ liệu nghiệp vụ và xem báo cáo vận hành.
- Quản lý: có quyền của nhân viên, đồng thời quản lý tài khoản và xem nhật ký hoạt động.
- Quản trị viên: quản trị toàn bộ hệ thống, gồm vai trò và quyền truy cập.

## 3. Yêu cầu chức năng

| Mã | Nhóm chức năng | Nội dung |
| --- | --- | --- |
| FR-01 | Xác thực | Đăng ký, đăng nhập JWT, đổi mật khẩu, cập nhật hồ sơ. |
| FR-02 | Phân quyền | Bốn vai trò: customer, staff, manager, admin. |
| FR-03 | Dữ liệu nền | CRUD khu vực, vị trí đỗ, loại xe và bảng giá. |
| FR-04 | Khách hàng | Quản lý khách hàng, phương tiện và vé tháng. |
| FR-05 | Xe vào | Chuẩn hóa biển số, kiểm tra phiên đang hoạt động, tìm vị trí đúng loại xe, tạo vé UUID. |
| FR-06 | Xe ra | Tính phí, áp dụng vé tháng hợp lệ, đóng phiên và giải phóng vị trí. |
| FR-07 | Chỗ trống | Thống kê toàn bãi và theo khu vực/loại xe; trình bày sơ đồ trạng thái. |
| FR-08 | Báo cáo | Lưu lượng, doanh thu, giờ cao điểm; xuất Excel/PDF. |
| FR-09 | AI | Hỏi đáp dữ liệu, báo cáo ngày/tuần và gợi ý nhân sự. |
| FR-10 | Kiểm soát | Nhật ký thao tác thay đổi dữ liệu, không lưu nội dung nhạy cảm. |

## 4. Quy tắc nghiệp vụ chính

1. Một phương tiện chỉ có tối đa một phiên gửi xe ở trạng thái `active`.
2. Một vị trí chỉ được cấp cho một phương tiện tại cùng thời điểm.
3. Vị trí phải đang hoạt động, còn trống và phù hợp loại xe.
4. Khi check-out, việc tính phí, đóng phiên và giải phóng vị trí phải nhất quán.
5. Vé tháng chỉ miễn phí khi đang hoạt động và ngày check-out nằm trong thời hạn.
6. Bảng giá được chọn theo loại xe, loại vé, trạng thái hoạt động và ngày hiệu lực mới nhất.
7. Thời gian check-out không được trước thời gian check-in.
8. AI chỉ phân tích dữ liệu có cấu trúc được cung cấp; khi thiếu dữ liệu phải nói rõ và không tự tạo số liệu.

## 5. Yêu cầu phi chức năng

- Bảo mật: mật khẩu băm, JWT, phân quyền ở cả API và giao diện; bí mật qua biến môi trường.
- Tin cậy: các luồng xe vào/ra và tính phí có kiểm thử tự động.
- Hiệu năng: truy vấn có bộ lọc; giao diện tải trang theo nhu cầu.
- Khả dụng: giao diện phản hồi, thông báo lỗi rõ, có trạng thái tải và dữ liệu rỗng.
- Bảo trì: tách router, service, schema, model; frontend chia page, component, hook và service.
- Truy vết: lưu nhật ký các thao tác tạo/sửa/xóa, check-in, check-out và tác vụ AI.

## 6. Phạm vi

Trong phạm vi: quản lý một hệ thống bãi xe nhiều khu vực, nhiều loại xe, tính phí, vé tháng, báo cáo và AI hỗ trợ quản trị.

Ngoài phạm vi hiện tại: nhận dạng biển số từ camera thực, thanh toán trực tuyến, điều khiển barie vật lý, triển khai đa chi nhánh và ứng dụng di động riêng.

## 7. Tiêu chí nghiệm thu

- Các API nghiệp vụ chính hoạt động đúng theo vai trò.
- Xe vào/ra cập nhật đúng phiên và vị trí.
- Phí theo giờ/ngày và vé tháng cho kết quả đúng.
- Dashboard và báo cáo hiển thị số liệu từ cơ sở dữ liệu.
- AI từ chối suy đoán khi dữ liệu rỗng.
- Toàn bộ kiểm thử backend, lint và build frontend đạt.
