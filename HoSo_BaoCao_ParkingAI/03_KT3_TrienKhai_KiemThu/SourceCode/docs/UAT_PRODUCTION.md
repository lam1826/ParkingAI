# UAT và kiểm định production

Tài liệu này là cổng phát hành cho kiến trúc Cloudflare Pages + Fly.io +
Supabase. UAT có ghi dữ liệu phải chạy trên **Supabase project được restore/clone
riêng**, không chạy trên database production. Probe production được giới hạn ở
đăng nhập và `GET`.

## 1. Phạm vi và trách nhiệm

| Vai trò | Người thực hiện | Trách nhiệm |
| --- | --- | --- |
| Product owner | Chưa chỉ định | Chấp nhận nghiệp vụ, sai lệch và rủi ro còn lại |
| UAT lead | Chưa chỉ định | Quản lý dữ liệu UAT, bằng chứng và retest |
| Customer thật | Chưa chỉ định | Đăng ký, hồ sơ và trải nghiệm bị từ chối quyền |
| Nhân viên bãi xe | Chưa chỉ định | Vận hành check-in/check-out và dữ liệu danh mục |
| Manager | Chưa chỉ định | Kiểm tra người dùng, audit và báo cáo, không sửa quyền admin |
| Admin | Chưa chỉ định | Quản trị user/role và xử lý sự cố |

Không ghi “UAT đạt” khi chưa có tên người thực hiện, ngày chạy, release SHA và
bằng chứng. Không dùng thông tin cá nhân hoặc biển số thật trong dữ liệu UAT.

## 2. Môi trường và điều kiện vào

1. Restore một physical backup hoặc mốc PITR sang Supabase project mới theo
   [PRODUCTION_READINESS_RESEARCH.md](PRODUCTION_READINESS_RESEARCH.md). Không
   đổi `DATABASE_URL` của Fly production.
2. Tạo backend UAT riêng hoặc chạy bản release ứng viên cục bộ với credential
   ngắn hạn của clone. Frontend UAT phải trỏ vào backend UAT, không trỏ vào
   `api.parkingai.am` cho các test có ghi dữ liệu.
3. Ghi `release SHA`, URL UAT, Supabase clone ID đã che bớt, người phê duyệt và
   thời điểm hết hạn credential. Giữ `AI_ENABLED=false` trừ khi có ca kiểm thử
   provider được phê duyệt riêng.
4. Xác nhận `/ready` trả `200 {"status":"ready"}`, migration ở đúng revision,
   không có cảnh báo schema/integrity, và đã tạo bốn persona riêng:
   `customer`, `staff`, `manager`, `admin`.
5. Dùng tiền tố dữ liệu `UAT-YYYYMMDD-<tester>` để có thể truy vết/xóa sau UAT.

## 3. Ma trận quyền phải đạt

| Năng lực | Customer | Staff | Manager | Admin |
| --- | :---: | :---: | :---: | :---: |
| Đăng nhập, xem/sửa hồ sơ, đổi mật khẩu | Có | Có | Có | Có |
| Dashboard và vận hành bãi xe | Không | Có | Có | Có |
| Zone, slot, loại xe, giá, khách, xe, vé tháng, phiên đỗ | Không | Có | Có | Có |
| Xem danh sách user/role và audit | Không | Không | Có | Có |
| Tạo/sửa/xóa user | Không | Không | Không | Có |
| Tạo/sửa/xóa role | Không | Không | Không | Có |

Với mỗi ô “Không”, kiểm tra cả giao diện (route/nút không xuất hiện hoặc trang
403) và API trực tiếp (HTTP `401/403`). Không chấp nhận chỉ ẩn nút ở frontend.

Probe không ghi dữ liệu để kiểm tra ranh giới API production:

```powershell
$env:PARKINGAI_PROBE_CUSTOMER_USERNAME = "<secret>"
$env:PARKINGAI_PROBE_CUSTOMER_PASSWORD = "<secret>"
# Khai báo tương tự STAFF, MANAGER và ADMIN trong session tạm thời.
.\.venv\Scripts\python.exe scripts\production_rbac_probe.py `
  --role customer --role staff --role manager --role admin
