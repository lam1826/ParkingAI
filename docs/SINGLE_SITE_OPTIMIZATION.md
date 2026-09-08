# Tối ưu ParkingAI một bãi từ các hệ thống AI tham khảo

Ngày 08/09/2026. Baseline `8182c3f`; bản đã phát hành `3afc56cad9cd6a4d43f56eb96766c7006141dd0f`. Kết quả phát hành online được ghi riêng ở cuối tài liệu; số đo cục bộ không thay cho nghiệm thu production.

## 1. Phạm vi và căn cứ lựa chọn

Đã đối chiếu Metropolis, SKIDATA, Flash và bốn dự án FastALPR, FastPlateOCR, Frigate, Ultralytics bằng nguồn chính chủ. [Báo cáo nghiên cứu](RESEARCH_SINGLE_SITE_AI_PARKING.md) ghi URL, revision, giấy phép và quyết định KEEP/ADAPT/FUTURE. Không sao chép mã bên ngoài, cài thêm stack hoặc dùng số quảng bá của nhà cung cấp làm benchmark.

Giữ đồ án **một bãi**, FastAPI/React, QR mô phỏng, Gemini tắt và cấu hình Fly 1 GB. Ba thay đổi được chọn vì đã tái hiện vấn đề trên mã/dữ liệu thử của ParkingAI. Không mở rộng quản lý nhiều bãi hoặc tự thu tiền theo kết quả OCR.

## 2. Ba thay đổi đã kiểm chứng cục bộ

| Phần | Trước | Sau | Bằng chứng và giới hạn |
|---|---|---|---|
| Tra chỗ trống | Service thực hiện hai truy vấn đặt/giữ chỗ riêng cho mỗi chỗ trống: 10 chỗ: 21 SELECT; 100 chỗ: 201 SELECT | Cùng hai predicate cam kết được đặt vào truy vấn có EXISTS: 10/100 chỗ đều 1 SELECT khi site đã được nạp | Ca query budget tái hiện trước sửa và đạt sau sửa; không gồm truy vấn đăng nhập/cấp quyền. Session chưa nạp site cần thêm truy vấn kiểm tra site. Không suy ra p95 HTTP hoặc số xe/giây từ số SQL |
| Danh sách camera | ORM lấy cả cột `image_bytes` dù JSON chỉ trả metadata | Defer BLOB và đặt raiseload để tránh vô tình tải lại trong lúc serialize; ảnh chỉ đọc tại endpoint ảnh được kiểm quyền | Test kiểm câu SELECT thực tế, body metadata, đọc ảnh hợp lệ và các test cách ly quyền hiện có. Không thay đổi dữ liệu ảnh hay thời hạn lưu |
| Thứ tự chữ OCR | Chia tọa độ y thành dải 10 px; hai cụm chữ hơi nghiêng cùng dòng có thể bị đảo | Gom box có chồng lấp dọc tương đối rồi đọc trái→phải trong từng dòng; dùng cùng helper trong runtime và evaluator | Ca hình học tái hiện `1234551A` thay vì `51A-123.45` đã sửa; test một/hai dòng, nhiều tỷ lệ và đầu vào rỗng. Không tự thay O/0 hoặc dùng đáp án sửa dự đoán |

Availability vẫn bảo vệ cam kết tương lai vì lượt gửi không hẹn giờ ra có thể kéo dài. `arrival_deadline` và `end_at` giữ ranh giới loại trừ như trước; chỗ có xe không trở thành khả dụng chỉ vì vé đặt chỗ đã hết hạn. Truy vấn đọc không đổi trạng thái reservation. Nhận xe thực tế vẫn khóa chỗ và kiểm lại quyền/cam kết bên trong transaction; không dùng kết quả dashboard như lệnh giữ chỗ.

Đã đo bổ sung hai đường đọc trong cùng tiến trình và SQLite in-memory riêng, tất cả chỗ trống, cache site đã nạp. Mỗi cấu hình chạy 11 lượt, xen kẽ thứ tự cũ/mới và xác nhận payload bằng nhau. p95 dùng nearest-rank nên với 11 lượt là giá trị lớn nhất quan sát được.

| Số chỗ | p50 cũ → mới (ms) | p95 mẫu cũ → mới (ms) |
|---:|---:|---:|
|10|4,932 → 0,606|6,468 → 0,813|
|100|46,887 → 1,215|49,257 → 1,864|
|500|248,283 → 4,150|297,383 → 5,365|

Mẫu nhỏ này đo service SQLite, không đo HTTP, mạng Supabase, máy Fly hoặc tải đồng thời. Bằng chứng ở `availability-benchmark.json`; script lấy nguyên hàm availability tại baseline từ Git và gọi trong môi trường DB tách biệt. Không dùng số này làm cam kết tốc độ website.

