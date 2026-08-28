# ParkingAI

Hệ thống quản lý bãi đỗ xe dùng FastAPI, React, SQLite và Gemini. Hệ thống hỗ trợ phân quyền, quản lý dữ liệu nền, xe vào/ra, tính phí, vé tháng, chỗ trống, báo cáo lưu lượng–doanh thu và trợ lý AI.

## Chức năng chính

- Đăng ký/đăng nhập JWT; vai trò `customer`, `staff`, `manager`, `admin`.
- CRUD khu vực, vị trí đỗ, loại xe, phương tiện, khách hàng, vé tháng và bảng giá.
  Tên loại xe được chuẩn hóa Unicode/hoa-thường và có unique index ở database, nên
  các biến thể như `Ô tô`, ` ô TÔ ` không thể tạo thành hai bản ghi nghiệp vụ.
- Check-in theo biển số: nhân viên chọn loại xe, khu vực và vị trí đỗ cụ thể (hoặc để hệ thống
  tự cấp phát); hệ thống kiểm tra vị trí tồn tại/còn trống/đúng loại xe và chặn một xe vào hai lần.
  **Mọi lượt vào — kể cả xe có vé tháng — đều bắt buộc phải có một bảng giá dự phòng đang
  `is_active` và `effective_date <= ngày check-in`.** Nhờ vậy nếu vé tháng hết hạn giữa lượt gửi
  thì lúc tính phí vẫn còn một hợp đồng giá ổn định để dùng; DB backstop bằng trigger, không chỉ
  kiểm ở tầng ứng dụng.
- Check-out, miễn phí khi vé tháng đã gắn lúc check-in vẫn bao phủ ngày xe ra;
  nếu ở quá ngày hết hạn thì làm tròn phí theo giờ/ngày từ bảng giá cấu hình
  trong DB, sau đó giải phóng vị trí.
- Vòng đời phiên gửi xe: trạng thái được LƯU chỉ gồm `active`, `completed`, `cancelled`.
  `checking_out` là trạng thái chuyển tiếp CHỈ tồn tại bên trong transaction check-out
  (`active -> checking_out -> completed`): nó được claim nguyên tử để hai request đồng thời
  không thể cùng tính phí, và không bao giờ được INSERT trực tiếp hay còn đọng lại sau khi
  request kết thúc. Tính phí lỗi thì transaction rollback đưa phiên về `active`, vị trí vẫn
  occupied và không có billing dở dang. Cả hai endpoint check-out
  (`POST /parking/check-out` và `PUT /api/v1/parking-sessions/{id}/check-out`) dùng chung
  đúng vòng đời này.
- Tra cứu lịch sử theo biển số, trạng thái (đang gửi/đã ra/đã hủy), thời gian, khu vực,
  loại xe; hiển thị thời lượng đã gửi của phiên hoàn tất và thống kê chỗ trống theo khu vực.
- Dashboard, báo cáo lưu lượng/doanh thu và khung giờ cao điểm.
- Sơ đồ chỗ đỗ trực quan theo khu vực với trạng thái còn trống, đang có xe và bảo trì.
- Xuất báo cáo tổng hợp ra tệp Excel (`.xlsx`) hoặc PDF.
- Nhật ký hoạt động dành cho manager/admin, không lưu nội dung nhạy cảm của request.
- Trang AI Analytics (`/ai`) và chatbot Gemini tích hợp trên các trang: hỏi đáp dữ liệu,
  sinh báo cáo ngày/tuần và gợi ý lịch nhân sự. Backend tự tổng hợp số liệu thật từ database
  rồi mới gửi cho AI (AI không tự tạo số liệu); thiếu `GEMINI_API_KEY` thì các endpoint `/ai/*`
  trả 503 rõ ràng còn thống kê cơ bản vẫn hoạt động.
- Lỗi ở biên provider AI được ánh xạ fail-closed sang HTTP ổn định, chỉ trả một thông báo
  chung và không lộ API key, phản hồi thô của provider hay stack trace:

  | Tình huống ở biên provider | HTTP |
  | --- | --- |
  | Provider phản hồi quá thời gian (timeout, `DEADLINE_EXCEEDED`, mã 408/504) | 504 |
  | Hết quota/không khả dụng/lỗi mạng/không xác thực được (mã 401/403/429/503) | 503 |
  | Phản hồi không hợp lệ hoặc lỗi không phân loại được | 502 |
  | AI tắt (`AI_ENABLED=false`) hoặc thiếu `GEMINI_API_KEY` | 503 |

  `HTTPException` do tầng trong ném ra được router/service re-raise nguyên trạng, không bị
  nuốt thành 500. Các lỗi nội bộ ngoài dự kiến chỉ được ghi đầy đủ ở log máy chủ; response
  công khai dùng thông báo chung, không ghép exception SQL/provider hoặc stack trace.