```

Không đưa các biến trên vào repo, workflow log hay ảnh chụp. Xóa biến khỏi
session sau khi chạy.

## 4. Kịch bản UAT đầu-cuối

Ghi kết quả từng ca là `PASS`, `FAIL` hoặc `BLOCKED`, kèm ảnh/video, request ID
hoặc dòng audit tương ứng.

| ID | Persona | Kịch bản và kết quả mong đợi |
| --- | --- | --- |
| AUTH-01 | Customer | Đăng ký customer, đăng nhập, logout, đăng nhập lại; sai mật khẩu trả thông báo chung, không tiết lộ user có tồn tại. |
| AUTH-02 | Mọi role | Hồ sơ phản ánh đúng role; sửa tên hợp lệ; đổi mật khẩu yêu cầu mật khẩu cũ. Ghi nhận token đã phát hành có thể còn hiệu lực tối đa 30 phút theo contract hiện tại. |
| AUTH-03 | Admin | Khóa một user UAT; user đó không đăng nhập và token hiện có không truy cập được. Mở khóa và retest. |
| RBAC-01 | Customer | Không mở được dashboard hoặc mọi module quản lý; gọi trực tiếp `/api/v1/zones`, `/users`, `/roles` bị từ chối. |
| RBAC-02 | Staff | Vào các module vận hành; `/users`, `/roles`, audit và thao tác admin bị từ chối. |
| RBAC-03 | Manager | Xem user/role/audit nhưng không tạo, sửa, xóa user/role; API trả 403 cho thao tác vượt quyền. |
| RBAC-04 | Admin | Tạo user UAT, gán role hợp lệ, khóa/mở khóa; bảo vệ role hệ thống khỏi rename/delete. |
| CFG-01 | Staff | Tạo zone và slot UAT; sức chứa/occupied đồng bộ; không vô hiệu hóa tài nguyên đang được phiên active sử dụng. |
| CFG-02 | Staff | Tạo loại xe và bảng giá có ngày hiệu lực; từ chối khoảng giá/ngày sai và quan hệ đang được tham chiếu. |
| CRM-01 | Staff | Tạo khách, xe và vé tháng; chuẩn hóa biển số; từ chối trùng lặp/quan hệ không tồn tại. |
| PARK-01 | Staff | Check-in xe vào slot tương thích; session thành `active`, slot occupied và audit có actor/thời gian đúng. |
| PARK-02 | Hai staff | Cùng lúc check-in một xe/slot; đúng một request thành công, request còn lại bị từ chối mà không tạo dữ liệu mồ côi. |
| PARK-03 | Staff | Check-out; thời lượng/phí đúng bảng giá tại thời điểm check-in, session `completed`, slot được giải phóng. Gửi lại request không thu phí hai lần. |
| PARK-04 | Staff | Vé tháng hợp lệ/không hợp lệ và bảng giá dự phòng cho kết quả phí đúng; timezone qua ranh giới ngày đúng. |
| SEARCH-01 | Staff | Lọc phiên theo biển số/ngày/trạng thái, sort và phân trang; tổng số không đổi hoặc trùng giữa trang. |
| REPORT-01 | Staff | Báo cáo ngày/tuần/tháng/năm khớp dữ liệu chuẩn; export mở được, đúng timezone, tiền tệ và không chứa dữ liệu ngoài quyền. |
| AUDIT-01 | Manager | Audit ghi đủ login nhạy cảm theo policy, CRUD, check-in/out và lỗi quyền; không chứa password, JWT hoặc secret. |
| AI-01 | Staff | Khi `AI_ENABLED=false`, endpoint AI fail-closed bằng 503 và không gọi provider. Nếu bật, phải có phê duyệt dữ liệu/chi phí riêng. |
| UX-01 | Mọi role | Chrome/Edge và viewport mobile/desktop: loading, empty, lỗi mạng, hết phiên, keyboard focus, nhãn/đơn vị tiếng Việt hoạt động. |
| REC-01 | UAT lead | Sau toàn bộ UAT, `/ready` vẫn 200; row count, constraint, index và các bất biến slot/session còn đúng. |

Mọi lỗi Sev-1/Sev-2 phải được sửa và chạy lại toàn bộ luồng liên quan. Sev-3
cần owner chấp nhận bằng văn bản và có issue/ETA trước phát hành.

## 5. Load, bảo mật và kiểm tra production không ghi dữ liệu

Probe tải dưới đây chỉ gọi `GET /ready`, bị chặn ở 10.000 request và 200 luồng.
Lần xác minh ban đầu nên dùng mức nhỏ; đây là smoke tải, không phải chứng minh
năng lực cực đại:

```powershell
.\.venv\Scripts\python.exe scripts\read_only_load_probe.py `
  --requests 100 --concurrency 10 --max-error-rate 0.01 --max-p95-ms 1500
```

