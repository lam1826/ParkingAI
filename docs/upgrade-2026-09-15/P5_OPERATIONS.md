# Vận hành thanh toán payOS cho một bãi

Hiện người dùng chưa có tài khoản payOS. Bản đồ án chạy với `PAYOS_ENABLED=false`; thanh toán DEMO có nhãn và thu tại quầy vẫn sử dụng được. Hướng dẫn bật provider bên dưới dành cho đợt cấu hình và nghiệm thu riêng sau này; việc viết hướng dẫn không bật thanh toán hoặc đăng ký webhook.

## 1. Cấu hình có hiệu lực ở đâu

`OnlinePaymentConfig` đọc biến môi trường của **tiến trình**, không tự đọc `backend/.env`. API và worker phải dùng cùng `DATABASE_URL`, `PAYOS_SITE_ID`, kênh, tài khoản nhận và các khóa provider. Biến đặt ở một cửa sổ PowerShell không tự xuất hiện ở cửa sổ khác đang mở.

| Biến | Nội dung |
|---|---|
| `PAYOS_ENABLED` | Mặc định `false`; chỉ bật khi đã cấu hình đợt nghiệm thu riêng |
| `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY` | Giá trị do kênh payOS cung cấp; chỉ cấu hình phía server |
| `PAYOS_RECEIVER_ACCOUNT_NUMBER` | Số tài khoản nhận của chính kênh; chỉ chứa chữ số |
| `PAYOS_SITE_ID` | ID bãi hiện có trong DB, không phải ID tài khoản provider |
| `PAYOS_RETURN_URL`, `PAYOS_CANCEL_URL` | HTTPS trên tên miền frontend đã triển khai; có thể cùng trỏ `/portal` |
| `PAYOS_TIMEOUT_SECONDS` | Mặc định 10 giây, cho phép 1–30 |
| `PAYOS_MAX_PAYLOAD_BYTES` | Mặc định 65.536 byte, cho phép 1.024–1.048.576 |
| `SESSION_FEE_QUOTE_TTL_SECONDS` | Mặc định 300 giây, cho phép 60–900; độc lập với cuối khối phí `paid_through` |

Không đưa các biến khóa vào biến `VITE_*`, mã frontend, Git, ảnh chụp hoặc shared memory. `scripts/demo_server.py` luôn ép payOS tắt để DB tổng hợp không nhận tiền thật; không dùng launcher demo để bật provider.

## 2. Chuẩn bị DB và kiểm tra cục bộ

Thực hiện quy trình backup/migration trong [DEPLOYMENT.md](../DEPLOYMENT.md). Dừng các tiến trình ghi trong đợt chuyển DB; tạo candidate bằng `db_rollout --source ... --copy-to ...`, kiểm tra candidate rồi mới cấu hình runtime trỏ tới đó. Schema hiện hành gồm migration `20260915_06`, hai bảng đề nghị/ghi có và mapping online có nguồn đơn hoặc đề nghị lượt. Không chạy mã cũ không hiểu ghi có trên DB đã phát sinh tiền online.

Các lệnh sau chạy từ thư mục dự án. Đường dẫn DB và tên miền là chỗ cần thay bằng môi trường đã chuẩn bị; không phải DB/tên miền tự được tạo bởi hướng dẫn.

```powershell
Set-Location 'D:\Ứng_dụng_TTNT\ParkingAI'
$env:PYTHONPATH = Join-Path (Get-Location) 'backend'
$env:DATABASE_URL = 'sqlite:///C:/ParkingAI-UAT/parking-copy.db'
$env:AI_ENABLED = 'false'
$env:DEMO_PAYMENTS_ENABLED = 'false'
$env:PAYOS_ENABLED = 'false'
.venv\Scripts\python.exe -m expansion.online_payment_worker --once
```

Khi tắt, worker trả `disabled: true` và không gọi provider. Các tùy chọn CLI thực tế đã kiểm bằng `--help`: worker có `--once` hoặc `--run`, `--poll-seconds`, `--limit`; `db_rollout` có `--database` hoặc cặp `--source`/`--copy-to`.

## 3. Nhập cấu hình cho đợt nghiệm thu provider

Chỉ thực hiện phần này sau khi đã có kênh nhận tiền. Nhập giá trị qua lời nhắc ẩn hoặc cơ chế cấp secrets của môi trường triển khai; đoạn dưới không chứa giá trị khóa mẫu. Lặp lại bước cấu hình tương ứng trong môi trường của API và worker, hoặc để trình quản lý dịch vụ cấp cùng bộ biến cho cả hai.

```powershell
foreach ($parkingPaymentName in @('PAYOS_CLIENT_ID', 'PAYOS_API_KEY', 'PAYOS_CHECKSUM_KEY', 'PAYOS_RECEIVER_ACCOUNT_NUMBER')) {
    $parkingPaymentSecret = Read-Host $parkingPaymentName -AsSecureString
    [Environment]::SetEnvironmentVariable($parkingPaymentName, ([System.Net.NetworkCredential]::new('', $parkingPaymentSecret)).Password, 'Process')
    Remove-Variable parkingPaymentSecret
}
$env:PAYOS_SITE_ID = Read-Host 'ID bai trong DB'
$env:PAYOS_RETURN_URL = Read-Host 'HTTPS frontend URL, ket thuc /portal'
$env:PAYOS_CANCEL_URL = $env:PAYOS_RETURN_URL
$env:PAYOS_ENABLED = 'true'
```

Preflight dưới đây không gọi mạng, không tạo đơn, không gửi tiền; chỉ kiểm hình dạng cấu hình, schema/data readiness và đúng một bãi đang hoạt động. Nó không in khóa. Nếu thất bại, sửa cấu hình/DB trước khi khởi động provider; lỗi cấu hình không được `/ready` tự thay thế bằng kết luận ngân hàng sẵn sàng.

