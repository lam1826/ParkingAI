# Hoàn thiện demo theo đề bài gốc

Phạm vi: chỉ prototype HTML/CSS/JS trong thư mục này. Giữ ba giao diện chính Admin/Manager/Customer, có chế độ Nhân viên để duyệt phân quyền nghiệp vụ. Admin bao gồm Manager. Dữ liệu trong RAM, không API/CSDL/provider/ngân hàng/camera thật. Người dùng duyệt trước khi tích hợp ứng dụng thật.

## Các bước

- [x] Đăng nhập/đăng xuất mô phỏng và quyền Admin/Manager/Nhân viên/Customer.
- [x] Khu vực/vị trí/loại xe/giá: thêm, sửa, trạng thái, xóa khi chưa được tham chiếu.
- [x] Nhận/trả xe không cần đặt trước; phí snapshot, trả chỗ, tránh trùng, vé tháng.
- [x] Khách quen/phương tiện/vé tháng và gia hạn.
- [x] Lịch sử toàn bộ, lọc biển/mã/ngày/trạng thái và xem chi tiết.
- [x] Thống kê ngày/tuần, doanh thu đã thu, chỗ hiện tại/cao điểm.
- [x] AI mô phỏng: báo cáo ngày/tuần, hỏi đáp, đề xuất nhân sự từ đúng dữ liệu; rỗng/sai và giới hạn quyền.
- [x] Minh chứng KT1/KT2/KT3, test nghiệp vụ và AI, browser desktop/mobile; dựng lại index.html.

## Phân công

Root: app/auth/build/guide/docs/browser. Engine: core_permissions. UI core: core_frontend. Báo cáo/chat/AI: simplify_flows_audit. Root giữ quyền ghi memory; các agent không sửa ứng dụng thật.

## Nghiệm thu

Đủ các màn và thao tác để người dùng thử theo đề; không dùng trang ghi chú thay chức năng. Xác thực, lưu trữ và AI trong demo vẫn là mô phỏng được ghi nhãn. Node tests cho logic; browser kiểm các hành trình cần thiết; một lượt xem ảnh desktop/mobile và một lượt sửa xác nhận nếu cần. Không commit/push/deploy.

## Kết quả — 23/09/2026

Hoàn tất phạm vi demo tương tác. Node 30/30 đạt; trình duyệt 65/65 kiểm tra đạt, gồm desktop/mobile; không lỗi JavaScript hoặc gọi API/provider. Đã xem ảnh và xác nhận chỉnh bảng mobile. HTML 210523 bytes, HTTP200 và khớp file. Minh chứng cuối tại `backend/artifacts/simple-ui-demo/core-completion/7049b00faf/result.json`. Các nháp mã ứng dụng thật giữ nguyên theo hash diff trước/sau. Chờ người dùng xem demo trước khi tích hợp.
