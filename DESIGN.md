---
name: ParkingAI
description: Giao diện theo đúng prototype parking-simple đã được người dùng duyệt.
colors:
  primary: "#1767bd"
  canvas: "#f5f7fa"
  surface: "#ffffff"
  text-primary: "#172638"
  text-secondary: "#596879"
  divider: "#dde4ed"
  navigation-selected: "#edf4fd"
  focus: "#438adb"
typography:
  headline:
    fontFamily: "Segoe UI,Arial,sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
  section:
    fontFamily: "Segoe UI,Arial,sans-serif"
    fontSize: "19px"
    fontWeight: 700
rounded:
  button: "7px"
  card: "14px"
---

# ParkingAI — nguồn thiết kế hiện hành

Cập nhật 24/09/2026. Người dùng chỉ rõ mẫu bắt buộc là `http://127.0.0.1:8790/?v=full-demo`, không chấp nhận bản tích hợp trước chỉ giữ màu và nhóm menu. [Prototype](frontend/prototypes/parking-simple/README.md) là nguồn bố cục, tỷ lệ, biểu mẫu, bảng và responsive. Không sửa prototype để khớp ứng dụng.

## Nguồn mã

- `frontend/prototypes/parking-simple/style.css` và `core.css`: CSS mẫu nguyên gốc.
- `frontend/scripts/sync-prototype-style.mjs`: sao chép CSS vào `src/styles/prototype-reference.css`, giới hạn selector trong `.prototype-ui`. Chạy từ frontend bằng `node scripts/sync-prototype-style.mjs` khi cần đồng bộ nguồn mẫu.
- `frontend/src/styles/prototype-app.css`: cầu nối cho Link/role đã xác thực, biểu mẫu còn dùng MUI và các chi tiết ứng dụng thật; không thiết kế một shell khác.
- `frontend/src/components/common/PrototypeUI.jsx`: SVG, logo, minh họa bãi, PageHeader và WorkspaceTabs dùng chung.
- Theme MUI giữ cùng màu/chữ/input46px/nút44px, nhãn ở trên ô. Slot props theo MUI9; không dùng InputLabelProps đã loại bỏ.

## Khung và tỷ lệ

Thanh trên cao tối thiểu82px, logo trái, ba nhãn vai trò giữa và thao tác tài khoản phải. Vai trò hiện tại được đánh dấu; nhãn không cho đổi quyền. Banner mỏng35px. Sidebar nội bộ224px với7 mục chính; Admin thêm tài khoản, cấu hình, nhật ký. Dưới780px sidebar thành thanh ngang cuộn, không dùng drawer. Khách có4 mục ở thanh riêng.

Main nội bộ tối đa1600px; từ1400px padding40px48px. Main khách tối đa1136px; padding32px và48px phía trên ở màn lớn. Lưới form/kết quả hoặc form/chỗ trống có tỷ lệ1.17/.83, gap24px; dưới780px một cột. Surface padding26px, border1px, radius14px; trên điện thoại22px rồi18px ở390px. Không lồng các khung lớn chỉ để bố trí.

Chữ Segoe UI/Arial, nội dung15px, mô tả14px, nhãn13px, tiêu đề30px, h2 19px. Input46px có nhãn tách ở trên; nút44px, nút nhỏ34px. Bảng HTML cao theo nội dung, header12px/body13px, chứa vùng cuộn ngang khi thực sự cần. Ô sơ đồ bãi108px; luôn có nhãn trạng thái, không chỉ dùng màu.

## Luồng

- Tổng quan:4 chỉ số → thu tiền hôm nay → tình trạng toàn bãi theo loại xe → liên kết nhanh. Thu ròng và chứng từ theo server; phí đang gửi từ quote server, không tính lại tại client.
- Vận hành: Nhập tay/Camera ở tiêu đề; Xe vào/Xe ra ở biểu mẫu; panel phí bên phải và bảng xe đang gửi bên dưới. Thao tác ngoại lệ/config thêm ở details. Xác nhận thu/ra vẫn dùng hợp đồng quote/idempotency thật.
- Danh mục và vé: biểu mẫu tạo/sửa ngay trên trang, bảng gọn phía dưới; quyền và validator hiện có giữ nguyên.
- Customer: Phí, Đặt trước, Vé & lịch sử, Hỗ trợ. Tra phí/đặt trước là biểu mẫu hai panel theo mẫu. Quyền xe hoặc mã vé riêng vẫn bắt buộc để xem phí riêng; đặt trước không tạo sở hữu.
- Chat: nút robot tròn58px góc phải, cửa sổ385×530px; dưới780px nút54px và chiều rộng theo viewport. AI dùng nguồn dữ liệu theo quyền; lỗi provider hiển thị thật.

## Ranh giới

Giao diện dùng cấu trúc mẫu; dữ liệu, xác thực, quyền và thanh toán dùng API. Không đưa role-switch hoặc dữ liệu RAM của prototype vào bản thật. Mẫu có dữ liệu/AI/camera giả lập; cổng8793 là bản API thật trên DB tổng hợp riêng. Camera chưa có thiết bị thì hiện vùng camera trống, không dùng ảnh giả như camera thật. Bảng giá/phí, proof thanh toán, xác nhận thu tiền và ngày báo cáo phải giữ đúng hợp đồng server.

Chi tiết nguồn trang: [IMPLEMENTED_DESIGN.md](frontend/src/IMPLEMENTED_DESIGN.md). Bằng chứng kiểm tra đợt sửa được ghi riêng trong docs; tài liệu thiết kế này không thay thế nghiệm thu.
