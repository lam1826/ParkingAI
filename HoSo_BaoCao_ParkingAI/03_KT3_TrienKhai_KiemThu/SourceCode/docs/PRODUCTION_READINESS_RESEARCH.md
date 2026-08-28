# Nghiên cứu mức sẵn sàng production: Cloudflare Pages + Fly.io + Supabase

Ngày đối chiếu: **2026-08-29**. Phạm vi chỉ đọc: mã nguồn và tài liệu chính thức hiện hành của Cloudflare, Fly.io và Supabase. Không kiểm tra dashboard/tài khoản, không thay đổi dịch vụ và không đọc hay ghi bí mật. Vì vậy, mọi trạng thái plan, backup, PITR, cảnh báo và số Machine thực tế bên dưới đều là **chưa xác minh** cho tới khi chủ tài khoản cung cấp bằng chứng dashboard/API đã che bí mật.

## 1. Kiến trúc đã có bằng chứng trong repo

- `docs/PRODUCTION_DEPLOYMENT.md` xác định frontend `https://parkingai.am` chạy trên Cloudflare Pages, backend app Fly.io `parkingai-api-lam1826` tại `sin`, và database Supabase PostgreSQL project `parkingai` tại `ap-southeast-1`.
- `backend/fly.toml` cấu hình một process HTTP, VM 1 CPU/1 GiB, `min_machines_running = 1`, tự start/stop và probe `GET /ready` mỗi 30 giây. `/ready` trong `backend/main.py` thực sự kiểm tra kết nối/schema database và trả 503 khi database chưa sẵn sàng.
- Frontend là Vite SPA tĩnh; repo không có Pages Functions. Do đó quota Functions không nằm trên critical path hiện tại.

## 2. Phục hồi backup/PITR Supabase

### Bằng chứng từ nhà cung cấp

