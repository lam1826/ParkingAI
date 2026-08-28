# Triển khai production: CDN + PostgreSQL + Blue/Green

Tài liệu này là runbook vận hành cho ParkingAI. Mục tiêu là phát hành bản mới
với thời gian gián đoạn gần bằng 0, có cổng kiểm thử/duyệt rõ ràng và rollback
traffic nhanh mà không sửa lịch sử Git hay hạ schema dữ liệu.

## 1. Kiến trúc đích

```text
Người dùng
   |
   +--> Cloudflare Pages/CDN (React, config.js theo môi trường)
   |          |
   |          +--> https://api.example.com
   |                         |
   |                      Caddy/TLS
   |                         |
   |              +----------+----------+
   |              |                     |
   |         backend_blue          backend_green
   |              |                     |
   |              +----------+----------+
   |                         |
   +--------------> Managed PostgreSQL (TLS, backup/PITR)
```

- Frontend là một artifact tĩnh duy nhất. `config.js` được ghi lúc deploy để
  cùng artifact có thể trỏ tới API staging hoặc production mà không build lại.
- Hai backend container luôn tồn tại. Chỉ một màu nhận traffic; màu còn lại
  được pull, migrate, health-check và smoke-test trước khi Caddy reload cấu
  hình. Màu cũ không bị dừng nên có thể chuyển traffic lại ngay.
- Backend không lưu session trên local disk; JWT và dữ liệu nghiệp vụ dùng
  chung PostgreSQL nên request kế tiếp có thể đến container khác.
- PostgreSQL là dịch vụ managed, bật TLS, backup tự động và point-in-time
  recovery. SQLite chỉ còn là nguồn import một lần hoặc môi trường local.

Hai container trên **một VPS** chống lỗi ứng dụng/deploy, nhưng không chống
VPS hoặc availability-zone bị hỏng. Khi cần HA hạ tầng thật, chạy hai host ở
hai failure domain sau load balancer managed; cơ chế image/readiness vẫn giữ
nguyên.

## 2. Điều kiện tiên quyết

1. Một database PostgreSQL 16+ rỗng; tài khoản ứng dụng là owner của schema và
   có quyền `CREATE EXTENSION btree_gist` trong lần migration đầu.
2. Backup tự động + PITR đã bật, retention tối thiểu 7 ngày, có cảnh báo dung
   lượng/kết nối/CPU.
3. VPS Linux có Docker Engine, Docker Compose v2, `curl`, `rsync`, `flock` và
   SSH key-only. Firewall chỉ mở 22 (giới hạn IP CI nếu có), 80 và 443.
4. DNS `API_DOMAIN` trỏ tới VPS. Cloudflare SSL/TLS đặt **Full (strict)** nếu
   record API được proxy qua Cloudflare.
5. Cloudflare Pages project dùng Direct Upload; production branch và custom
   domain frontend đã cấu hình.
6. VPS đã `docker login ghcr.io` bằng deploy token chỉ có `read:packages` nếu
   package backend là private.

## 3. Bootstrap server (mỗi môi trường một state riêng)

Ví dụ production dùng `/opt/parkingai-production`; staging dùng một path và
`COMPOSE_PROJECT_NAME` khác. Không dùng chung database giữa hai môi trường.

```bash
sudo install -d -o deploy -g deploy -m 750 \
  /opt/parkingai-production/control \
  /opt/parkingai-production/state/caddy

cp deploy/.env.production.example \
  /opt/parkingai-production/state/.env.production
chmod 600 /opt/parkingai-production/state/.env.production
```

Điền các giá trị thật trực tiếp trên server. `DATABASE_URL` phải dùng
`postgresql+psycopg://` và `sslmode=require` (hoặc chế độ xác minh CA do nhà
cung cấp yêu cầu). Sinh `SECRET_KEY` riêng cho staging/production; không dùng
registration code mẫu; giữ `AI_ENABLED=false` cho tới khi UAT/chi phí Gemini
được duyệt.

Không đặt secret trong GitHub variable thường, repository, image, frontend
artifact hoặc file `config.js`.

## 4. Cấu hình GitHub

