# KT3 - BÁO CÁO TRIỂN KHAI VÀ KIỂM THỬ

## 1. Cấu trúc triển khai

- `SourceCode/backend`: API FastAPI, ORM, nghiệp vụ bãi xe, báo cáo và AI.
- `SourceCode/frontend`: giao diện React, phân quyền route, dashboard, CRUD và chatbot.
- `SourceCode/tests`: kiểm thử backend tự động.

Bản sao mã nguồn đã loại trừ tệp `.env`, khóa API, dữ liệu chạy thật, môi trường ảo, thư viện cài đặt và thư mục build.

## 2. Phạm vi kiểm thử

| Nhóm | Nội dung chính |
| --- | --- |
| Xác thực | Đăng nhập đúng/sai, tài khoản khóa, đăng ký, mã cấp quyền, đổi mật khẩu. |
| Phân quyền | Khách hàng không truy cập dashboard nhân viên; manager/admin truy cập chức năng quản trị. |
| Check-in | Thành công, xe mới, xe đã ở trong bãi, hết chỗ, thiếu biển số, sai loại xe, vé tháng; chọn đích danh vị trí (thành công, vị trí không tồn tại, vị trí đã có xe, vị trí sai loại xe). |
| Check-out | Thành công, không tìm thấy xe, trả xe hai lần, tính phí và giải phóng vị trí; đường phụ `/api/v1/parking-sessions/{id}/check-out` do server tính phí và chặn check-out hai lần. |
| Tính phí | Theo giờ, theo ngày (nhánh DAILY), vé tháng thật (phí = 0), giá bằng 0, thiếu bảng giá, thời gian sai; boundary 0s/3599s/3600s/3601s. |
| Chỗ trống | Có chỗ, hết chỗ, theo khu vực, theo loại xe, loại trừ vị trí đang chiếm dụng. |
| Dashboard/báo cáo | Tổng xe, doanh thu, tỷ lệ lấp đầy, giờ cao điểm, xuất Excel/PDF. |
| AI | Hỏi đáp, báo cáo ngày/tuần, gợi ý nhân sự, dữ liệu rỗng, timeout, chống bịa số liệu; thiếu API key trả 503; backend tự tổng hợp dữ liệu khi client không gửi số liệu. |
| Nhật ký | Ghi thao tác thay đổi và giới hạn quyền đọc nhật ký. |

## 3. Kết quả xác minh

Thời điểm: 18/08/2026.

| Hạng mục | Kết quả |
| --- | --- |
| Pytest backend | 79 passed |
| Cảnh báo | 1 cảnh báo deprecation từ Starlette TestClient/httpx |
| ESLint frontend | Đạt, không có lỗi |
| Vite production build | Đạt, 2.104 module được xử lý |

## 4. Lệnh tái hiện

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm.cmd run lint
npm.cmd run build
```

## 5. Đánh giá

Các luồng quan trọng đều có kiểm thử tự động và hiện đạt. Cảnh báo duy nhất nằm ở tương thích tương lai giữa thư viện TestClient và httpx, không làm thất bại kiểm thử. Nên theo dõi và nâng phiên bản phụ thuộc trong lần bảo trì tiếp theo.
