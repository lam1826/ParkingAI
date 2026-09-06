# Biên bản kiểm chứng đợt nâng cấp 06/09/2026

## Môi trường và phạm vi

- Windows, workspace `ParkingAI`; baseline trước thay đổi:
  `4ff715041fc6d93bd3cfc6bbf18608d6b267aca8`.
- Test backend dùng SQLite riêng; UAT dùng server nội bộ, CSDL và tài khoản
  giả. Provider AI bị chặn. Không thao tác trên dữ liệu production.
- Script `scripts/verify.ps1` kiểm tra dữ liệu SQLite thật trước/sau chạy,
  đối chiếu snapshot hồ sơ, chạy pytest, frontend tests, lint và build.
- Báo cáo chức năng và hướng dẫn nâng cấp: [RELEASE_2026-09-06.md](RELEASE_2026-09-06.md).

## Kết quả kiểm thử tự động

| Hạng mục | Kết quả cuối |
| --- | --- |
| Backend toàn bộ, kiểm chứng cuối trên Windows | **868 passed, 3 skipped**, 323,76 giây |
| Frontend toàn bộ | **107 passed, 0 failed** |
| Backend trên Linux CI, commit `6d9b499` | **867 passed, 5 skipped**, 229,73 giây |
| PostgreSQL 16 trên CI | **3 passed**, 2,41 giây; migration thành công |
| Kiểm tra phát hành trên Windows CI | **147 passed, 1 skipped**, 358,34 giây |
| ESLint | Đạt |
| Vite production build | Đạt |
| Snapshot hồ sơ | 348 file đồng bộ, không có artifact runtime |
| Git diff whitespace | Đạt theo cấu hình line ending của repository |
| Dữ liệu SQLite thật | Kiểm tra trạng thái trước/sau không phát hiện thay đổi |

Ba test bỏ qua: hai test PostgreSQL do thiếu `POSTGRES_TEST_URL`, một test
quyền sở hữu POSIX không áp dụng trên Windows. Backend có một cảnh báo
deprecation của datetime adapter trong test SQLite.

Log `release-verified-final.log` ghi lần chạy sạch backend, frontend, lint
và build sau các bản sửa cuối. Bản build kiểm chứng có entry
`index-DmtqvABe.js`. Không thay đổi mã ứng dụng sau mốc này.

Test PostgreSQL có dữ liệu cũ được bổ sung riêng trong bước chuẩn bị phát
hành. Chạy file PostgreSQL trên máy này cho **3 skipped** đúng cấu hình;
CI đã thực thi cả ba thành công trên PostgreSQL 16. Case backfill tạo database UUID
riêng trong dịch vụ thử loopback, nâng bản cũ có dữ liệu lên revision mới,
kiểm tra ID/thẻ, phiếu thu, đổi múi giờ, giữ snapshot cũ NULL và chạy lại
không nhân đôi. Database thử được dọn theo đúng tên do test tạo.

