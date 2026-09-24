# Sửa nút Bật tự động — 24/09/2026

## Lỗi đã tái hiện

Trên ứng dụng 8793, Admin và Manager có webcam sẵn sàng (`readyState=4`, 1280×720), camera hoạt động và OCR khả dụng nhưng **Bật tự động vẫn bị mờ**. Hai camera chưa có bản ghi quy tắc, nên máy chủ trả `enabled=false`. Giao diện dùng chính cờ này để khóa nút cho mọi vai trò; ô cho phép lại nằm trong phần cài đặt thu gọn.

Bằng chứng trước sửa: `backend/artifacts/camera-auto-uat/0df0465f5c/result.json` và ảnh Admin/Manager/Staff. Kiểm tra trước sửa không gửi ảnh, không bật quy tắc, không tạo lượt gửi xe. Staff bị khóa khi chưa được quản lý cho phép là đúng quyền; assertion cũ muốn mở nút cho Staff không phải yêu cầu sản phẩm và được giải thích trong báo cáo browser.

## Hành vi sau sửa

- Admin/Manager bấm **Bật tự động** ngay tại màn hình camera. Nếu chưa có webcam hoặc nguồn edge thì trình duyệt xin mở webcam. Khi có hình, ứng dụng bật quy tắc qua API, tải lại để xác nhận, rồi mới chụp ảnh mới và xử lý tự động.
- Giữ nguyên ngưỡng điểm và tuổi ảnh đã cấu hình. Không giảm ngưỡng nhận diện để cho ảnh thử được nhận xe. Cài đặt nâng cao cũng không còn ghi đè giá trị bằng mặc định.
- Staff chỉ chạy khi quản lý đã cho phép. Máy chủ vẫn quyết định phân quyền cuối cùng.
- Từ chối quyền camera, video không có hình sau 10 giây, lỗi ghi quy tắc hoặc lỗi đọc xác nhận đều không được báo là đang chạy. Có hướng dẫn/thử tải lại khi không lấy được quy tắc.
- **Dừng tự động** dừng vòng lặp của cửa sổ hiện tại; không tự tắt quy tắc dùng chung của camera. Không gửi vòng mới sau khi dừng; yêu cầu đã tới máy chủ có thể hoàn tất. Tab ẩn tạm dừng gửi vòng mới.
- Yêu cầu nhận/trả xe đã gửi vẫn làm mới danh sách xe và chỗ trống khi hoàn tất sau thao tác Dừng. Không tự đổi lượt xe đang chọn khi người dùng đã dừng/chuyển làn. Tình huống này được kiểm riêng bằng phản hồi thành công có độ trễ mô phỏng, không coi là nhận xe thật bằng OCR.
- Ảnh thiếu tin cậy, xe chưa có hồ sơ hoặc còn phí giữ nguyên quy trình kiểm tra/thanh toán. Loại xe lấy từ hồ sơ phương tiện, chưa phải phân loại bằng hình ảnh.

## Vòng đời ảnh khi chạy lâu

Ảnh đã xử lý thành công (`entered`, `already_entered`, `exited`) có thể được giải phóng khi đầy quota, sau cửa sổ giới hạn tốc độ 60 giây. Phải khớp đầy đủ ảnh, mã sự kiện, camera, bãi và có lượt gửi xe. Lịch sử quyết định, lượt gửi, thanh toán và khả năng gọi lại yêu cầu gốc được giữ; ảnh chưa kiểm tra hoặc đang chờ thanh toán không bị lấy làm chỗ trống. Không gán giả trạng thái người đã duyệt. Gửi lại mã sự kiện của ảnh đã hết lưu trả 410 để chụp ảnh mới; quota 500 và giới hạn tốc độ không thay đổi.

## Kiểm chứng hiện có

