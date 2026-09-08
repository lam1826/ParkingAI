# Kết quả xử lý review/debug vòng 2 — 08/09/2026

Tài liệu này đối chiếu các ticket trong `docs/tickets/tickets.json` với mã đã
triển khai. Bốn lỗi P0 nằm ở commit `532569f`; các mục còn lại thuộc release
candidate hiện tại. Không dùng trạng thái trong bảng này để thay thế CI
PostgreSQL hoặc cổng backup production.

| Ticket | Trạng thái mã | Bằng chứng chính |
| --- | --- | --- |
| PARK-101 | Đã sửa | v1 giữ kiểm tra email đầu vào nhưng không làm 500 khi dữ liệu cũ có email lạ |
| PARK-102 | Đã sửa | replay portal kết thúc transaction trước audit; kiểm thử SQLite file thật |
| PARK-103 | Đã sửa | giới hạn tải trước DB, inference không giữ session, audit ngoài event loop |
| PARK-104 | Đã sửa | `/dashboard` trả JSON cho API và SPA cho trình duyệt theo `Accept` |
| PARK-105 | Đã sửa | lifespan bảo trì production, expiry lười, luồng đơn manual và hủy đơn |
| PARK-106 | Đã sửa | horizon 30 ngày, tối đa 5 đặt chỗ còn hiệu lực mỗi khách, lỗi commitment rõ |
| PARK-107 | Đã sửa | API và trigger hai dialect chặn ngừng khu khi còn cam kết; revision `20260908_01` |
| PARK-108 | Đã sửa | cấm tự duyệt, hiển thị role người yêu cầu, admin có API/UI gỡ liên kết |
| PARK-109 | Đã sửa | lazy import thử lại một lần và reload khi preload/chunk lỗi |
| PARK-110 | Đã sửa | login không mang bearer cũ, 5xx profile giữ JWT, path match đúng, xoay request key |
| PARK-111 | Đã sửa | chỉ tin `Fly-Client-IP` khi bật cờ; Fly bật, Caddy gỡ header, uvicorn giới hạn proxy |
| PARK-112 | Đã sửa | authz trước lookup, `no-store`, DTO allowlist và 422 không phản chiếu secret |
| PARK-113 | Đã sửa | nhận đúng slot đã đặt, request ID kết thúc không replay, một xe không giữ hai chỗ |
| PARK-114 | Đã sửa | eviction ảnh terminal, retention áp ảnh cũ, trạng thái engine degraded và nút xóa |
| PARK-115 | Mã gate đã xong; chờ môi trường | backup/PITR fail-closed trước migration, action/image ghim SHA/digest, runbook rollback Pages |
| PARK-116 | Mã/test đã xong; chờ CI PostgreSQL | thứ tự khóa `vehicle → slot`; test write path và tranh chấp trên PostgreSQL 16 |
| PARK-117 | Đã sửa | metadata UTC, thời gian nghiệp vụ UTC+7, thông báo waitlist idempotent |

## Kết quả kiểm tra candidate cục bộ

- Backend toàn bộ lượt cuối sau mọi sửa đổi: **1.177 đạt, 8 bỏ qua, 0 lỗi**
  trong 640,01 giây. Tám skip gồm bảy ca cần PostgreSQL CI/host POSIX và một ca
  chỉ chạy trên POSIX.
- Frontend: 134/134 test, ESLint sạch, Vite production build thành công.
- Impeccable detector: không có phát hiện (`[]`).
- Demo bằng `scripts/start_demo.ps1` trên DB/cổng tạm: `/ready` 200, đăng nhập
  `admin_demo` 200, `/dashboard` JSON 200 và deep-link `/portal` 200.

## Điều kiện phát hành còn phải qua bên ngoài

1. GitHub environment `production` có `FLY_API_TOKEN`,
   `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF` và Required reviewers.
2. Supabase trả PITR đang bật hoặc backup `COMPLETED` trong 36 giờ; thiếu dữ
   liệu này thì workflow dừng trước `flyctl deploy` và trước Alembic.
3. CI chạy test PostgreSQL 16 mới, sau đó CD xác minh `/ready`, release SHA và
   CORS. Chỉ khi ba điểm này đạt mới ghi release production là hoàn thành.
