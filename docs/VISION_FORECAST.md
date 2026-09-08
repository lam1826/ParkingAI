# Camera điện thoại, YOLO và dự báo trong bản đồ án

## 1. Phạm vi đang triển khai

Điện thoại chụp hoặc chọn ảnh JPEG/PNG/WebP; giao diện thu nhỏ, chuyển sang JPEG rồi tải lên camera đã khai báo của bãi. Backend dùng model YOLOv8n nhận diện **vùng biển số**, sau đó RapidOCR đọc chữ trong vùng đó. Nhân viên đối chiếu ảnh, sửa biển số và xác nhận. Kết quả chỉ điền sẵn vào màn hình xe vào/tra cứu xe ra; nghiệp vụ vào/ra, chỗ trống và thu phí vẫn phải được xác nhận riêng.

YOLO dùng model được huấn luyện riêng cho biển số; model COCO thông thường nhận diện ô tô không thay thế được model này. Adapter chạy ONNX trên CPU, không dùng file pickle `.pt`, không tải model khi có yêu cầu API. RapidOCR 1.4.4 chứa các model OCR ONNX của PaddleOCR trong gói cài đặt. Chưa có tập kiểm thử biển Việt Nam để kết luận độ chính xác.

## 2. Cài model và chạy bằng máy tính

