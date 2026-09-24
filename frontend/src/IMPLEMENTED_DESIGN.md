# Giao diện triển khai theo mẫu 8790

Cập nhật24/09/2026, thay thế mô tả bố cục của bản tích hợp23/09. Người dùng yêu cầu ứng dụng thật nhìn và thao tác theo đúng `http://127.0.0.1:8790/?v=full-demo`. Nguồn thiết kế tại [DESIGN.md](../../DESIGN.md); bản mẫu giữ nguyên.

| Phần | Nguồn triển khai | Bố cục / hành vi |
|---|---|---|
| Khung | layouts/MainLayout.jsx | Header82px, banner mỏng, sidebar224px; mobile điều hướng ngang; Customer4mục; role chỉ báo, không đổi quyền |
| Thành phần mẫu | components/common/PrototypeUI.jsx, styles/prototype-reference.css, styles/prototype-app.css | Logo/SVG/minh họa/CSS từ mẫu, PageHeader/WorkspaceTabs |
| Đăng nhập | pages/Login/LoginPage.jsx | Giới thiệu + form hai cột; xác thực API thật, hỗ trợ next hợp lệ |
| Tổng quan | pages/Expansion/OverviewPage.jsx |4 chỉ số, thu ròng/chứng từ/quote còn trả, trạng thái theo loại xe, link nhanh |
| Vận hành | pages/Expansion/SitesWorkspace.jsx, OperationsPanel.jsx | Nhập tay/Camera, form và thông tin lượt2cột, bảng xe đang gửi; thu/ra giữ CheckoutDialog và quote server |
| Camera | pages/Expansion/CameraOperations.jsx | Video/khung ảnh thật hoặc vùng trống; xác nhận OCR và tự động theo policy, không giả thiết bị |
| Lịch sử | SitesWorkspace view=history | Lọc biển số/mã/khoảng ngày/trạng thái, chi tiết lượt và chứng từ đúng quyền |
| Bãi đỗ | pages/ParkingSlot/ParkingSlotPage.jsx | Sơ đồ nhóm theo khu, ô108px, form vị trí và bộ lọc; khả dụng theo API |
| Danh mục | components/common/CrudPage.jsx | Form inline, bảng cao theo dòng, lọc/sắp xếp/phân trang; các API và quyền cũ |
| Khách / vé | pages/Customer, Vehicle, MonthlyPass | Tab nhóm, hồ sơ/xe/vé tháng; inline editor, validate và request-id giữ nguyên |
| Báo cáo / AI | pages/Expansion/CoreAnalyticsPage.jsx | Panel lọc, chart lưu lượng, bảng số, AI theo ngày/tuần và lịch sử snapshot |
| Admin | pages/User, Role, AuditLog; Expansion/SiteConfigurationPage.jsx | Admin gồm Manager; tài khoản/quyền, cấu hình profile công khai, nhật ký |
| Khách tra phí | pages/Expansion/CustomerFees.jsx | Form trái; minh họa+capacity theo loại phải; mã vé cho xe chưa liên kết, payment modal thật |
| Đặt trước | pages/Expansion/ReservationsPage.jsx | Form và danh sách2cột; biển/loại/ngày; đặt và hủy quaAPI, không bắt buộc trước khi gửi |
| Vé / hỗ trợ | pages/Expansion/CustomerPortal.jsx | Landing gọn2panel; mua/gia hạn/hóa đơn/refund/profile qua chi tiết, không mất tính năng |
| Chat | components/ai/AIChatbot.jsx | Robot tròn/cửa sổ theo mẫu; khách chỉ dữ liệu công khai, nội bộ theo quyền/bãi |

Một số khác biệt có chủ đích so với mô phỏng: báo cáo chỉ chọn ngày/tuần mà API hỗ trợ; nhãn thu ròng phản ánh hoàn tiền; Camera trống khi chưa cấp thiết bị; tiền QR thử luôn là mô phỏng; xem dữ liệu riêng cần tài khoản/quyền hoặc mã vé hợp lệ. Không tính phí/đổi quyền/bỏ xác nhận ở client để bắt chước thao tác giả lập.

Đường dẫn cũ và các chức năng mở rộng còn giữ guard, nằm trong tab/details/tài khoản để giảm số nút mặc định. Backend, schema và dữ liệu người dùng không thay đổi trong đợt sửa giao diện này. Cổng8793 dùng DB tổng hợp riêng để kiểm chứng.
