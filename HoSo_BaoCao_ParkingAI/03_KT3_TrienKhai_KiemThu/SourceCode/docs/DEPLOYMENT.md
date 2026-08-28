# Triển khai và UAT an toàn

Tài liệu này áp dụng cho SQLite của ParkingAI. Mục tiêu là không migration
nhầm database thật, không gọi Gemini ngoài ý muốn và luôn có đường phục hồi
đã kiểm chứng.

## 1. Nguyên tắc bắt buộc

- Import hoặc khởi động `main:app` không tự tạo bảng hay migration.
- Mọi migration phải chỉ rõ đường dẫn database bằng lệnh tường minh.
- Luôn thử trên bản sao mới trước; không dùng `--reload` trong UAT/production.
- DB nguồn phải ở trạng thái **cold**: backend đã dừng, dùng persistent
  `journal_mode=DELETE` và không còn file `-wal`, `-shm` hoặc `-journal`.
  Công cụ từ chối cả file không còn sidecar nhưng header vẫn ở WAL mode, kiểm
  tra lặp lại và fail-closed nếu sidecar xuất hiện. Fingerprint không thể khóa
  một writer bên ngoài trong khe rất ngắn ngay trước lúc publish; maintenance
  window vẫn là bắt buộc.
- `AI_ENABLED=false` trong UAT. Có API key nhưng cờ này tắt thì provider vẫn
  không được khởi tạo.
- Git revert không hoàn tác schema/dữ liệu SQLite; rollback database phải phục
  hồi nguyên file backup.

## 2. Preflight và bản sao UAT

Đứng tại thư mục gốc repository, dừng mọi backend đang dùng database nguồn.
Ghi lại SHA-256, kích thước và mtime của file nguồn:

```powershell
Get-FileHash -Algorithm SHA256 backend\database\parking.db
Get-Item backend\database\parking.db | Select-Object Length, LastWriteTimeUtc
Get-ChildItem backend\database -Force | Where-Object Name -Match 'parking\.db-(wal|shm|journal)$'
```

Nếu DB từng dùng WAL, trong maintenance window và khi mọi backend/writer đã
dừng, dùng một công cụ SQLite đáng tin cậy để chạy tuần tự:

```sql
PRAGMA wal_checkpoint(TRUNCATE);
PRAGMA journal_mode=DELETE;
```

Xác nhận câu lệnh thứ hai trả `delete`, đóng công cụ SQLite, rồi kiểm tra lại
không còn sidecar trước khi chạy rollout. Không thực hiện hai PRAGMA này khi
ứng dụng hoặc SQLite browser khác còn mở DB.

Tạo và migration một bản sao mới (đường dẫn đích không được tồn tại):

```powershell
python backend\db_rollout.py `
  --source backend\database\parking.db `
  --copy-to C:\ParkingAI-UAT\parking-copy.db
```

Công cụ dùng SQLite Backup API, mở nguồn ở `mode=ro`, chạy
`PRAGMA integrity_check`, từ chối source=output/tệp đích đã tồn tại,
`journal_mode` khác `DELETE` hoặc WAL/sidecar còn hoạt động, rồi xác minh lại
fingerprint của file nguồn + sidecar sau migration.
Candidate được migration/verify ở file `.partial` riêng và chỉ publish bằng
thao tác atomic no-clobber; nếu bất kỳ gate nào lỗi thì đường dẫn `--copy-to`
không xuất hiện và file partial được dọn.

Readiness/rollout cũng kiểm tra bất biến dữ liệu: `parking_slots.is_occupied`
phải bằng chính xác việc có hay không một `parking_sessions` trạng thái
`active` tham chiếu vị trí đó. Sai ở bất kỳ chiều nào đều làm rollout dừng;
công cụ không tự sửa cờ vì không thể suy đoán an toàn nguồn dữ liệu đúng.