Tạo hai GitHub Environments: `staging` và `production`.

### Variables trong từng environment

| Tên | Ví dụ |
| --- | --- |
| `DEPLOY_HOST` | IP/hostname VPS |
| `DEPLOY_PORT` | `22` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PATH` | `/opt/parkingai-production` |
| `PUBLIC_API_URL` | `https://api.example.com` |
| `CLOUDFLARE_PAGES_PROJECT` | tên project Pages |
| `CLOUDFLARE_PAGES_BRANCH` | `staging` hoặc production branch |

### Secrets trong từng environment

| Tên | Nội dung |
| --- | --- |
| `DEPLOY_SSH_PRIVATE_KEY` | private key riêng cho CD |
| `DEPLOY_KNOWN_HOSTS` | output đã xác minh của `ssh-keyscan`, chống MITM |
| `CLOUDFLARE_API_TOKEN` | token chỉ có quyền Pages deploy cần thiết |
| `CLOUDFLARE_ACCOUNT_ID` | account ID Cloudflare |

Với environment `production`:

1. Bật **Required reviewers** và không cho bypass protection.
2. Reviewer chỉ approve sau khi staging/UAT xanh và đã xác nhận backup/PITR.
3. Sau khi protection hoạt động, tạo repository variable
   `PRODUCTION_DEPLOY_ENABLED=true`. Nếu biến thiếu hoặc khác `true`, job
   production bị skip (fail-closed).

Sau khi staging server/Pages/secrets đã bootstrap xong, tạo repository variable
`STAGING_DEPLOY_ENABLED=true`. Trước thời điểm đó workflow vẫn build/publish
artifact nhưng chủ động skip deploy, nên việc merge code hạ tầng này không làm
CI đỏ vì credential chưa tồn tại. Hai cờ enable phải là **repository variable**,
không phải environment variable, vì GitHub đánh giá điều kiện job trước khi
job được cấp environment.

## 5. Khởi tạo PostgreSQL và import SQLite một lần

Luôn thực hiện trong maintenance window **trước khi có khách hàng production**.
Không chạy importer trong mỗi release.

1. Dừng mọi backend đang ghi SQLite, checkpoint WAL và tạo bản backup lạnh.
2. Ghi lại SHA-256/size/mtime của nguồn và sao thêm một bản ngoài server.
3. Chạy Alembic trên PostgreSQL rỗng:

   ```bash
   docker run --rm --env-file /opt/parkingai-production/state/.env.production \
     IMAGE_DIGEST alembic -c /app/alembic.ini upgrade head
   ```

4. Mount **bản copy backup** ở chế độ read-only và import:

   ```bash
   docker run --rm \
     --env-file /opt/parkingai-production/state/.env.production \
     --mount type=bind,src=/backup/parking.db,dst=/import/parking.db,readonly \
     IMAGE_DIGEST python /app/postgres_import.py \
       --source /import/parking.db --confirm-empty-target
   ```

Importer từ chối DB đích đã có dữ liệu, từ chối SQLite có WAL/journal sidecar,
kiểm tra readiness ở cả hai đầu và xác minh fingerprint nguồn không đổi. Không
trỏ importer vào file SQLite đang chạy.

Nếu đây là cài mới không import dữ liệu, tạo admin đầu tiên bằng terminal tương
tác để password không nằm trong command line/process list:

```bash
docker run --rm -it \
  --env-file /opt/parkingai-production/state/.env.production \
  IMAGE_DIGEST python /app/create_admin.py
```

## 6. Luồng phát hành bình thường

```text
feature branch -> Pull Request -> CI xanh -> review -> merge main
     -> build một frontend artifact + một backend image digest
     -> migrate/deploy Blue-Green staging -> UAT staging
     -> production environment approval
     -> migrate/deploy đúng image digest -> Cloudflare Pages production
```

Workflow `.github/workflows/delivery.yml` chỉ bắt đầu tự động khi workflow
`CI` của một push lên `main` thành công. Backend được deploy bằng **digest**,
không bằng tag mutable. Production dùng lại đúng frontend artifact và image đã
qua staging.

