# Trạng thái bản mở rộng ParkingAI cho đồ án

Cập nhật ngày 07/09/2026. Phạm vi đã triển khai là bản demo chạy trên SQLite riêng: QR ngẫu nhiên và kết quả thanh toán mô phỏng, điện thoại chụp ảnh, YOLO tìm vùng biển số và OCR đọc ký tự. Mã nguồn hiện nằm trong thư mục làm việc; bản mở rộng này chưa được đẩy lên Git hoặc triển khai thay website đang vận hành.

## Chức năng đã triển khai và kiểm chứng

| Phần | Kết quả |
| --- | --- |
| Cổng khách hàng | Liên kết hồ sơ qua xác minh; quản lý xe đã duyệt; xem vé, lịch sử được cấp quyền, vị trí hiện tại, chứng từ PDF và thông báo |
| QR và đơn vé tháng | Server chốt giá/kỳ vé; QR mang mã ngẫu nhiên và nhãn DEMO; mô phỏng thành công, thất bại, hủy, hết hạn; xử lý lặp không cấp thêm vé |
| Hoàn tiền | Khách gửi yêu cầu, quản lý duyệt/từ chối; hoàn DEMO được phân biệt với tiền thật, không cộng vào doanh thu thực hoặc chốt ca |
| Nhiều bãi cùng đơn vị | Bãi, khu, vị trí, thành viên và quyền theo bãi; API cũ toàn hệ thống bị giới hạn với nhân sự không đủ quyền, kể cả lịch sử bãi đã đóng |
| Đặt chỗ và đội xe | Đặt/hủy, xác nhận đến, no-show, bảo đảm chỗ, danh sách chờ và cấp vị trí; danh sách đặt chỗ/phân bổ/chờ lọc theo bãi, trạng thái, khoảng giờ và phân trang tại server với thứ tự ổn định; nhóm xe với báo cáo trả tập trường tường minh, tổng lượt/tổng phí tính trên toàn phạm vi được cấp quyền |
| Xe vào/ra | Nhận xe theo bãi/đặt chỗ, xem phí bằng báo giá có chữ ký, xác nhận đã thu rồi checkout; bảo vệ xe/vị trí trước yêu cầu đồng thời |
| Camera điện thoại | Chụp/upload, chuẩn hóa ảnh, chạy YOLO ONNX + RapidOCR trên CPU; ảnh riêng theo bãi, hết hạn lưu; nhân viên đối chiếu/sửa rồi mới chuyển sang nghiệp vụ |
| Dự báo và nhân sự | Dự báo thống kê, khoảng ước lượng, backtest theo thời gian, cảnh báo và phương án nhân sự với giả định rõ ràng; báo thiếu dữ liệu; khối độ phủ dữ liệu (giờ có bản ghi, giờ điền 0, tuần tham chiếu có xe, cảnh báo lịch sử thưa) và mức đầy đủ quan sát ghi "chưa xác định" vì không có nhật ký nguồn ghi nhận |
| Giao diện tải từng phần | Trang bãi, cổng khách và đặt chỗ tải mỗi bảng bằng một remote riêng: lỗi một API không làm mất phần khác, có Thử lại riêng, đổi trang một bảng không tải lại dữ liệu khác, thao tác ghi chỉ làm mới các phần phụ thuộc; giữ bảo vệ kết quả trả muộn khi đổi bãi/bộ lọc/tài khoản |
| Dữ liệu và triển khai demo | Seeder chỉ tạo DB mới, marker riêng, hai bãi/32 vị trí/56 ngày dữ liệu tổng hợp; máy chủ phục vụ giao diện và API cùng địa chỉ, bảo trì mỗi 30 giây |
| Migration SQLite | Nâng cấp trên bản sao có kiểm tra dữ liệu và bảo toàn nguồn; readiness từ chối khu chưa gán bãi trong DB nhiều bãi |

PostgreSQL đã có revision `20260907_02` và kiểm tra sinh SQL offline. **Chưa kiểm chứng PostgreSQL thực**; không xếp phần này vào các chức năng đã nghiệm thu chạy thực tế.

Không quy đổi bảng này thành “100% sản phẩm thực tế”: đây là mức hoàn thành phạm vi đồ án đã thống nhất, có các giới hạn bên dưới.

## Bằng chứng kiểm tra cuối

Lượt nghiệm thu độc lập ngày 07/09/2026, sau tám nhóm sửa bổ sung:

| Kiểm tra | Kết quả mới | Minh chứng |
| --- | --- | --- |
| Pytest toàn bộ | **1.141 đạt / 7 bỏ qua / 0 lỗi**, 1.148 ca, 551,34 giây | `backend/artifacts/acceptance-current/backend-final.xml` |
| Frontend | **130 đạt / 0 lỗi / 0 bỏ qua**, lint/build exit 0 | `backend/artifacts/acceptance-current/frontend-*.log` |
| React/component thật | **11/11**: 5 portal/hook + 6 workspace | `backend/artifacts/review-remote/9b27169a41/result.json`, `backend/artifacts/workspace-sections/cd87016113/result.json` |
| UAT đầy đủ | **9/9 nhóm**, 12 ảnh; 0 lỗi JavaScript/console/cảnh báo; desktop và mobile 390×844 không tràn ngang | `backend/artifacts/uat/771c6a2fe6/summary.json` |
| Word và snapshot | 103/15 trang, 26/5 ảnh giữ nguyên; 444 file source đồng bộ và kiểm tra byte | `../ParkingAI-Report-Work/acceptance-document-verification.json`, `backend/artifacts/acceptance-current/verification.json` |

Bảy skip đúng sáu PostgreSQL thiếu môi trường thật và một POSIX trên Windows. Có 193 cảnh báo datetime adapter sqlite3/Python 3.12. Không lấy SQL offline thay PostgreSQL. Không cộng các lượt test chọn lọc vào tổng; hai runner React và UAT là các kiểm tra riêng.

UAT xác nhận QR → cấp vé → vé/chứng từ tự cập nhật → tải PDF → yêu cầu/duyệt hoàn; đặt/hủy/chờ → cấp chỗ → đến → báo phí ký/xác nhận thu/ra → nhận xe vãng lai; ảnh qua YOLO/OCR và người duyệt; độ phủ dự báo/giả định nhân sự; đổi bãi nhanh; logout/login khách khác cùng document khi XHR chủ cũ về sau; viewport mobile. Chỉ dùng DB mới. Không khẳng định đã nạp mã này lên server demo đang chạy hoặc website.

Review lại ngày 08/09/2026 trên bản đã commit `026e692`: chạy lại toàn bộ pytest (1.141 đạt / 7 bỏ qua / 0 lỗi, 603,8 giây, lượt bắt đầu trước khi thêm ca mới bên dưới), frontend 130 đạt và lint/build exit 0, runner hook trình duyệt 5/5, snapshot 444 file khớp nguồn. Lỗi mới có tái hiện và đã sửa: `scripts/start_demo.ps1` thiếu BOM UTF-8 nên Windows PowerShell 5.1 báo `The string is missing the terminator` và không khởi động được (`backend/artifacts/demo/production-deploy.err.log`, 08/09 07:36); đã thêm BOM (parser 5.1 trả 0 lỗi) và ca `tests/test_demo_server.py::test_powershell_scripts_with_vietnamese_text_carry_a_utf8_bom` (file này 3/3 đạt khi chạy riêng). Script đã được chạy thật dưới Windows PowerShell 5.1 với DB/cổng riêng: seed DB mới, `/ready` trả `ready` sau 3 giây, giao diện HTTP 200. Đoạn bằng chứng trong hai file Word đã cập nhật theo kết quả này (backup `../ParkingAI-Report-Work/backup-before-rereview-20260908`, manifest `rereview-authoring-manifest.json`; số trang khi render bằng LibreOffice không đổi so với bản trước khi sửa). Bản sửa này chưa commit.

Các kết quả 1.058, 1.086, 1.114 backend và 129 frontend trước đây là mốc lịch sử. Lượt này thêm 27 ca backend và một ca frontend; sửa quyền bảo đảm chỗ theo chủ, biên bộ lọc, phản hồi ảnh bãi đóng, các lỗi ghép API và crash khi danh sách đơn lỗi. [Review nghiệm thu](ACCEPTANCE_REVIEW_2026-09-07.md) ghi bảng lỗi, RED/GREEN, tình huống tranh chấp không xác nhận lỗi mới và bốn nâng cấp A–D. [Review Claude](CLAUDE_REVIEW_RESPONSE.md) giữ các bản sửa trước để truy vết.

## Giới hạn và phần phát triển tiếp