- Supabase tự tạo daily backup cho Pro/Team/Enterprise, với retention lần lượt 7/14/tối đa 30 ngày; Free không có automatic backup. PITR là add-on cho Pro/Team/Enterprise, yêu cầu ít nhất Small compute, thay thế daily backup, và hiện có giá xấp xỉ USD 100/200/400 mỗi tháng cho 7/14/28 ngày retention. Physical backup không tải trực tiếp được; khi cần bản portable phải tự tạo logical dump bằng CLI hoặc `pg_dump`. [Supabase — Database Backups](https://supabase.com/docs/guides/platform/backups)
- Restore tại chỗ làm project **không truy cập được** trong thời gian phục hồi; thời gian dừng phụ thuộc kích thước database. Đây không phải cách phù hợp để diễn tập trên production đang hoạt động. [Supabase — Database Backups, Restoration process](https://supabase.com/docs/guides/platform/backups#restoration-process)
- `Restore to a New Project` tạo một database copy mới từ physical backup hoặc mốc PITR để kiểm thử an toàn. Tính năng đang beta, chỉ dành cho paid plan và đòi source project đã bật physical backups. Bản copy gồm schema, data, indexes, database roles/permissions/users và Auth data; không copy Storage objects/settings, Edge Functions, Auth settings/API keys, Realtime settings, extensions/settings hoặc read replicas. [Supabase — Restore to a new project](https://supabase.com/docs/guides/platform/clone-project)

### Khuyến nghị diễn tập không gây rủi ro cho production

1. Chủ tài khoản chụp bằng chứng đã che thông tin nhạy cảm về plan, Postgres version/physical-backup eligibility, earliest/latest recovery point và retention; chốt RPO/RTO mong muốn. Không bấm restore tại chỗ.
2. Chọn một backup/mốc PITR có các sự kiện nghiệp vụ đã biết ở hai phía của mốc (ưu tiên bản ghi `audit_logs` hiện có), rồi dùng **Restore to a New Project**. Đây là thay đổi có chi phí và phải do owner phê duyệt.
3. Không trỏ `parkingai-api-lam1826` hoặc `parkingai.am` vào clone. Chỉ kết nối clone từ một môi trường kiểm thử cô lập bằng credential mới, có thời hạn và quyền tối thiểu.
4. Ghi bằng chứng bắt đầu/kết thúc để đo RTO; kiểm tra `alembic_version`, danh sách bảng/index/constraint/trigger, role và quyền, row count các bảng nghiệp vụ, các bản ghi trước/sau mốc PITR, rồi chạy smoke test read/write/rollback trên **clone**. Với PITR, bản ghi trước mốc phải có và bản ghi sau mốc phải không có.
5. Tạo thêm logical dump đã mã hóa, kiểm tra `pg_restore --list` và diễn tập restore vào một PostgreSQL tạm nếu tổ chức cần bản backup độc lập nhà cung cấp. Physical backup Supabase không thể tải trực tiếp.
6. Lưu biên bản RPO/RTO, sai lệch và người phê duyệt; sau thời gian giữ bằng chứng, owner xóa clone/credential theo quy trình thay đổi có kiểm soát.

**Tiêu chí đạt:** chỉ đánh dấu “backup restore verified” khi một bản backup thật đã được restore sang project mới và kiểm tra toàn vẹn thành công. Chỉ xem “PITR verified” khi một mốc chính xác được khôi phục và ranh giới dữ liệu trước/sau mốc được chứng minh. Việc chỉ nhìn thấy backup trong Dashboard chưa đủ.

## 3. Cảnh báo lỗi, downtime và tài nguyên

### Cloudflare Pages / DNS

**Bằng chứng:** Pages Project Updates có cảnh báo deployment started/failed/success trên mọi plan. Web Analytics miễn phí nhưng chủ yếu đo trải nghiệm/traffic người dùng; weekly summary có trên mọi plan. Standalone Health Checks có analytics và thông báo thay đổi healthy/unhealthy nhưng chỉ từ Pro trở lên (Free: 0 check; Pro: 10; Business: 50). Email notification có trên Free; webhook từ Pro; PagerDuty từ Business, với ngoại lệ phụ thuộc highest zone plan của account. [Cloudflare — Available Notifications](https://developers.cloudflare.com/notifications/notification-available/), [Cloudflare — Notifications](https://developers.cloudflare.com/notifications/), [Cloudflare — Health Checks](https://developers.cloudflare.com/health-checks/), [Cloudflare Pages — Web Analytics](https://developers.cloudflare.com/pages/how-to/web-analytics/)

**Khuyến nghị:** bật Project Updates cho production/deployment failed; bật Web Analytics; nếu account từ Pro, tạo Health Check cho `https://parkingai.am/` và `https://api.parkingai.am/ready`, cảnh báo cả unhealthy và recovery. Nếu đang ở Free, owner phải chọn nâng Pro hoặc một synthetic uptime monitor độc lập; Pages deployment alert và Web Analytics không thay thế probe uptime.

### Fly.io backend

**Bằng chứng:** Fly cung cấp built-in Prometheus/Grafana và các metric HTTP status/latency, instance up, CPU/load, memory, exit code/OOM. Dữ liệu managed Prometheus chỉ giữ khoảng 15 ngày. Fly **không có built-in metric alerting**; tài liệu yêu cầu kết nối Grafana alerting hoặc Prometheus/Alertmanager. Health check loại Machine/service có thể dừng rollout hoặc rút Machine lỗi khỏi routing, nhưng một health check thất bại không tự restart/stop Machine. [Fly.io — Metrics](https://fly.io/docs/monitoring/metrics/), [Fly.io — Health Checks](https://fly.io/docs/reference/health-checks/)

**Khuyến nghị:** nối Fly Prometheus vào cùng nơi nhận cảnh báo và đặt tối thiểu: không có instance healthy/`fly_instance_up` trong 2 phút; bất kỳ OOM exit; memory available dưới 15% trong 10 phút; CPU/load bão hòa kéo dài; tỷ lệ 5xx vượt 1% cảnh báo và 5% critical trong 5 phút; p95 latency vượt SLO; `/ready` thất bại từ probe ngoài. Tinh chỉnh ngưỡng bằng số liệu tải thật, không coi các con số khởi đầu là SLO cuối cùng.

Repo chỉ cam kết **ít nhất một** Machine chạy, còn số Machine thực tế chưa biết. Fly khuyến nghị hơn một Machine là mức redundancy cơ bản; owner cần xác minh `fly scale show` và phê duyệt chạy ít nhất 2 Machine nếu uptime production quan trọng. [Fly.io — App Availability and Resiliency](https://fly.io/docs/apps/app-availability/)

### Supabase PostgreSQL

**Bằng chứng:** mỗi project có Metrics API tương thích Prometheus với khoảng 200 series về CPU, IO, WAL, connections và queries; API hiện beta nên tên/label có thể đổi. Reports built-in hiển thị database/resource health; Free chỉ xem tối đa 24 giờ, Pro 7 ngày, Team/Enterprise 28 ngày. Log Drains cho phép dựng alert/dashboard từ log nhưng chỉ có ở Pro/Team/Enterprise. [Supabase — Metrics API](https://supabase.com/docs/guides/monitoring-and-debugging/metrics), [Supabase — Reports](https://supabase.com/docs/guides/monitoring-and-debugging/reports), [Supabase — Log Drains](https://supabase.com/docs/guides/monitoring-and-debugging/log-drains)

**Khuyến nghị:** scrape Metrics API vào cùng hệ cảnh báo với Fly; alert database unreachable, CPU/memory/IOWait cao kéo dài, connection utilization trên 70% warning/85% critical, disk trên 80% warning/90% critical, WAL tăng bất thường, blocked/long-running queries và lỗi Postgres. Trên Pro+, dùng Log Drain cho Postgres events/long-term retention. Theo dõi status page Supabase qua RSS/Atom để phân biệt lỗi nền tảng với lỗi ứng dụng. [Supabase — Platform status](https://supabase.com/docs/guides/platform#platform-status)

## 4. Giới hạn plan/tier cần owner quyết định

| Dịch vụ | Bằng chứng hiện hành | Quyết định cần owner |
| --- | --- | --- |
| Supabase Free | Không automatic backup/PITR; database quota 500 MB và project có thể pause sau 1 tuần không hoạt động. | Không dùng Free cho mục tiêu production có DR. Xác nhận ít nhất Pro. [Pricing](https://supabase.com/pricing) |
| Supabase Pro/Team | Daily backup 7/14 ngày; PITR tốn thêm khoảng USD 100/7 ngày và cần Small compute; clone restore chỉ paid + physical backups; Log Drains chỉ Pro+. | Chọn RPO/retention, bật PITR nếu mất tối đa một ngày dữ liệu là không chấp nhận được; duyệt chi phí clone diễn tập và log drain. [Backups](https://supabase.com/docs/guides/platform/backups), [Log Drains](https://supabase.com/docs/guides/monitoring-and-debugging/log-drains) |
| Supabase disk/cost | Free vào read-only trên 500 MB. Paid auto-expand tại 90%; nếu đạt 95% sau khi hết quota 4 lần resize/24h có thể vào read-only. Spend Cap Pro không bao phủ PITR, compute, Log Drain hours/events hoặc extra IOPS/throughput. | Chốt cảnh báo disk trước 80/90%, Spend Cap và ngân sách overage; xác minh compute/connection cap trước load test. [Database size](https://supabase.com/docs/guides/platform/database-size), [Cost control](https://supabase.com/docs/guides/platform/cost-control) |
| Cloudflare Free | Pages: 500 build/tháng, 1 concurrent build; deployment notification có trên mọi plan nhưng Health Checks không có. | Nếu cần synthetic uptime first-party và webhook, nâng Pro; nếu không, chọn monitor ngoài. [Pages limits](https://developers.cloudflare.com/pages/platform/limits/), [Health Checks](https://developers.cloudflare.com/health-checks/) |
| Cloudflare Pro/Business | Pro: 5.000 build/tháng, 5 concurrent build, 10 Health Checks, webhook. Business: 20.000 build/tháng, 20 concurrent build, 50 Health Checks, PagerDuty. | Chọn tier theo kênh trực ca và nhu cầu check; không nâng tier chỉ vì SPA static nếu monitor ngoài đã đáp ứng SLO. [Pages limits](https://developers.cloudflare.com/pages/platform/limits/), [Notifications](https://developers.cloudflare.com/notifications/) |
| Fly.io | Tính tiền theo tài nguyên; managed metrics/Grafana hiện không tính thêm nhưng chỉ giữ khoảng 15 ngày và không có alerting. Shared CPU 1x/1 GiB niêm yết khoảng USD 5,92/tháng; cấu hình thực tế phải kiểm tra. Technical email support là add-on từ USD 29/tháng. | Duyệt chi phí Machine thứ hai, nơi chạy alerting/lưu dài hạn và support plan nếu cần SLA phản hồi. [Pricing](https://fly.io/docs/about/pricing/), [Metrics](https://fly.io/docs/monitoring/metrics/), [Support](https://fly.io/docs/about/support/) |

## 5. Thứ tự thực hiện đề xuất

1. Owner cung cấp bằng chứng plan/backup/PITR/compute và retention hiện tại của ba tài khoản, đã che ID/token/credential.
2. Chốt RPO, RTO, uptime SLO, kênh trực và ngân sách; sau đó mới chọn PITR, Cloudflare Pro hay monitor ngoài, số Fly Machine và log retention.
3. Cấu hình cảnh báo deployment + synthetic uptime trước; tiếp theo metric/resource + log alerts; thử từng rule bằng tín hiệu test có kiểm soát và ghi bằng chứng nhận/recovery notification.
4. Diễn tập restore sang Supabase project mới, đo RTO và chạy kiểm tra toàn vẹn/luồng nghiệp vụ trên clone.
5. Chỉ sau khi cảnh báo và DR drill đạt mới chạy load/security/authorization test production theo cửa sổ thay đổi đã phê duyệt.