```powershell
@'
from expansion.online_payment_schemas import get_online_payment_config
from database import engine, SessionLocal
from db_rollout import check_database_readiness
from expansion.site_models import ParkingSite
from sqlalchemy import select
try:
    config = get_online_payment_config()
    if not config.PAYOS_ENABLED:
        raise ValueError("provider_disabled")
    check_database_readiness(engine, deep=True)
    with SessionLocal() as db:
        sites = list(db.scalars(select(ParkingSite)))
        if len(sites) != 1 or sites[0].id != config.PAYOS_SITE_ID or not sites[0].is_active:
            raise ValueError("single_lot_config_mismatch")
    print("LOCAL_CONFIG_AND_DATABASE_READY; BANK_NOT_VERIFIED")
except Exception as error:
    print("LOCAL_PREFLIGHT_FAILED:", type(error).__name__)
    raise SystemExit(1)
'@ | .venv\Scripts\python.exe -
```

## 4. API, worker và webhook là ba phần riêng

API backend thông thường, trong môi trường đã cấu hình ở trên:

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Worker ở tiến trình riêng, được cấp cùng biến môi trường và cùng DB:

```powershell
.venv\Scripts\python.exe -m expansion.online_payment_worker --run --poll-seconds 30 --limit 50
```

`main.py` có vòng maintenance portal/ảnh nhưng **không tự chạy worker payOS**. Worker riêng xử lý inbox đã nhận và dò lại liên kết khi webhook/response bị mất. Một lần `--once` chỉ chạy một chu kỳ, không thay worker chạy liên tục. Dùng một worker cho bản một bãi; kiểm tiến trình/log để biết nó còn hoạt động. Các bộ đếm `handled/retry/reconciled` là kết quả xử lý, không phải bằng chứng tiền đã nhận.

Frontend được build/phục vụ theo hướng dẫn triển khai chung; Uvicorn ở trên phục vụ API. Reverse proxy HTTPS phải đưa đường `/api/` đến API và các đường frontend như `/portal` đến ứng dụng React. Kiểm `GET /ready` trả 200 ở backend; đây là database readiness, không kiểm credentials với ngân hàng, kết nối provider hoặc trạng thái worker.

Địa chỉ webhook cấu hình trên kênh là `https://<ten-mien-api>/api/v2/payments/payos/webhook`. Localhost không phải địa chỉ callback công khai. App không tự đăng ký/confirm webhook khi khởi động. Đăng ký endpoint và kiểm yêu cầu của tài khoản trong đợt nghiệm thu riêng theo [nghiên cứu provider](PAYOS_INTEGRATION_RESEARCH.md). Return/cancel URL chỉ điều hướng về portal; tham số `status`, `code`, `cancel` hoặc thao tác quay về trang không chứng minh tiền đã nhận. Chưa có màn hình chuyên biệt `/payment-return`; dùng route đang có `/portal`.

## 5. Kiểm tra vận hành và xử lý tình huống

| Tình huống | Hành vi đã triển khai / thao tác |
|---|---|
| Provider chưa bật | Gói không chào payOS; API tạo link/quote trả 503; phí lượt vẫn xem được để thu tại quầy |
| Tạo link timeout | Mapping đã lưu; kiểm lại chính đề nghị đó. Không tạo mã mới hoặc gửi lại POST create để đoán kết quả |
| Khách đã chuyển nhưng màn hình chưa đổi | Giữ nguyên đơn/đề nghị, dùng kiểm tra giao dịch; kiểm worker. Chỉ receipt/credit được phân bổ sau đối soát mới là số đã trả |
| Tiền thiếu/dư, ref mới, sai tài khoản/tiền tệ hoặc đến muộn | Manager xem “Đối soát chuyển khoản”, lý do và bằng chứng; không tự cấp thêm vé hoặc hoàn tiền |
| Ghi chú/xác nhận hoàn bên ngoài | Lưu quyết định, người thực hiện, lý do, chứng từ; không gọi ngân hàng để hoàn. Chỉ xác nhận khi đã thực hiện và có bằng chứng phù hợp |
| Xe đã thu tại quầy trong khi provider đang chờ | Giữ lượt completed và receipt quầy; tiền online đến sau vào review, không ghi có/thu lần hai |
| Xe đã ra hoặc bãi đóng khi tạo QR | Mapping vẫn giữ; response không còn QR/URL trả tiền. Worker tiếp tục lưu/đối soát sự kiện đã xác minh; không giả provider đã hủy link |
| Khách/nhân viên mất quyền trong HTTP | Mapping được giữ; response không trả QR và từ chối truy cập theo quyền mới |
| Muốn dừng nhận online | Tắt `PAYOS_ENABLED` ở cả API và worker rồi khởi động lại; khi tắt webhook trả 503. Vì vậy cần đối soát các liên kết/tiền đang chờ trước khi dừng có kế hoạch; việc tắt cờ không tự hủy link ở provider |
| Đổi kênh/tài khoản hoặc restore DB | Không sửa mapping cũ. Đối chiếu bằng chứng/chứng từ đang chờ của kênh cũ trước chuyển cấu hình; dữ liệu provider không được khôi phục theo backup SQLite |

Người dùng hiện chưa có tài khoản, nên bước nghiệm thu provider thật còn mở. Bộ kiểm thử offline có chữ ký, SQLite race và các phép kiểm local chỉ xác minh hợp đồng/phân quyền/ghi sổ của ứng dụng. Không báo đã kết nối ngân hàng từ kết quả `223 passed` hoặc `/ready`.