Trước load test lớn phải chốt SLO, giới hạn Supabase connection/compute, ngân
sách Fly, cửa sổ thay đổi và tiêu chí dừng. Không chạy POST/check-in/check-out
song song trên production. Kiểm tra bảo mật gồm CSP/HSTS/header, CORS trusted và
untrusted origin, không cache auth/API, token hết hạn, tài khoản bị khóa, input
boundary, dependency scan và kiểm tra secret trong log/artifact.

Workflow `production-monitor.yml` chạy 15 phút/lần để kiểm tra frontend, API
readiness/release, header và CORS. Owner vẫn phải bật GitHub Actions failure
notifications hoặc nối kênh trực; workflow xanh không thay thế cảnh báo CPU,
memory, disk, connection, OOM và 5xx của nhà cung cấp.

Security audit ngày 2026-08-29 đã thay `python-jose` bằng PyJWT cho HS256, bỏ
dependency `ecdsa` không có bản vá và nâng `cryptography` lên 50.0.1. Sau thay
đổi, `pip-audit -r backend/requirements.txt` và `npm audit --omit=dev` đều báo
không có vulnerability đã biết; auth/audit regression có 91 test PASS. Advisory
gốc: [cryptography GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5)
và [python-ecdsa GHSA-wj6h-64fc-37mp](https://github.com/tlsfuzzer/python-ecdsa/security/advisories/GHSA-wj6h-64fc-37mp).

Các kiểm soát vẫn cần owner quyết định cho vận hành thương mại: rate limit/WAF
cho login và register ở edge, MFA hoặc SSO cho manager/admin, cơ chế thu hồi
token ngay khi đổi mật khẩu (hiện timeout tối đa 30 phút), secret rotation và
penetration test độc lập. CSP/header và dependency audit không thay thế các
kiểm soát này.

## 6. Điều kiện thoát và biên bản ký duyệt

- Tất cả ca bắt buộc PASS; không còn lỗi Sev-1/Sev-2.
- RBAC probe đủ bốn role PASS và không rò credential trong log.
- DR drill restore sang project mới đạt RPO/RTO đã chốt; có kiểm tra ranh giới
  dữ liệu trước/sau mốc PITR.
- Synthetic monitor đã phát cả cảnh báo lỗi và recovery thử nghiệm; resource
  alerts Fly/Supabase đã có người nhận.
- Smoke tải đạt SLO sơ bộ; test tải lớn có biên bản riêng nếu cần.
- 14 PR dependency được duyệt từng PR và test theo rủi ro; không auto-merge.

| Trường | Giá trị |
| --- | --- |
| Release SHA / ngày UAT | Chưa điền |
| Môi trường clone / dataset marker | Chưa điền |
| Tổng PASS / FAIL / BLOCKED | Chưa điền |
| RPO / RTO đo được | Chưa điền |
| Lỗi còn lại và quyết định chấp nhận | Chưa điền |
| Customer / Staff / Manager / Admin ký | Chưa điền |
| UAT lead / Product owner ký | Chưa điền |
