# Nâng cấp dữ liệu cho bản mở rộng đồ án

Phiên bản PostgreSQL `20260907_02` bổ sung 20 bảng cho bãi xe, đặt chỗ, hồ sơ khách hàng, đơn vé tháng và camera. SQLite dùng công cụ `db_rollout.py` hiện có. Các công cụ chỉ chạy khi được gọi rõ ràng; khởi động API không tự sửa dữ liệu.

## Quy tắc giữ dữ liệu

- Khu vực cũ được gán vào một **Bãi xe mặc định**. Khi tạo bãi này lần đầu, nhân viên và quản lý đã có được cấp quyền tương ứng. Quản trị viên vẫn có quyền toàn hệ thống. Những tài khoản được tạo sau đó cần được phân công rõ ràng.
- Nếu dữ liệu đã có nhiều bãi mà còn khu vực chưa được gán bãi, migration dừng để xử lý phân loại; không chọn ngẫu nhiên một bãi.
- Readiness SQLite (cả thường và sâu) cũng từ chối trạng thái nhiều bãi có khu chưa gán bãi và chỉ ra mã khu cần xử lý. PostgreSQL dùng cùng bất biến ở bước kiểm tra dữ liệu sâu; kiểm tra catalog đơn thuần không thay thế bước này. Kiểm tra không tự sửa dữ liệu nguồn.
- API tạo khu cũ giữ tương thích khi chưa có bãi; nếu đúng một bãi thì tự gắn vào bãi đó. Từ hai bãi trở lên, tính cả bãi đã đóng còn lịch sử, API trả HTTP 409: tạo khu qua cấu hình bãi cụ thể. Quy tắc này ngăn phát sinh khu mồ côi mới từ giao diện cũ.
- Không tự liên kết tài khoản với khách hàng, không tự xác nhận quyền sở hữu xe và không cấp quyền xem lịch sử cũ. Các quan hệ này cần được xác minh qua cổng khách hàng.
- Phiếu thu, hoàn tiền, phương thức thu và mã tham chiếu cũ được giữ nguyên. SQLite chỉ thay CHECK đã biết của bảng `payments` trên bản sao, giữ thêm các cột, index và trigger riêng đã có.
- Phương thức `demo` chỉ áp dụng cho vé tháng, không gắn ca thu tiền. Hoàn tiền demo không được tham chiếu phiếu thu thực và ngược lại. Kiểm tra này tồn tại cả ở dịch vụ, trigger và kiểm tra readiness.

## SQLite dùng cho đồ án

Chạy lệnh từ thư mục dự án `ParkingAI`, sau khi dừng các tiến trình dùng database nguồn. Đường dẫn bên dưới là ví dụ; thay bằng tên bản dữ liệu cần nâng cấp. Đích sao chép phải là một file chưa tồn tại.

```powershell
.venv/Scripts/python.exe backend/db_rollout.py --source backend/parkingai.db --copy-to backend/artifacts/parkingai-expanded.db
```

Công cụ sao chép bằng SQLite Backup API, nâng cấp trên file tạm, kiểm tra cấu trúc, dữ liệu, foreign key và integrity trước khi công bố file đích. File nguồn được kiểm tra hash, kích thước và thời gian sửa đổi để xác nhận không thay đổi. Database còn WAL hoặc journal đang hoạt động bị từ chối; đóng writer và checkpoint theo hướng dẫn lỗi trước khi thử lại.

Để kiểm tra việc tạo một database rỗng:

```powershell
.venv/Scripts/python.exe backend/db_rollout.py --database backend/artifacts/parkingai-demo.db
```

Lệnh này chỉ khởi tạo cấu trúc và bãi mặc định; không tạo tài khoản mẫu hoặc marker cho máy chủ demo. Khi chạy lại trên file đã có, công cụ vẫn nâng cấp trên bản sao tạm và kiểm tra trước khi thay thế file đích. Để có bộ dữ liệu trình diễn đầy đủ, dùng `scripts/start_demo.ps1` theo [hướng dẫn demo](DEMO_GUIDE.md) với một đường dẫn DB mới. Seeder từ chối ghi đè DB đã tồn tại.

## PostgreSQL

Trong môi trường kiểm thử đã cấu hình `DATABASE_URL` cho PostgreSQL, chạy từ thư mục `backend`:

```text
python -m alembic -c alembic.ini upgrade head
python production_release_gate.py
```

Revision giữ bản SQL cố định của bảng, index và trigger, không nhập model đang thay đổi để chạy migration cũ. Cổng phát hành kiểm tra revision `20260907_02`, các cột bắt buộc, ràng buộc và dữ liệu nghiệp vụ.

Kiểm thử PostgreSQL thực nằm trong `tests/test_postgres_integration.py`, được kích hoạt bởi `POSTGRES_TEST_URL` trong dịch vụ CI riêng. Biên dịch migration ở chế độ offline chỉ kiểm tra việc sinh SQL; không thay thế kiểm thử chạy PostgreSQL.

Sau review, `tests/test_review_zone_regressions.py` bổ sung các trường hợp 0/1/nhiều bãi, bãi đóng, readiness và nâng cấp bản sao sau khi tạo khu qua API. Truy vấn bất biến dùng chung đã được kiểm tra trên SQLite; đây chưa phải bằng chứng khóa hoặc transaction hoạt động đúng trên PostgreSQL thực.

## Khôi phục

Với SQLite, giữ database nguồn trước nâng cấp và chạy thử bằng file mới. Nếu cần quay lại trước khi nhận dữ liệu mới, dừng ứng dụng rồi trỏ cấu hình về file nguồn. Sau khi đã phát sinh giao dịch, không thay bằng bản cũ vì sẽ mất các giao dịch mới; cần sửa ứng dụng hoặc khôi phục theo quy trình backup có đối soát.

PostgreSQL không hỗ trợ tự động `downgrade` revision này vì thao tác đó có thể xóa hồ sơ và lịch sử mới. Khôi phục phiên bản ứng dụng phải giữ schema đã nâng cấp và dùng phiên bản có hiểu phương thức `demo`; phiên bản cũ chưa biết `demo` có thể tính nhầm báo cáo tiền. Đối với đồ án, sử dụng dữ liệu demo riêng trước khi cân nhắc phát hành lên môi trường đang vận hành.