## Ma trận phân quyền hiện hành

Phân quyền được kiểm tra tại backend; ẩn menu ở frontend chỉ là lớp trải nghiệm bổ sung.

| Vai trò | Quyền chính |
| --- | --- |
| `customer` | Đăng nhập và dùng các chức năng tài khoản được cấp; không truy cập màn hình vận hành/quản trị |
| `staff` | Nghiệp vụ xe vào/ra, tra cứu phiên, dashboard, báo cáo, AI analytics và quản lý dữ liệu bãi được router cho phép |
| `manager` | Kế thừa `staff`; quản lý tài khoản và xem nhật ký hoạt động |
| `admin` | Toàn quyền quản trị tài khoản và mô tả vai trò; không được đổi tên/xóa bốn vai trò canonical |

Bốn tên vai trò `customer`, `staff`, `manager`, `admin` là contract cố định giữa token,
backend và frontend. API từ chối tên vai trò tùy ý để tránh tài khoản hợp lệ bị mất quyền.

## Cài đặt

Yêu cầu Python 3.11+ và Node.js 20+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
npm.cmd install
Set-Location frontend
npm.cmd install
Set-Location ..
```

Sửa `backend/.env`, đặc biệt là `SECRET_KEY`, `GEMINI_API_KEY`, `MANAGER_REGISTRATION_CODE` và `ADMIN_REGISTRATION_CODE`. Các mã đăng ký phải là chuỗi bí mật dài, ngẫu nhiên và chỉ chia sẻ cho đúng người cần cấp quyền. Tạo tài khoản quản trị đầu tiên:

```powershell
python backend\db_rollout.py --database backend\database\parking.db
Set-Location backend
python create_admin.py
Set-Location ..
```

Ứng dụng không tự migration khi import/khởi động. Với DB đã có, hãy backup
và thử migration trên bản sao trước (file đích phải chưa tồn tại):

```powershell
python backend\db_rollout.py --source backend\database\parking.db --copy-to C:\ParkingAI-UAT\parking-copy.db
```

`create_admin.py` không tự tạo bảng; script chỉ chạy khi database đã vượt qua
schema readiness. Sau khi khởi động, dùng `GET /ready` (không chỉ `GET /`) để
xác nhận đúng DB đã được migration.

`GET /ready` chạy ở chế độ `deep=False`: mở SQLite read-only rồi kiểm contract
bảng/cột/type/nullability/PK/FK/index/**trigger** cùng các bất biến nghiệp vụ
(canonical BOOLEAN, `effective_date`, đồng bộ cờ chiếm chỗ với phiên `active`,
vòng đời `parking_sessions` — kể cả một hàng `checking_out` còn đọng lại sau sự
cố sẽ làm readiness fail-closed). Endpoint này **không** chạy full
`PRAGMA integrity_check` hay `PRAGMA foreign_key_check`; hai PRAGMA đó chạy
trong rollout tường minh (`db_rollout.py`) và trong `scripts\verify.ps1`.

AI mặc định fail-closed. Chỉ đặt `AI_ENABLED=true` trong đúng môi trường đã
được duyệt gọi provider; có `GEMINI_API_KEY` nhưng cờ này tắt thì năm endpoint
sinh nội dung AI trả 503 và không tạo Gemini client (các endpoint đọc lịch sử
báo cáo AI vẫn hoạt động bình thường).

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
ESLint và production build trên mọi lần push hoặc pull request; một job Windows riêng khóa các
semantics rollout SQLite (`os.link`, `os.replace`, URI và file locking). `verify.ps1` chụp
SHA-256, kích thước, mtime và trạng thái sidecar của hai DB local trước/sau, rồi fail nếu test
vô tình làm thay đổi bất kỳ file được bảo vệ nào.

Thiết kế 3NF và ERD tự chứa nằm tại [docs/KT1_Database_Design.md](docs/KT1_Database_Design.md).
Chi tiết kiến trúc, prompt và minh chứng dùng AI trong SDLC nằm tại [docs/AI_SDLC.md](docs/AI_SDLC.md).
Checklist backup, UAT, rollout và rollback SQLite nằm tại [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Kiến trúc production (frontend Cloudflare CDN, hai backend container,
PostgreSQL managed, GitHub Actions Continuous Delivery và Blue/Green) cùng
runbook bootstrap/rollback nằm tại
[docs/PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md).
