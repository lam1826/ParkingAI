# Triển khai production: Cloudflare Pages + Fly.io + Supabase

## 1. Kiến trúc chuẩn

| Thành phần | Dịch vụ | Định danh production |
| --- | --- | --- |
| Frontend | Cloudflare Pages, Git integration từ `main` | `https://parkingai.am` |
| Backend | Fly.io Machines | app `parkingai-api-lam1826`, region `sin` |
| Database | Supabase PostgreSQL | project `parkingai`, region `ap-southeast-1` |
| API domain | Fly certificate + Cloudflare DNS | `https://api.parkingai.am` |
| CI/CD backend | GitHub Actions sau CI xanh | `.github/workflows/delivery.yml` |

Cloudflare Pages tự build frontend khi `main` thay đổi. Biến build
`VITE_API_URL` của Pages phải là `https://api.parkingai.am`. Backend chỉ được
deploy từ commit đầy đủ 40 ký tự thuộc `main` và đã vượt workflow `CI`.

## 2. Cấu hình Fly.io

`backend/fly.toml` là nguồn cấu hình được version-control. Cấu hình này:

- build `backend/Dockerfile`;
- chạy `alembic -c alembic.ini upgrade head` bằng `release_command` trước khi
  thay Machines;
- kiểm tra `/ready`;
- duy trì ít nhất một Machine chạy ở `sin`;
- dùng rolling deployment và rollback tự động nếu health check không đạt.

Các giá trị bí mật chỉ nằm trong Fly Secrets:

| Secret | Nội dung |
| --- | --- |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `SECRET_KEY` | JWT secret production riêng |
| `CORS_ORIGINS` | `https://parkingai.am` |
| `MANAGER_REGISTRATION_CODE` | mã đăng ký quản lý riêng |
| `ADMIN_REGISTRATION_CODE` | mã đăng ký quản trị riêng |
| `GEMINI_API_KEY` | chỉ đặt khi AI đã được duyệt |
| `AI_ENABLED` | mặc định `false`, chỉ bật sau UAT/chi phí |

Không commit connection string, password, token hoặc private key. Với Fly là
backend chạy lâu dài, dùng Supabase direct connection nếu Fly kết nối IPv6 ổn;
nếu không, dùng Shared Pooler **session mode** cổng `5432`. Không dùng
transaction mode cổng `6543` cho Alembic hoặc prepared statement mặc định.
URL plain `postgresql://` được ứng dụng chuẩn hóa sang psycopg 3; có thể lưu
trực tiếp dạng `postgresql+psycopg://`.

Kiểm tra tên secret mà không đọc giá trị:

```powershell
flyctl secrets list -a parkingai-api-lam1826
flyctl status -a parkingai-api-lam1826
```

## 3. GitHub Actions

Tạo GitHub Environment `production`, bật Required reviewers nếu repository hỗ
trợ và thêm repository/environment secret:

| Secret | Cách tạo |
| --- | --- |
| `FLY_API_TOKEN` | `flyctl tokens create deploy -a parkingai-api-lam1826` |

Chỉ dùng deploy token giới hạn theo app, không dùng token tài khoản rộng. Sau
khi CI của `main` xanh, Continuous Delivery sẽ:

1. khóa SHA release và xác minh SHA thuộc `origin/main`;
2. build frontend với `VITE_API_URL=https://api.parkingai.am` làm bằng chứng;
3. chạy `flyctl deploy --remote-only` từ thư mục `backend`;
4. chạy Alembic release command trên Supabase trước rollout;
5. gắn `RELEASE_ID=<git-sha>` vào Machine;
6. kiểm tra `/ready`, release ID và CORS từ `parkingai.am`.

Có thể chạy lại chính xác một commit đã thuộc `main` bằng `workflow_dispatch`
và input `commit_sha`.

## 4. Cloudflare Pages và domain

Cloudflare Pages project phải theo dõi branch `main` với:

```text
Root directory: frontend
Build command: npm run build
Build output directory: dist
Environment variable: VITE_API_URL=https://api.parkingai.am
```

`parkingai.am` là custom domain của Pages. `api.parkingai.am` trỏ tới hostname
Fly do `flyctl certs setup api.parkingai.am` cung cấp; certificate phải ở trạng
thái `Ready`. Không proxy `/api` qua Pages và không dùng same-origin fallback
cho production.

## 5. Xác minh sau deploy

```powershell
Invoke-RestMethod https://api.parkingai.am/ready
Invoke-RestMethod https://api.parkingai.am/
Invoke-WebRequest https://parkingai.am/
flyctl certs list -a parkingai-api-lam1826
flyctl status -a parkingai-api-lam1826
```

Kết quả bắt buộc:

- `/ready` trả `{"status":"ready"}`;
- endpoint `/` trả `release_id` bằng SHA vừa deploy, không phải `development`;
- preflight từ `https://parkingai.am` trả
  `Access-Control-Allow-Origin: https://parkingai.am`;
- frontend bundle dùng `https://api.parkingai.am`;
- Fly health check passing và certificate `api.parkingai.am` Ready.

## 6. Khôi phục admin cũ một lần

Nếu PostgreSQL production chưa có username `admin` nhưng SQLite cũ còn tài
khoản này, dùng `backend/restore_legacy_admin.py`. Lệnh chỉ đọc đúng tài khoản
`admin` đang hoạt động và thuộc role `admin`, giữ nguyên bcrypt hash, từ chối
ghi đè username đã có và không in hash ra log.

```powershell
flyctl ssh sftp put backend/database/parking.db /tmp/parkingai-legacy-admin.db `
  --app parkingai-api-lam1826 --mode 0600
flyctl ssh console --app parkingai-api-lam1826 --pty=false `
  --command "cd /app && python restore_legacy_admin.py --source /tmp/parkingai-legacy-admin.db --confirm-legacy-admin"
flyctl ssh console --app parkingai-api-lam1826 --pty=false `
  --command "rm -f /tmp/parkingai-legacy-admin.db"
```

Chỉ chạy sau khi release chứa script đã healthy. Sau đó xác minh đăng nhập và
`GET /api/auth/me`, rồi kiểm tra tệp tạm đã bị xóa. Không commit SQLite cũ,
không truyền password/hash qua command line và không chạy full importer vào
database production đã có dữ liệu.

## 7. Rollback

Liệt kê release rồi rollback image nếu cần:

```powershell
flyctl releases -a parkingai-api-lam1826
flyctl releases rollback <version> -a parkingai-api-lam1826
```

Migration phải theo expand/contract và tương thích ngược ít nhất một release.
Không rollback destructive migration chỉ bằng cách đổi image. Trước migration
contract, xác nhận Supabase backup/PITR và hoàn tất thời gian quan sát release
expand. Khi backend rollback, giữ `VITE_API_URL` và DNS không đổi.