Rollout còn dừng nếu một phiên đã gắn vé tháng không khớp phương tiện/ngày
check-in, hoặc **bất kỳ** phiên đang `active` nào — kể cả phiên đã gắn vé tháng
— không có bảng giá active đã hiệu lực tại thời điểm vào. Rollout cũng dừng khi
`parking_sessions` legacy có status ngoài `active`/`completed`/`cancelled` (ví
dụ một hàng `checking_out` đọng lại), có datetime sai dạng naive canonical,
hoặc có phiên `completed` thiếu `check_out_time`/`parking_fee`/`staff_out_id`.
Sau rollout, trigger khóa định danh phiên, quyền lợi vé tháng, dữ liệu tính tiền
đã hoàn tất và bảng giá đang phục vụ phiên mở; công cụ không tự gán vé, tạo giá
hay viết lại lịch sử để vượt qua các lỗi này.

SQLite không đảm bảo thứ tự nổ giữa nhiều BEFORE trigger trên cùng một câu
lệnh, nên các trigger của `parking_sessions` được viết với WHEN rời nhau để
thông báo lỗi là xác định. Thứ tự ưu tiên: (1) domain tiền
(`parking fee must be nonnegative integer` / `parking fee exceeds exact VND
range`), (2) hàng đã `completed` (`completed parking session is terminal` /
`... billing is immutable` / `parking session identity is immutable`),
(3) domain datetime (`parking session datetime invalid`), (4) domain và
transition của status (`parking session status invalid`), (5) state đầy đủ
(`parking session state incomplete`). Việc trừ bớt điều kiện chồng lấn không
nới lỏng bất biến nào — mọi hàng bị trừ vẫn bị chính trigger sở hữu nó ABORT.
Cùng thứ tự ưu tiên đó được áp dụng trong bước tiền kiểm của migration.

Nếu bảng `parking_sessions` legacy thiếu các cột vòng đời (`check_in_time`,
`check_out_time`, `staff_in_id`, `staff_out_id`, `monthly_pass_id`, ...),
migration bỏ qua phần trigger vòng đời thay vì đoán mò dữ liệu — và vì
`verify_schema` đòi đủ trigger nên `GET /ready` sẽ fail-closed rõ ràng trên
database đó. Hãy bổ sung cột rồi migration lại; không có đường tự sửa ngầm.

Không chạy đồng thời bất kỳ backend, SQLite browser hoặc script ghi DB nào.
Fingerprint là lớp phát hiện sai sót, không phải cơ chế khóa liên tiến trình mà
mọi writer bắt buộc tôn trọng.

Chạy lại migration trên chính bản sao để chứng minh tính idempotent:

```powershell
python backend\db_rollout.py --database C:\ParkingAI-UAT\parking-copy.db
```

`--database` cũng không sửa trực tiếp từng bước trên file hiện hữu: công cụ tạo
candidate sibling, chạy toàn bộ migration + schema manifest +
`integrity_check` + `foreign_key_check`, xác minh nguồn không đổi rồi mới
atomic replace. Dù vậy backup ngoài vẫn bắt buộc để rollback nghiệp vụ.

Khi thay một DB hiện hữu, công cụ giữ metadata bảo mật của file đích: Windows
dùng `ReplaceFileW` để giữ DACL/metadata của destination; POSIX giữ mode,
UID và GID rồi mới `os.replace`. Trên POSIX, ACL mở rộng/xattr phụ thuộc
filesystem và không nằm trong contract hiện tại; vì vậy phải chạy rollout bằng
đúng tài khoản sở hữu DB, kiểm tra ACL đặc thù của môi trường trước/sau và để
lệnh fail thay vì nâng quyền/chown âm thầm khi không đủ quyền.

## 3. UAT ứng dụng

Thiết lập biến môi trường cho đúng tiến trình trước khi import app:

```powershell
$env:DATABASE_URL = "sqlite:///C:/ParkingAI-UAT/parking-copy.db"
$env:AI_ENABLED = "false"
Set-Location backend
python -m uvicorn main:app --host 127.0.0.1 --port 8101
```