Chạy từ thư mục `ParkingAI`, Python 3.10–3.12:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-vision.txt
.venv/Scripts/python.exe edge/download_vision_model.py
.venv/Scripts/python.exe edge/download_demo_images.py
$env:PARKING_VISION_ENGINE = 'yolo_rapidocr'
$env:PARKING_VISION_MODEL = (Resolve-Path 'backend/artifacts/vision/license-plate-yolov8n.onnx').Path
```

Hai biến môi trường phải được đặt trong tiến trình khởi động API. `GET /api/v2/vision/status` trả trạng thái thư viện/model. Khi chưa cài hoặc tắt `PARKING_VISION_ENGINE=disabled`, giao diện vẫn cho lưu ảnh và nhập biển số thủ công, hiển thị rõ chưa nhận diện. Model lỗi trả `ocr_status=error`, ghi traceback ở log server và chuyển status sang `degraded` cho tới lần nhận diện thành công tiếp theo; phản hồi không lộ đường dẫn model. Ảnh không tìm thấy chữ trả `no_plate`, không sinh biển số giả.

Chạy kiểm chứng độc lập, chưa cần API hay CSDL:

```powershell
.venv/Scripts/python.exe edge/recognize_image.py backend/artifacts/vision/rolls-royce-cc0.jpg --model backend/artifacts/vision/license-plate-yolov8n.onnx --output backend/artifacts/vision/smoke-rolls.json
.venv/Scripts/python.exe edge/recognize_image.py backend/artifacts/vision/colorado-cc0.jpg --model backend/artifacts/vision/license-plate-yolov8n.onnx --output backend/artifacts/vision/smoke-colorado.json
```

Thư mục `backend/artifacts/` bị loại khỏi Git. Downloader xác minh SHA-256 và từ chối ghi đè model/ảnh khác mã kiểm tra. Không truyền đường dẫn model do khách hàng gửi vào endpoint.

## 3. Demo trên điện thoại

1. Khởi động bản demo trên laptop, kết nối điện thoại và laptop cùng Wi-Fi; dùng địa chỉ LAN được script demo in ra.
2. Đăng nhập tài khoản quản trị/nhân viên, mở **Camera biển số**, chọn bãi và camera cổng vào/cổng ra. Quản trị có thể tạo cấu hình camera điện thoại; không cần RTSP/IP camera.
3. Bấm chụp ảnh hoặc chọn từ thư viện. Dùng ảnh rõ nét, đủ sáng, nhìn được cả xe và vùng biển. Giao diện nhận JPEG/PNG/WebP tối đa **20 MB**, tự thu nhỏ cạnh dài còn 1600 pixel và chuyển sang JPEG trước khi gửi. API chỉ nhận JPEG/PNG tối đa **2 MB**, tối đa 12 triệu điểm ảnh. HEIC chưa hỗ trợ; nếu trình duyệt không giải mã được ảnh, xuất sang JPEG rồi thử lại.
4. Xem khung biển số và gợi ý OCR, sửa ký tự sai. Chỉ bấm xác nhận khi đã đối chiếu ảnh; ảnh không phù hợp có thể từ chối.
5. Màn hình vận hành nhận biển số đã duyệt. Chọn loại xe/vị trí để ghi xe vào; với xe ra, tìm lượt đang gửi, xem báo phí và xác nhận thu tiền.

Nút chụp dùng lựa chọn file/camera của trình duyệt (`capture=environment`), không truyền video liên tục. Việc trình duyệt có mở ngay camera hay hộp chọn ảnh phụ thuộc điện thoại. Không cần kết nối camera thật hoặc tài khoản nhà cung cấp.

## 4. Lưu ảnh và phân quyền

- Camera, ảnh và lịch sử duyệt thuộc một bãi; nhân viên ngoài bãi không được tải lên hoặc xem ảnh.
- Upload được giới hạn trước khi phân tích multipart. Ảnh được giải mã rồi lưu lại thành JPEG, loại bỏ EXIF/vị trí GPS và dữ liệu phụ. JPEG điện thoại dạng MPO chỉ giữ ảnh chính.
- Mỗi camera tối đa 30 ảnh/phút, mỗi bãi tối đa 500 ảnh; một tác vụ nhận diện
  tại một thời điểm trên mỗi tiến trình API. Khi đủ 500, hệ thống loại ảnh đã
  duyệt cũ nhất, ưu tiên ảnh bị từ chối và không tự xóa ảnh đang chờ duyệt. Nếu
  cả 500 ảnh đều đang chờ thì trả 409. Khi bộ nhận diện bận, API trả 429.
- Mặc định lưu 24 giờ, cấu hình 1–72 giờ. Giảm thời hạn có hiệu lực với cả ảnh
  đã lưu ở chu kỳ bảo trì kế tiếp. Ảnh hết hạn không còn đọc được. Quản lý có
  thể xóa từng ảnh trên giao diện; worker hoặc lệnh dưới đây xóa vật lý ảnh hết
  hạn.
- Đường dẫn ảnh cần token đăng nhập, phản hồi `Cache-Control: no-store`; không phát URL công khai. Nhận diện thất bại không làm thay đổi lượt gửi xe.
- Camera mạng sau này có thể gửi `POST /api/v2/vision/edge-events` bằng `X-Camera-Token` riêng camera. Token chỉ ghi ảnh, không đọc biển số; xoay khóa hoặc tắt camera thu hồi khóa cũ. Bản đồ án không cần bật tính năng này.

```powershell
Set-Location backend
../.venv/Scripts/python.exe -m expansion.vision_service purge-expired
```

Lệnh bảo trì dùng `DATABASE_URL` của bản demo đang vận hành. Không trỏ sang dữ liệu khác.

## 5. Kết quả kiểm chứng thật ngày 07/09/2026

Môi trường CPU cục bộ, ONNX Runtime 1.23.2, RapidOCR ONNX Runtime 1.4.4. Mỗi lệnh chạy trong tiến trình mới. Thời gian dưới đây là phép đo đơn lẻ gồm nạp model, không phải benchmark tải hoặc cam kết tốc độ.

| Ảnh | Kết quả | Điều cần nêu khi bảo vệ |
|---|---|---|
| Xe Rolls-Royce, 1280 × 853 | Có khung `[513,708,639,742]`, OCR `LD445558`, độ tin cậy kết hợp 0,4804, 2,222 giây | Vùng biển được tìm đúng; chữ đọc tay là `LD-45-58-BI`, **OCR chưa đúng** nên phải sửa |
| Biển Colorado, 546 × 316 | `no_plate`, không gợi ý chữ, 0,673 giây | Thể hiện trường hợp detector không tìm thấy; nhân viên nhập thủ công |

Điểm confidence là tích điểm detector/OCR, **không phải tỷ lệ chính xác đã kiểm chứng**. Hai ảnh nước ngoài không chứng minh chất lượng trên biển xe Việt Nam. Muốn đánh giá tiếp cần bộ ảnh được phép sử dụng, có nhãn đúng, tách tập huấn luyện/kiểm thử và báo cáo riêng: tỷ lệ tìm đúng vùng, tỷ lệ đọc đúng toàn biển, lỗi ký tự, thời gian xử lý, ảnh tối/mờ/nghiêng/hai dòng.

Ảnh Rolls-Royce của Paulo César Santos, ảnh Colorado của SuperSonic337 đều có giấy phép CC0 trên [trang ảnh xe](https://commons.wikimedia.org/wiki/File:Rolls_Royce_in_Porto_Amboim,_Angola.JPG) và [trang ảnh biển](https://commons.wikimedia.org/wiki/File:Colorado_license_plate.jpg). Downloader lưu tác giả, nguồn và SHA-256 trong `SAMPLE_PROVENANCE.json`.

Model lấy từ [ml-debi/yolov8-license-plate-detection](https://huggingface.co/ml-debi/yolov8-license-plate-detection), revision `8062e8e86734e272c60fa9a819433327ebdb66d7`, SHA-256 `85d236280a1301ad98907947d284951dd2b20c23a6786ff50f7e6a8ec515bd50`, 12.238.119 byte. Model card ghi MIT nhưng metadata trong ONNX ghi AGPL-3.0; tài liệu này ghi nhận mâu thuẫn, không kết luận weights được sử dụng tự do theo MIT. Cần giữ thông tin nguồn và đối chiếu [điều khoản Ultralytics](https://www.ultralytics.com/license) khi phân phối. Nguồn bộ huấn luyện chưa được người đăng model mô tả. Thông tin OCR tham khảo [RapidOCR](https://github.com/RapidAI/RapidOCR).

## 6. Dự báo và gợi ý nhân sự

`GET /api/v2/insights/forecast?site_id=...&horizon_hours=24` tổng hợp lượt theo giờ của từng bãi; dữ liệu ngày/giờ dùng múi giờ Việt Nam. Yêu cầu tối thiểu 42 ngày lịch sử, tối đa 84 ngày và 100.000 lượt trong cửa sổ. Giờ chưa kết thúc và dữ liệu tương lai không vào tập huấn luyện. Dữ liệu rỗng/thiếu trả `insufficient_data`, không sinh dự báo.

Mô hình lấy trung bình cùng thứ/cùng giờ các tuần trước, dự báo 1–48 giờ; trả cả xe vào và xe ra. Kiểm thử theo thời gian trong 14 ngày cuối, mỗi mốc chỉ dùng dữ liệu trước mốc đó. MAE được so với cách lấy cùng giờ tuần trước; nếu kém hơn, API cảnh báo. Khoảng thấp/cao phản ánh biến động quan sát, chưa được hiệu chuẩn để khẳng định xác suất. Giờ không có bản ghi được xem là 0; cần đối chiếu thời gian mất dữ liệu trước khi sử dụng.

### Độ phủ dữ liệu của dự báo

Trường `coverage` trong phản hồi dự báo (và được sao chép vào `staff-plan`) cho biết ước lượng dựa trên bao nhiêu quan sát thật, tính trên cửa sổ lịch sử `[window_start, window_end)`:

| Trường | Ý nghĩa |
|---|---|
| `history_days` / `required_days` | Số ngày lịch sử có được so với mức tối thiểu 42 ngày |
| `days_with_arrivals` | Số ngày có ít nhất một bản ghi xe vào |
| `hours_in_window` | Tổng số khung giờ trong cửa sổ |
| `hours_with_arrivals` / `hours_with_departures` | Số khung giờ có bản ghi xe vào / xe ra lớn hơn 0 |
| `hours_zero_filled` | `hours_in_window - hours_with_arrivals`: số giờ mô hình coi là 0 lượt vì không có bản ghi |
| `observation_completeness` | Luôn là `"unknown"` ("Chưa xác định" trên giao diện): hệ thống không có nhật ký hoạt động của nguồn ghi nhận nên không phân biệt được giờ vắng xe thật với giờ mất ghi nhận |
| `completeness_note` | Diễn giải tiếng Việt của điều trên; không được suy ra mất dữ liệu hay giờ vắng xe từ các con số này |
| `sparse_history` | `true` khi `days_with_arrivals < 0,6 × history_days` hoặc `hours_with_arrivals < 0,15 × hours_in_window`; kèm cảnh báo "Lịch sử thưa: ..." |

Mỗi dòng trong `predictions` có thêm `samples_observed` (số tuần tham chiếu có bản ghi lớn hơn 0) và `samples_zero_filled` (số tuần tham chiếu được điền 0); giao diện hiển thị cột "Tuần có bản ghi" dạng `quan sát/tổng tuần`. Các trường này chỉ mô tả dữ liệu đầu vào, không phải thước đo chất lượng dự báo.

`POST /api/v2/insights/staff-plan` nhận thời gian phục vụ 5–600 giây/lượt, tỷ lệ sử dụng 0,3–0,95 và 0–50 nhân viên. Công thức dùng tổng xe vào/ra chia công suất mỗi nhân viên; trả nhu cầu, số có thể bố trí và phần vượt công suất. Mặc định năng suất là giả định; nguồn “đã đo” cần khai báo ít nhất 30 mẫu nhưng hệ thống vẫn ghi chưa xác minh số mẫu. Không tự phân công người hoặc thay thế quy định nghỉ/ca làm.

`GET /api/v2/insights/anomalies` trả cảnh báo lượt gửi lâu và cờ chỗ đỗ không khớp lượt đang gửi, kèm bằng chứng số liệu. Đây là quy tắc kiểm tra vận hành, không phải kết luận gian lận.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_expansion_vision_api.py tests/test_expansion_forecast.py tests/test_expansion_insights_api.py -q
```