Đã bổ sung test PostgreSQL thật cho ba chỗ, một reservation và một allocation ở tương lai, session mới chưa có site trong bộ nhớ, rồi chuyển đến đúng thời điểm kết thúc. Ca này đã chạy và đạt trong nhóm 17 test PostgreSQL của CI; collect-only cục bộ không được tính là PASS nghiệp vụ PostgreSQL.

## 3. So sánh nhận diện trước/sau trên cùng dữ liệu

Giữ nguyên ONNX SHA256 `85d236280a1301ad98907947d284951dd2b20c23a6786ff50f7e6a8ec515bd50`, manifest 500 crop `4f4545a4f07b732aedc53ee7d9fc098da8adb40494dccc3584eb2188da763a64` và manifest 20 frame `cca84266dbb4c290c111ed18a186808a8aa9e5aebd667c14e023440aed497887`. Nguồn, giấy phép, cách chọn mẫu và giới hạn nhãn nằm trong [PHONE_VN_ACCEPTANCE.md](PHONE_VN_ACCEPTANCE.md).

| Phép đo | Trước | Sau |
|---|---:|---:|
| OCR trực tiếp trên crop ô tô có nhãn |225/250|225/250|
| OCR trực tiếp trên crop xe máy có nhãn |231/250|232/250|
| OCR trực tiếp, tổng |456/500 (91,2%)|457/500 (91,4%)|
| CER OCR trực tiếp |2,5487%|2,4525%|
| Cả YOLO→OCR trên ảnh đã cắt sát biển |64/500 (12,8%)|64/500 (12,8%)|
| Pilot ảnh toàn xe, đúng toàn biển |20/20|20/20|
| Pilot detection TP / FP / FN |20 / 9 / 0|20 / 9 / 0|

Trong 500 crop, hai dự đoán OCR thay đổi: một ảnh từ sai thành đúng, một ảnh vẫn sai nhưng bớt sai ký tự; không có ảnh trước đúng thành sai. Không có lỗi pipeline/OCR trong hai lượt đo mới. 20 frame là pilot cùng camera, nhãn do agent gán trước suy luận và chưa được người kiểm độc lập.

Đây là **đối chiếu hồi quy trên tập đã dùng**, không phải test set mới độc lập. Chênh lệch một ảnh không đủ chứng minh accuracy tổng quát tăng. 91,4% là OCR khi được cung cấp đúng vùng biển, **không phải accuracy website**. Chưa cải thiện detector đối với ảnh cắt sát, chưa loại được chín box thừa ở pilot và chưa đo ảnh điện thoại vật lý. Latency được lưu trong JSON nhưng điều kiện tải máy giữa các lượt khác nhau; không dùng chênh lệch đó để tuyên bố OCR nhanh hơn.

## 4. Giao diện và kiểm thử

Camera hướng dẫn giữ một phần xe quanh biển để phù hợp detector. Khi không tìm được biển, giao diện chỉ rõ cách chụp lại hoặc nhập tay. Nhân viên vẫn phải kiểm tra và xác nhận; thao tác nhận/trả xe và thu tiền riêng giữ nguyên.

- 110 test liên quan trên Windows đạt, gồm reservation/concurrency, vision API, tài chính theo bãi, bộ chấm điểm và test tensor OCR thật với model cục bộ.
- CI Linux: 1.235 passed/21 skipped; PostgreSQL: 17 passed; Windows release safety: 190 passed/1 skipped; test skipped không tính thành pass. CI OCR memory: 6 ảnh trong container 1 CPU/640 MiB/network none, đỉnh 350,6 MiB.
- 139 test frontend, lint và build đạt. Build dùng `VITE_API_URL=https://api.parkingai.am` như workflow phát hành.
- 8 kiểm tra trình duyệt ở 390px/1440px đạt: hướng dẫn chụp, no_plate, nhập tay và không tràn ngang; đã xem cả hai ảnh render. OCR trong kiểm tra giao diện này được giả lập, không phải phép đo accuracy.
- Trước sửa, bốn ca tái hiện thất bại: query budget 10/100, tải BLOB thừa, đảo chữ. Sau sửa, bốn ca này đạt.

Hai ca kiểm trạng thái arrived ban đầu tạo dữ liệu chưa có session hợp lệ và bị constraint từ chối. Đã sửa fixture để nhận xe qua dịch vụ nghiệp vụ rồi kiểm trạng thái arrived; không nới constraint. Lần preview đầu thiếu cấu hình API production nên chưa tới được màn hình camera; build lại đúng cấu hình trước khi kiểm giao diện. Đây là lỗi thiết lập kiểm thử, không được tính là lỗi ứng dụng đã sửa.