- QR là dữ liệu `PARKINGAI-DEMO`, không chuyển tiền qua ngân hàng. Tích hợp thật cần nhà cung cấp, webhook đã xác minh và đối soát.
- Đã chạy model trên ảnh xe thật có nguồn, nhưng OCR đọc sai và có ảnh trả `no_plate`. Chưa có bộ đánh giá biển Việt Nam; không công bố độ chính xác. Bản demo giữ bước người kiểm tra, chưa tự mở barie.
- Model có nhãn giấy phép trên model card khác metadata bên trong. Giữ nguồn/SHA-256 và ghi rõ khác biệt; cần làm rõ quyền trước khi phân phối thương mại.
- Điện thoại dùng chụp ảnh/upload theo khả năng trình duyệt, chưa phải luồng video IP camera liên tục. UAT dùng viewport mobile và đường upload ảnh thật; chưa kiểm chứng trên mọi thiết bị điện thoại vật lý.
- Nhiều bãi thuộc cùng một đơn vị vận hành, chưa phải SaaS tách biệt các doanh nghiệp. Đội xe chưa có hóa đơn công nợ doanh nghiệp.
- Đặt chỗ giữ cửa sổ `[start_at,end_at)` ngay cả khi xe ra sớm; mỗi mã chỉ ghi một lần đến. Chỗ trống vật lý có thể vẫn được giữ, xe vãng lai phải chọn vị trí còn nhận xe. Trả lại giờ dư hoặc tái vào là chính sách phát triển sau.
- Dữ liệu dự báo trong demo là 56 ngày tổng hợp, không chứng minh chất lượng trên bãi thật. LLM bên ngoài mặc định tắt trong bộ chạy demo; chức năng Gemini của sản phẩm hiện có được kiểm thử tách biệt.
- Muốn phát hành lên PostgreSQL/website thật cần chạy sáu bài integration còn thiếu, diễn tập nâng cấp/khôi phục trên dữ liệu mục tiêu và kiểm tra cấu hình triển khai đó.
- Lịch bảo trì tự động hiện nằm trong demo server; triển khai ngoài bộ demo cần cấu hình worker và giám sát riêng. Retry sự kiện thanh toán chưa có trần số lần.
- Backlog sau đợt 2 (chính sách hoặc cần quyết định sản phẩm, không phải lỗi giao dịch): đơn thu tại bãi cũng hết hạn sau 15 phút như đơn DEMO; đơn xét duyệt vì kết quả DEMO đến muộn chỉ quản lý mới gỡ được; bảo đảm chỗ bọc ngoài một đặt chỗ cùng xe tạo trước bị từ chối trong khi thứ tự ngược lại được phép; xe đã đến rồi ra sớm không vào lại chính vị trí bằng cùng mã. Phân trang portal sessions/orders/passes/receipts/notifications và site sessions đã có từ trước và được giữ nguyên.

## Cách sử dụng và tài liệu

Chạy `./scripts/start_demo.ps1` tại thư mục dự án, hoặc thêm `-Lan` để mở từ điện thoại cùng Wi-Fi. Mật khẩu mặc định của bốn tài khoản `_demo` là `DemoParkingAI!2026`. DB đã tồn tại giữ mật khẩu lúc tạo.

- [Hướng dẫn demo](DEMO_GUIDE.md)
- [Cổng khách và thanh toán](PORTAL_PAYMENTS.md)
- [Bãi, đặt chỗ và đội xe](SITES_RESERVATIONS.md)
- [Camera và dự báo](VISION_FORECAST.md)
- [Migration và khôi phục](EXPANSION_MIGRATION.md)
- [Minh chứng AI trong SDLC](EXPANSION_SDLC.md)
- [Lộ trình phát triển tiếp](DEVELOPMENT_ROADMAP.md)

Hai file Word tại thư mục cha của dự án đã cập nhật theo văn phong và bố cục gốc: `báo cáo hệ thống parkingAI.docx` (103 trang) và `Hướng dẫn sử dụng và triển khai ParkingAI.docx` (15 trang). Đã làm mới mục lục, render và kiểm tra trình bày, đối chiếu ảnh/font/màu đề mục/khổ/lề với bản trước chỉnh sửa. Backup và manifest kiểm tra nằm tại `../ParkingAI-Report-Work`.

Bản mã nguồn nộp sau nghiệm thu có 444 file đồng bộ và kiểm tra khớp nguồn. Word giữ 103/15 trang; manifest mới tại `../ParkingAI-Report-Work/acceptance-document-verification.json`. [Kết luận bàn giao](EXPANSION_RELEASE_GATE.md): READY cho demo SQLite cục bộ. Các log, DB, ảnh UAT và model tải về là artifact cục bộ, được loại khỏi bản source; script tải model/ảnh và hướng dẫn tái lập được giữ lại.