Kiểm thử bao gồm giới hạn ảnh, MIME sai, JPEG điện thoại MPO, phân quyền bãi, hết hạn ảnh, mã sự kiện lặp, thu hồi khóa camera, tranh chấp duyệt, dữ liệu dự báo rỗng, ngăn rò dữ liệu tương lai, xe ra trong kỳ dù đã vào trước kỳ và tham số công suất nhân sự. Các test tự động không tải model, ảnh mạng hoặc gọi LLM; hai phép chạy model thật ở trên là kiểm chứng riêng.

## 7. Tạo lịch sử giả để trình diễn dự báo

Script `backend/expansion/demo_seed.py` chỉ tạo CSDL SQLite mới cùng tệp đánh dấu `<database>.demo.json`. Script từ chối đường dẫn đã tồn tại, dựng CSDL trong thư mục tạm qua quy trình rollout, kiểm tra schema và ràng buộc rồi mới công bố tệp đích. Lỗi khi tạo dữ liệu không để lại bản demo dở dang; tệp xuất hiện đồng thời ở đích cũng không bị ghi đè.

Dữ liệu gồm hai bãi DEMO, 32 vị trí, bốn gói vé, bốn cấu hình camera, tài khoản quản trị/quản lý/nhân viên/khách và hai xe đã xác minh của khách. Có 56 ngày lịch sử tạo bằng quy luật theo thứ/giờ và một xe máy đang đỗ. Toàn bộ lượt lịch sử có dấu `demo://synthetic-history`, phí bằng 0 và không sinh phiếu thu. Lịch sử này chỉ giúp trình diễn biểu đồ và phép kiểm thử theo thời gian; không được dùng để tuyên bố chất lượng dự báo trên bãi thật.

Tài khoản `staff_demo` và `manager_demo` chỉ được vận hành bãi A; `admin_demo` xem cả hai bãi; `customer_demo` chỉ xem hồ sơ và phương tiện của mình. Chạy theo hướng dẫn khởi động demo chính của dự án để dùng đúng đường dẫn, mật khẩu và địa chỉ điện thoại.