`GET /` chỉ là liveness. Chỉ tiếp tục UAT khi `GET /ready` trả HTTP 200 và
`{"status":"ready"}`. Endpoint này gọi `check_database_readiness(engine,
deep=False)`: mở SQLite read-only (`mode=ro` + `PRAGMA query_only=ON`) và kiểm
contract bảng/cột/type/nullability/PK/FK/index/trigger cùng khả năng truy cập.
Vì `deep=False`, `/ready` **không** chạy `PRAGMA integrity_check` hay
`PRAGMA foreign_key_check`. Hai PRAGMA đó chỉ chạy ở `deep=True` — tức trong
rollout tường minh (`db_rollout.py`, `create_admin.py`) và trong
`scripts\verify.ps1` — để mỗi health probe không phải trả giá I/O quét toàn DB;
có thể chạy lại chúng trong maintenance khi cần chẩn đoán sâu.

Probe nhẹ vẫn kiểm tra các bất biến nghiệp vụ read-only ở MỌI lần `/ready`,
không chỉ trong deep check:

- canonical BOOLEAN (chỉ INTEGER 0/1) trên các cột cờ;
- `price_configs.effective_date` đúng dạng `YYYY-MM-DD` hợp lệ;
- `parking_slots.is_occupied` khớp với phiên `active`;
- vòng đời `parking_sessions`: status phải thuộc `active`/`completed`/
  `cancelled` (một hàng `checking_out` còn đọng lại sau sự cố sẽ làm readiness
  fail-closed), datetime đúng dạng naive canonical, và phiên `completed` phải
  đủ `check_out_time`/`parking_fee`/`staff_out_id` với
  `check_out_time >= check_in_time`;
- quyền lợi vé tháng khớp xe/ngày check-in, và mọi phiên `active` đều có bảng
  giá dự phòng hiệu lực tại check-in;
- phiên `active` không dùng vị trí/khu vực đã tắt hoặc sai loại xe.

Không chạy endpoint `/ai/*` trong vòng UAT không-provider. Kiểm tra các luồng:

1. đăng nhập và phân quyền;
2. Zone/Slot và sức chứa;
3. bảng giá, khách hàng, xe, vé tháng;
4. check-in/check-out, phí và giải phóng chỗ;
5. lọc lịch sử theo biển số, ngày và phân trang;
6. báo cáo ngày/tuần/tháng/năm và export;
7. gọi lại `/ready`, sau đó có thể chạy độc lập
   `PRAGMA integrity_check`/`foreign_key_check` sau khi dừng app.

## 4. Rollout thật

1. Chọn maintenance window và dừng backend.
2. Tạo backup riêng, ghi hash và thử mở backup.
3. Chạy copy-first như mục 2 và hoàn tất UAT.
4. Chỉ khi checkpoint được duyệt, migration đúng file thật bằng đường dẫn tuyệt
   đối đã kiểm tra:

   ```powershell
   python backend\db_rollout.py --database C:\ParkingAI\data\parking.db
   ```

5. Khởi động đúng commit, không `--reload`; ban đầu giữ `AI_ENABLED=false`.
6. Yêu cầu `/ready` trả 200; sau đó smoke test read-only rồi một luồng
   check-in/check-out đánh dấu UAT.
7. Chỉ bật `AI_ENABLED=true` khi người phụ trách đã duyệt key, chi phí và dữ
   liệu được gửi sang provider.

## 5. Rollback

Nếu migration hoặc smoke test thất bại: dừng app, giữ file lỗi để điều tra,
xác nhận không còn process SQLite, di chuyển riêng file lỗi và mọi sidecar
`-wal`/`-shm`/`-journal`, rồi phục hồi nguyên file backup đã xác minh. Kiểm tra
lại SHA-256, `/ready`/integrity trước khi khởi động phiên bản cũ. Không chép
backup đè lên DB đang có WAL, không `git reset --hard`, không force-push
`main` và không kỳ vọng `git revert` tự xóa cột/index/trigger.
