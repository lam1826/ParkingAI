# ParkingAI

Hệ thống quản lý bãi đỗ xe dùng FastAPI, React, SQLite và Gemini. Hệ thống hỗ trợ phân quyền, quản lý dữ liệu nền, xe vào/ra, tính phí, vé tháng, chỗ trống, báo cáo lưu lượng–doanh thu và trợ lý AI.

## Chức năng chính

- Đăng ký/đăng nhập JWT; vai trò `customer`, `staff`, `manager`, `admin`.
- CRUD khu vực, vị trí đỗ, loại xe, phương tiện, khách hàng, vé tháng và bảng giá.
- Check-in theo biển số: nhân viên chọn loại xe, khu vực và vị trí đỗ cụ thể (hoặc để hệ thống
  tự cấp phát); hệ thống kiểm tra vị trí tồn tại/còn trống/đúng loại xe và chặn một xe vào hai lần.
- Check-out, miễn phí cho vé tháng hợp lệ (vé tháng được gắn vào phiên gửi khi check-in),
  làm tròn phí theo giờ/ngày từ bảng giá cấu hình trong DB và giải phóng vị trí.
- Tra cứu lịch sử theo biển số, trạng thái (đang gửi/đã ra), thời gian, khu vực, loại xe;
  thống kê chỗ trống theo khu vực.
- Dashboard, báo cáo lưu lượng/doanh thu và khung giờ cao điểm.
- Sơ đồ chỗ đỗ trực quan theo khu vực với trạng thái còn trống, đang có xe và bảo trì.
- Xuất báo cáo tổng hợp ra tệp Excel (`.xlsx`) hoặc PDF.
- Nhật ký hoạt động dành cho manager/admin, không lưu nội dung nhạy cảm của request.
- Trang AI Analytics (`/ai`) và chatbot Gemini tích hợp trên các trang: hỏi đáp dữ liệu,
  sinh báo cáo ngày/tuần và gợi ý lịch nhân sự. Backend tự tổng hợp số liệu thật từ database
  rồi mới gửi cho AI (AI không tự tạo số liệu); thiếu `GEMINI_API_KEY` thì các endpoint `/ai/*`
  trả 503 rõ ràng còn thống kê cơ bản vẫn hoạt động.

## Cài đặt

Yêu cầu Python 3.11+ và Node.js 20+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
npm.cmd install
Set-Location frontend
npm.cmd install
Set-Location ..
```

Sửa `backend/.env`, đặc biệt là `SECRET_KEY`, `GEMINI_API_KEY`, `MANAGER_REGISTRATION_CODE` và `ADMIN_REGISTRATION_CODE`. Các mã đăng ký phải là chuỗi bí mật dài, ngẫu nhiên và chỉ chia sẻ cho đúng người cần cấp quyền. Tạo tài khoản quản trị đầu tiên:

```powershell
Set-Location backend
python create_admin.py
Set-Location ..
```

Chạy đồng thời backend và frontend:

```powershell
npm.cmd run dev
```

- Giao diện: http://localhost:5173
- API/Swagger: http://127.0.0.1:8000/docs

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Hoặc chạy toàn bộ các bước kiểm tra từ thư mục gốc:

```powershell
.\scripts\verify.ps1
```

`pytest.ini` giới hạn việc thu thập test vào thư mục `tests/`, vì bộ hồ sơ bàn giao có chứa một
bản sao mã nguồn để lưu minh chứng. GitHub Actions cũng tự chạy lại backend test, frontend test,
ESLint và production build trên mọi lần push hoặc pull request.

Chi tiết kiến trúc, prompt và minh chứng dùng AI trong SDLC nằm tại [docs/AI_SDLC.md](docs/AI_SDLC.md).