Bằng chứng thô tại `backend/artifacts/single-site-optimization/` ngoài Git: `red.log`, `green-focused.log`, `regression-final.log`, `comparison.json`, `crops-after/`, `cctv-after/`, `camera-copy-results.json`, ảnh render và snapshot ứng dụng trước cập nhật. Ảnh, nhãn, mật khẩu và model tiếp tục ở ngoài Git.

## 5. Phát hành và rollback

**Trạng thái: READY cho trình diễn đồ án một bãi trong phạm vi đã kiểm.** Application SHA `3afc56cad9cd6a4d43f56eb96766c7006141dd0f` đã qua [CI 34246127629](https://github.com/lam1826/ParkingAI/actions/runs/34246127629) và [CD 34247663250](https://github.com/lam1826/ParkingAI/actions/runs/34247663250). Windows release safety: 190 passed/1 skipped. CD xác nhận đúng SHA, ready và CORS lúc 22:55 ngày 08/09/2026 (UTC+7).

Trước cập nhật đã lưu HTML/config/bundle, ghi API `76ef211821c52c3e5fae11bb5c980dcd8cabd35c` đang ready. Recovery gate kiểm tra thành công backup Supabase hoàn tất lúc `2026-09-07T16:54:11.668000+00:00`; không chạy restore mới trong lần cập nhật không đổi schema này. Giữ cấu hình 1 CPU/1 GB, model, QR mô phỏng, Gemini tắt và dữ liệu hiện tại.

Nghiệm thu sau CD:

- 18 kiểm tra API đạt: đúng SHA, bundle khớp build, một bãi, đăng nhập manager demo, trạng thái chỗ nhất quán, OCR available, upload một ảnh thử có quyền sử dụng/khớp manifest, biển khớp nhãn ảnh đó, chưa được nhân viên xác nhận, có request ID, danh sách metadata/đọc ảnh hợp lệ và readiness sau OCR. Một observation thử được lưu; không nhận/trả xe hoặc ghi thanh toán.
- OCR của lượt online này mất 9,683 giây. Đây là một lượt, không phải p95 hoặc phép đo tải. Kết quả đúng một ảnh không chứng minh accuracy Việt Nam.
- 31 kiểm tra giao diện online đạt: bốn vai trò đăng nhập, giao diện chỉ có bãi A, camera hoạt động, gói vé/đặt chỗ đúng phạm vi, không lỗi JavaScript hoặc ghi nghiệp vụ. Có bốn cảnh báo Cloudflare CSP đã biết; không nới CSP. Đã xem ảnh render mobile. Không cộng hai nhóm thành số ca độc lập và không gọi viewport là điện thoại thật.
- Bundle `/assets/index-DU4U-j2Z.js` khớp SHA256 `072e94f8fda1a12e1d96324b5133a89d0762614dccbee705314bf28ce342d505`; `/config.js` giữ `SINGLE_SITE_ID: 2`. Bằng chứng ở `online-probe.json`, `online-single-site-results.json` và log CI/CD ngoài Git.

PARK-214/215/216 DONE trong phạm vi này. PARK-209 vẫn IN_PROGRESS vì chưa có nghiệm thu điện thoại vật lý/kiểm nhãn pilot độc lập; PARK-211 giữ FUTURE cho tải API một bãi thực tế. **Vận hành bãi thật: NOT READY**; các giới hạn dữ liệu, OCR và vận hành không được thay bằng kết quả demo.

Nếu có hồi quy, quay lại ứng dụng trước và bản frontend tương ứng. Không cần downgrade schema; giữ mọi dữ liệu/chứng từ phát sinh. Nếu OCR lỗi, có thể tắt engine và dùng nhập tay như runbook hiện có. Restore PG17 của vòng 3 là bằng chứng phục hồi schema hiện tại; không coi snapshot frontend là backup database.

## 6. Phần nên làm tiếp cho đồ án

1. Nghiệm thu chụp iQOO Neo9/Chrome và iPhone/Safari, ghi phiên bản máy/trình duyệt và kết quả từng ca. Hạng mục này vẫn chờ thao tác của người dùng.
2. Thu tập ảnh Việt Nam toàn xe có nhãn và quyền sử dụng, gồm xe máy hai dòng, chói/tối/nghiêng và ảnh không có biển; tách bộ phát triển và bộ kiểm tra mới trước khi đổi model.
3. Nếu cần nhận ảnh đã cắt sát, thêm chế độ **người dùng chủ động chọn ảnh crop** với ghi nhận đường xử lý và kiểm thử riêng. Không tự chạy OCR toàn cảnh mỗi khi detector thất bại.
4. Chỉ thử camera đếm chỗ khi có camera cố định; coi đó là quan sát để đối chiếu sổ gửi xe, không thay quyền đặt chỗ và trạng thái transaction.

Các mục này là lộ trình có điều kiện, không mở lại phạm vi nhiều bãi hoặc dịch vụ có phí.