[CI của commit backend `6d9b499`](https://github.com/lam1826/ParkingAI/actions/runs/34017441000)
đã thành công. Ba test PostgreSQL được bỏ qua ở bước pytest thông thường
rồi chạy ở bước riêng có `POSTGRES_TEST_URL`; các test còn lại bỏ qua theo
hệ điều hành. Giao diện trong commit backend vẫn là bản cũ với 88 test;
107 test ở trên thuộc giao diện mới đã kiểm chứng tại workspace và UAT.

## UAT qua trình duyệt

Chrome headless chạy ứng dụng build thật ở độ rộng 1440px và 390px.
Kịch bản hoàn tất trên bản mã cuối cùng:

| Bước | Kết quả quan sát |
| --- | --- |
| Mở ca với tiền đầu ca 100.000đ | Ca mở thành công |
| Cấp vé tháng thu tiền mặt 500.000đ | Có kỳ vé và phiếu thu |
| Gia hạn thu chuyển khoản 600.000đ | Hai kỳ cùng mã thẻ, kỳ cũ giữ nguyên; kỳ tương lai hiển thị chưa đến hạn |
| Xe vào và xem vé QR | Đúng biển số, vị trí, thời điểm vào; tạo được bản in PDF |
| Đóng hộp vé rồi quét lại ngay | Chỉ hiện thao tác khi đúng lượt gửi được tải xong |
| Xác nhận xe ra | Hiển thị biên nhận; phí 0đ do vé tháng; phiếu thu không bị lặp |
| Hoàn 50.000đ từ phiếu thu gốc | Giao dịch hoàn có lý do; phiếu thu gốc giữ nguyên |
| Chốt ca với tiền mặt 550.000đ | Tiền phải có 550.000đ, thực đếm 550.000đ, chênh lệch 0đ |
| Báo cáo doanh thu | Vé tháng 1.100.000đ − hoàn 50.000đ = doanh thu thuần 1.050.000đ |
| Nhập câu hỏi AI quá dài | Nút gửi bị chặn, trang vẫn hoạt động |
| AI đang tắt | Hiển thị lỗi bằng văn bản, lịch sử vẫn mở được |
| Lịch sử AI và đổi tài khoản | Chỉ thấy báo cáo của tài khoản hiện tại; chat tài khoản trước không xuất hiện |
| Đổi tài khoản/đăng xuất ở tab khác | Tab còn lại tự đổi danh tính hoặc về đăng nhập; chat cũ biến mất |
| Vé QR đã hủy | Hộp thoại và bản in hiển thị đã hủy, không có thao tác cho xe ra |
| Giao diện nhỏ | Trang ca, vé tháng và xe vào/ra không tràn ngang toàn trang |

Kịch bản không ghi nhận JavaScript runtime exception. Sổ ca có 4 giao dịch:
2 phiếu thu vé tháng, 1 phiếu thu lượt gửi 0đ, 1 phiếu hoàn.

Minh chứng gốc nằm trong thư mục `ParkingAI-UAT-Evidence` cạnh repository:

- `implementation-browser.py`: script UAT và tạo dữ liệu thử.
- `implementation-browser-results.json`: kết quả và danh sách ảnh chụp.
- `implementation-browser-63d6d8e7/`: ảnh desktop/mobile, dữ liệu thử và
  `ticket-print.pdf` của vòng UAT hoàn tất cuối.
- `preprod-account-boundary-c38dcfe7/`: UAT hai tab, vé đã hủy và bản in.
- `release-verified-final.log`: kết quả backend, frontend, lint, build và
  kiểm tra dữ liệu SQLite thật.
- `release-browser-final.log`: kết quả UAT toàn bộ trên bản build cuối.

## Lỗi phát hiện và sửa ngay trong quá trình kiểm chứng

- API vé QR ban đầu dùng sai tên thuộc tính vị trí; test API đã tái hiện và
  bản sửa dùng `slot_name`.
- Chữ ký QR có ký tự Unicode gây lỗi 500; hiện trả lỗi 400.
- Chuyển nhanh giữa hộp vé có thể gọi xác nhận với ID rỗng; bản sửa chỉ
  cho thao tác trên dữ liệu vé khớp ID hiện tại, đã chạy lại UAT thành công.
- Ràng buộc CSDL bổ sung chặn tạo trực tiếp ca đã chốt với số dư giả.
- Thứ tự khóa khi hoàn tiền trên PostgreSQL được thống nhất; doanh thu
  đọc sổ thu và dữ liệu cũ trong một truy vấn để tránh thiếu số liệu giữa
  các lần đọc khi có giao dịch đồng thời.
- Hai test dựng CSDL giả được cập nhật: đóng kết nối SQLite trước thay file
  trên Windows; gỡ trigger tham chiếu trước khi cố ý dựng bảng sai cấu trúc.
  Đây là sửa dữ liệu/thiết lập test, không nới ràng buộc của ứng dụng.
- Xe đỗ qua hai kỳ liên tiếp đã mua trước lúc vào từng bị thu thừa. Bản sửa
  chốt ngày bao phủ tại lúc vào; test xác nhận không cấp quyền hồi tố từ
  kỳ mua sau, không nối kỳ bị đứt/ngừng hoặc khác thẻ.
- Đồng bộ phiên giữa các tab bổ sung chặn phản hồi muộn, xóa chat và dựng
  lại trạng thái trang khi đổi tài khoản. Vé đã hủy có trạng thái riêng.
- Ràng buộc lý do hoàn tiền trên PostgreSQL được sửa cho khớp model;
  trigger quyền lợi vé tháng chỉ cài khi schema cũ có đủ bảng tham chiếu.

## Phát hành theo thứ tự backend rồi frontend

- Backend `6d9b4997b3ac1733c528a04f459540b7bae87706` đã qua CI nêu trên
  và [Continuous Delivery](https://github.com/lam1826/ParkingAI/actions/runs/34017746839).
- Kiểm tra độc lập tại `https://api.parkingai.am` xác nhận đúng SHA,
  `/ready` trả `ready`, CORS cho phép `https://parkingai.am`; API thu tiền,
  ca và QR trả 401 khi chưa đăng nhập. Bằng chứng: `release-live-backend.json`.
- Lúc nâng backend, frontend vẫn giữ bundle `index-CYyc7Vl8.js`, tránh
  giao diện mới gọi API chưa triển khai. Các thay đổi frontend và tài liệu
  được phát hành trong commit tiếp theo sau mốc backend đã sẵn sàng.
- Cloudflare Pages và CI/CD ghi trạng thái theo đúng SHA của từng commit.
  Kết quả public smoke sau phát hành được lưu ngoài repo trong
  `ParkingAI-UAT-Evidence`, không đưa profile trình duyệt hay dữ liệu thử
  vào source snapshot.

## Giới hạn kiểm chứng

- PostgreSQL đã chạy thành công trên dịch vụ thử riêng của CI, gồm cả
  backfill dữ liệu lịch sử. Máy Windows local không có PostgreSQL thử.
- Chưa gọi provider AI thật; không kết luận về chất lượng, chi phí hoặc độ
  trễ suy luận thực tế.
- Chưa kiểm thử máy in nhiệt và máy quét vật lý. Đã kiểm tra bản in trình
  duyệt, nội dung QR, chữ ký và luồng nhập mã như máy quét bàn phím.
- Dữ liệu thu vé tháng lịch sử không có thời điểm thu chính xác; migration
  ghi rõ việc ước tính từ thời gian tạo bản ghi và để hình thức thu là không rõ.
