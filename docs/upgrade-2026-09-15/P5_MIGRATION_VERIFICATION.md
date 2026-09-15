# Migration và khôi phục sổ thu online

Kiểm tra ngày 15/09/2026 trên SQLite. Phiên bản PostgreSQL đích là `20260915_06`; chưa có PostgreSQL đang chạy để nghiệm thu. Toàn bộ dữ liệu trong các artifact dưới đây là dữ liệu đồ án hoặc fixture kiểm thử, không có giao dịch ngân hàng thật.

## Thay đổi của phiên bản 06

- Thêm `session_fee_quotes` và `session_fee_credits`; cơ sở dữ liệu đầy đủ có 48 bảng nghiệp vụ.
- `online_payment_links` nhận đúng một nguồn: đơn mua vé hoặc đề nghị trả phí lượt. Mapping cũ giữ nguyên mã provider, đơn, trạng thái, thời gian và bằng chứng đối soát; cột mới để NULL cho mapping cũ.
- Phiếu thu `session_credit` ghi khoản chuyển khoản đã xác minh. Lượt ra lưu tổng phí F; phiếu tất toán chỉ thu D = F − C. Khi C > 0 và D = 0 vẫn giữ phiếu tất toán 0đ để không cộng doanh thu lần nữa.
- Guard ngăn hủy lượt có tiền online hoặc bằng chứng đã nhận chưa xử lý. Guard PostgreSQL 06 đã đồng bộ điều kiện inbox chưa xử lý với guard hiện hành trước khi đóng băng mã.
- Reservation đã đến chỉ giữ sức chứa trong lúc lượt liên kết còn `active` hoặc `checking_out`. Rời bãi sớm không giữ thêm ô đến hết hạn vé một lần.
- Không tính lại lịch sử hoặc tạo khoản ghi có cho lượt cũ. Không hỗ trợ downgrade xóa sổ thu; dùng bản ứng dụng tương thích hoặc migration sửa tiếp.

## Kết quả đã thực hiện

| Kiểm tra | Kết quả |
|---|---|
| P1 → schema06 | 37 bảng gốc giữ nguyên mọi giá trị cột cũ; đích 48 bảng |
| Schema05 → schema06 | 46 bảng gốc giữ nguyên mọi giá trị cột cũ; đích 48 bảng |
| Chạy khởi tạo lại hai candidate | Không thay đổi dữ liệu; readiness, integrity và khóa ngoại đạt |
| Nguồn migration | SHA-256 nguồn trước/sau không đổi; chỉ sửa candidate riêng |
| Mapping provider cũ có dữ liệu | Giữ nguyên bản ghi, cột mở rộng và index tùy chỉnh; chạy lặp không đổi |
| CHECK nguồn không nhận diện | Từ chối trước thay đổi schema |
| Kiểm thử migration/contract PostgreSQL | 21 passed, 0 failed, 0,29 giây |
| Alembic từ base tới head06 | Render SQL offline thành công; không kết nối PostgreSQL |
| Khôi phục ledger có ghi có, vé giờ và vé ngày | Hai ca đạt; mỗi ca giữ nguyên 48 bảng, 2 khoản ghi có tổng 10.000đ và 3 phiếu thu 5.000đ + 5.000đ + 0đ |

Kiểm thử ledger tái sử dụng hai ca API độc lập trong `tests/test_session_payment_acceptance.py`: tạo đề nghị, tạo link qua HTTP transport giả có chữ ký, nhận webhook, chạy worker, trả thêm khi vượt block, xác nhận xe ra và thử lại. Hook sau mỗi ca dùng SQLite online backup, migration sang file mới, khởi tạo lại rồi so sánh toàn bộ bảng trước khi kiểm readiness sâu. Lệnh này thực tế có **2 passed trong 5,53 giây**; không cộng vào 21 ca trên để diễn đạt một lệnh kiểm thử duy nhất.

## Artifact cục bộ

Thư mục `backend/artifacts/demo/` bị Git bỏ qua, không đưa DB hoặc credentials vào commit.

- `p5-schema06-rehearsal-ca19d01c92304670b42f5b8a4ffcce20.json`: đường dẫn nguồn/candidate, SHA nguồn, số bảng và số dòng của cả hai tuyến nâng cấp. Nguồn schema05 được lấy bằng `sqlite3.Connection.backup` từ kết nối chỉ đọc; không sao chép thô file DB đang dùng.
- Nguồn P1 đóng băng: `p1-frozen-for-p4-a1df2cd47e144678ac9dd860ffecbee8.db`, SHA-256 `13103b579490490625f29260d5eb063320b4ec4857f8a269886a0ce8fcf46c96`.
- `p5-credit-ledger-recovery-8898a9f48f54432ab4e1b6f46f9d0675.json`: hai bản backup và phục hồi chứa ledger mới, so sánh dữ liệu và bất biến tổng thu.
- `p5-postgres06-offline.sql` và `.sql.json`: SQL 166.992 byte, SHA-256 `3a84e18aa971117591ecdee669b6b458dbde267a79e5fed5a5dc109352d14db1`. Đây là bằng chứng render và contract, không chứng minh SQL chạy trên PostgreSQL thật.
- `p8-final-http-6244f9ca7b0842a6b66053e1c895b477.db`: bộ dữ liệu mới cho UAT schema06, readiness đã đạt trước chạy server. Ban đầu có 1 bãi, 3 khu, 40 ô/36 ô hoạt động, 34 ô trống, 476 lượt lịch sử giả và 2 lượt active. Marker `.demo.json` ghi metadata; mật khẩu ngẫu nhiên chỉ nằm trong `.demo-credentials.json` riêng.

## Thực hiện lại khi triển khai

Chạy `python -m pytest tests/test_session_credit_migration.py tests/test_postgres_contract.py -q` trong virtualenv từ gốc project để kiểm các contract. SQLite dùng `backend/db_rollout.py --source <nguồn-đã-đóng> --copy-to <file-mới>` rồi chạy readiness, tuyệt đối không trỏ nguồn và đích cùng file. Nếu nguồn còn được dùng, tạo snapshot bằng SQLite backup API trước; giữ nguyên nguồn và sidecar.

Chỉ chuyển backend sang candidate sau khi giữ được bản backup, kiểm readiness sâu, so sánh dữ liệu và nghiệm thu HTTP. Kết quả full P8, trình duyệt, camera vật lý và ngân hàng được ghi riêng; tài liệu này không thay thế các nghiệm thu đó.