Trình tự Blue/Green trên mỗi server:

1. khóa deploy để không có hai release chạy cùng lúc;
2. chạy `alembic upgrade head` bằng image mới;
3. pull và chỉ cập nhật màu inactive;
4. chờ Docker health `/ready` và smoke trực tiếp container;
5. Caddy reload cấu hình sang màu mới;
6. smoke qua HTTPS public;
7. chỉ sau khi pass mới ghi `.active-color`; container cũ tiếp tục chạy.

## 7. Quy tắc migration không gián đoạn: expand-contract

Blue/Green chỉ an toàn nếu **cả code cũ và code mới cùng chạy được trên schema
sau migration**. Mọi thay đổi DB phải chia nhỏ:

1. **Expand**: thêm cột/table/index nullable hoặc có default tương thích; không
   đổi tên/xóa cột đang được màu cũ dùng.
2. Deploy code ghi được cả contract cũ/mới; backfill bằng job có checkpoint,
   giới hạn batch và metrics.
3. Deploy code chuyển hoàn toàn sang contract mới, theo dõi ít nhất một chu kỳ
   rollback.
4. **Contract** trong release riêng: mới xóa cột/index cũ sau khi chắc chắn
   không còn binary nào phụ thuộc.

`/ready` của container cũ kiểm các bảng/index/constraint tối thiểu nó cần chứ
không ép DB phải bằng đúng Alembic head cũ; nhờ vậy nó vẫn phục vụ trong cửa sổ
giữa migration và traffic switch. Ngược lại, `migrate.sh` có gate riêng bắt DB
bằng đúng head của image mới trước khi deploy tiếp. Không được xóa backstop cũ
trong cùng release expand.

Không chạy downgrade schema khi rollback ứng dụng. Với migration thất bại,
traffic chưa switch nên giữ màu đang active, sửa migration theo hướng
roll-forward rồi chạy lại.

## 8. Rollback và xử lý sự cố

### Backend mới lỗi sau khi switch

```bash
PARKINGAI_STATE_DIR=/opt/parkingai-production/state \
  sh /opt/parkingai-production/control/scripts/rollback.sh
```

Script chỉ chuyển Caddy về container cũ nếu container đó healthy, smoke HTTPS
và tự phục hồi route ban đầu nếu smoke rollback thất bại. Nó không xóa
container, image, DB hay migration.

### Frontend lỗi

Redeploy artifact của commit production trước (hoặc rollback deployment trong
Cloudflare Pages), giữ `config.js` đúng API production. Backend và frontend nên
duy trì tương thích ngược ít nhất một release.

### PostgreSQL lỗi/mất dữ liệu

Dừng phát hành; không tự chạy Alembic downgrade. Dùng failover/PITR của nhà
cung cấp theo runbook riêng, sau đó `/ready` và smoke toàn bộ nghiệp vụ trước
khi mở traffic.

## 9. Gate nghiệm thu production

- `/` liveness và `/ready` được giám sát từ ngoài VPS mỗi 30–60 giây.
- Cảnh báo theo error rate 5xx, latency p95/p99, số phiên `checking_out` tồn
  tại, drift `is_occupied`, PostgreSQL connections/CPU/storage và backup fail.
- Log Caddy/backend tập trung, có retention; secret/token/password không vào
  log.
- UAT tối thiểu: login/RBAC, check-in đồng thời, check-out/tính phí, vé tháng,
  chỗ trống theo zone, báo cáo/doanh thu và AI fail-closed/provider mock.
- Chỉ bật Gemini production sau một live canary được duyệt với dữ liệu demo
  không PII, quota/cost alert và kill switch `AI_ENABLED=false` đã thử.
- Diễn tập rollback traffic và khôi phục backup định kỳ; backup chưa từng restore
  thử không được xem là đã kiểm chứng.

Mục tiêu thực tế là **near-zero downtime**, không hứa tuyệt đối zero downtime:
DNS/TLS, VPS đơn, managed database, thay đổi schema phá tương thích và nhà cung
cấp bên ngoài vẫn là failure mode cần SLO/monitoring và runbook riêng.