- Frontend: **293/293 test**, 0 bỏ qua; ESLint và Vite build thành công. Trong đó 21 test tập trung vào khởi động camera, quyền, giữ cấu hình, lỗi xác nhận, dừng do rời màn hình, ảnh không có hình và lọc ảnh đủ điều kiện.
- Backend cuối: **127/127**, không lỗi/bỏ qua, 31,01 giây; gồm 22 ca mới về quota, ảnh cần người duyệt, giữ lịch sử và chống ghi lại mã ảnh đã giải phóng. Có bài runtime ONNX thật. Test đỏ trước sửa giữ nguyên **4 lỗi/11 đạt**; reproduction quota 1 ảnh nằm ở `processed-frame-quota-probe.json`. Không chạy lại toàn bộ 2.000+ ca trong đợt sửa hẹp này.
- Browser clone 8804: **116/116** kiểm tra bật/dừng/tiếp tục, giữ ngưỡng 0,99 và 12 giây, Staff, ảnh mới sau khi bật quyền, tab ẩn/hiện, webcam lỗi/không hình, lỗi PUT và GET xác nhận cùng phục hồi. `camera-auto-uat/64e3ccbfac/result.json`. Nguồn video mô phỏng dùng ảnh CC0, bộ OCR máy chủ thật đọc `LD4558BI`, điểm khoảng 0,57. Backend trả `manual` với lý do biển không nhất quán/chưa đúng định dạng Việt Nam; điểm dưới ngưỡng cũng không đủ điều kiện nhưng không phải lý do duy nhất được báo. Không tạo lượt xe.
- Kiểm bổ sung cách phân biệt lỗi 503 chủ động mô phỏng bằng đúng `networkId`: **60/60**, `643f1ae414/result.json`. Không gắn mọi 503 trong cùng kịch bản thành lỗi chủ động để che lỗi thật.
- Kiểm đọc trên 8793: **30/30**, `812fe705f5/result.json`; Admin/Manager bấm được dù quy tắc OFF, Staff vẫn bị hạn chế. Không bật quy tắc trên DB dùng chung.
- Kiểm phản hồi hoàn tất sau Dừng: trước sửa **26 đạt/1 lỗi** (`8f2c5c50c0`), sau sửa **27/27** (`ad920cc875`). Giữ phản hồi `/process` mô phỏng thành công đến sau Dừng; bản cuối phát GET cập nhật danh sách/chỗ trống, không chọn lượt giả và không khởi động lại vòng ảnh. Đây là test điều phối UI bằng mock, không phải bằng chứng nhận xe thật.

Các lượt trên có ca chồng lặp, không cộng thành số kịch bản độc lập. Clone lúc chạy batch đầu chưa nạp bản backend quota mới; backend được kiểm riêng 127 ca. Lượt tích hợp frontend/backend cuối sau restart clone đạt **34/34**, không lỗi runtime/HTTP ngoài dự kiến (`f704567da2/result.json`); vẫn dùng OCR thật và giữ kết quả cần kiểm tra, không tạo lượt xe. [Chi tiết browser](CAMERA_AUTOMATIC_START_BROWSER_UAT_2026-09-24.md) ghi từng lượt và ranh giới phiên bản. Clone8804 đã dừng đúng tiến trình; profile Chrome riêng đã xóa.

Ứng dụng 8793 đã nạp backend cuối và bundle `index-gS2ZkbPh.js`; `/ready` trả `ready`, `/sites` trả 200. Kiểm đối chiếu DB dùng chung trước/sau: 0 policy, 489 lượt gửi, 11 ảnh và 0 passage không đổi (`environments/add9801fbf/source-invariant.json`). Khởi động lại demo đổi khóa đăng nhập tạm, có thể cần đăng nhập lại.

Lần đầu harness dừng vì giả định endpoint danh sách lượt trả `total` nhưng API trả mảng; chưa kiểm tới nút. Đã sửa cách đếm có phân trang, giữ kết quả lỗi tại `2292cf68b8/result.json`; không gọi lỗi công cụ kiểm là lỗi sản phẩm và không xóa bằng chứng.

Log Node/build: `backend/artifacts/camera-automation-20260924/`. Bản sao UAT và ảnh browser: `backend/artifacts/camera-auto-uat/`. Không lưu mật khẩu/token trong báo cáo.

## Giới hạn nhận diện

Sửa được điều kiện bật nút không đồng nghĩa OCR đã đọc tốt mọi biển. [Báo cáo nhận diện](CAMERA_SCAN_DIAGNOSIS_2026-09-24.md) giữ nguyên các mẫu sai/không đọc được và phân biệt pipeline với OCR riêng. Video thử từ ảnh cố định là mô phỏng nguồn camera, chưa phải nghiệm thu webcam/điện thoại vật lý của người dùng.
