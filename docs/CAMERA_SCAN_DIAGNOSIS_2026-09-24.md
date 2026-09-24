# Kiểm tra lỗi camera có hình nhưng không đọc biển số

Ngày 24/09/2026, trên bản thật tại `http://127.0.0.1:8793`, dùng cơ sở dữ liệu demo tổng hợp đã được đánh dấu. Không truy cập camera vật lý, không tạo giao dịch ngân hàng và không đổi ngưỡng nhận diện.

**Đính chính trong cùng phiên:** nhận định ban đầu rằng không có bộ ảnh Việt Nam cục bộ là sai do tìm thiếu thư mục. Bộ 20 ảnh toàn xe và 500 ảnh crop đã có sẵn trong `backend/artifacts/phone-vn-acceptance/`; đã kiểm tra hash và chạy lại toàn bộ bằng model hiện tại, kết quả mới ở phần dưới. Vẫn chưa có khung hình từ camera đang gây lỗi của người dùng.

## Nguyên nhân đã tái hiện

- API `/api/v2/vision/status` báo `yolo_rapidocr`, `available=true`; model và thư viện CPU có sẵn.
- Cả hai làn đều có chính sách tự động `enabled=false`; chưa có quan sát nào được gửi lên máy chủ trước khi kiểm tra.
- `Dùng webcam` chỉ mở video. Vòng chụp/gửi ảnh cũ yêu cầu đồng thời `running=true` và chính sách tự động bật; giao diện không có nút quét riêng. Vì vậy có hình nhưng không có yêu cầu OCR. Browser tái hiện video sẵn sàng nhưng thiếu thao tác quét: 6 kiểm tra qua, 1 lỗi, không có POST ảnh.
- Phát hiện thêm khi xem lại ảnh đã xác nhận: ô biển số vẫn cho sửa nhưng thao tác dùng biển số lấy giá trị đã xác nhận cũ. Browser tái hiện sửa `AWY-U50` thành `AWY-U51` nhưng biểu mẫu nhận lại `AWY-U50`.

## Thay đổi

- Thêm **Quét biển số** độc lập với quyền tự động nhận/trả xe. Webcam cung cấp khung hình thật cho cùng bộ OCR trên máy chủ.
- Ảnh chụp một lần đi qua `/vision/observations`, giữ `manual_upload` và chờ kiểm tra. Chỉ vòng tự động gửi `/vision/live-frames`. Ảnh quét thủ công không thể được một cửa sổ tự động khác dùng để tự nhận/trả xe.
- Hiện riêng các kết quả: gợi ý biển số, chưa phát hiện biển, bộ nhận diện chưa cấu hình, lỗi xử lý; hiển thị điểm nhận diện như một điểm số, không gọi đó là tỷ lệ chính xác. Khi ảnh mới không đọc được, xóa gợi ý cũ khỏi ô biển số.
- Chụp có kiểm tra video đã có hình, giới hạn cạnh dài 1600px, JPEG tối đa 2MB; chống gửi trùng trong lúc đang đọc. Ngừng webcam giải phóng track. Nút tự động cần webcam hoặc camera ngoài đã cấu hình.
- Khóa trường của ảnh đã xử lý; giải thích phải quét/chọn ảnh mới để kiểm tra nội dung khác. Chính sách, điểm tối thiểu 0,97, tuổi ảnh, xác nhận thủ công, quyền truy cập và quy tắc phí không bị nới lỏng.

Các tệp: `CameraOperations.jsx`, `cameraCapture.js`, `cameraCapture.test.js`; `OperationsPanel.jsx` chỉ đổi tiêu đề thành “Đọc biển số”. Thêm `frontend/tests/browser/camera_scan_uat.py` để tái hiện và kiểm tra bằng video mô phỏng từ ảnh CC0, gọi OCR thật.

## Kết quả nhận diện thật, gồm trường hợp thất bại

| Ảnh CC0 cục bộ | Biển số đọc bằng mắt | Kết quả CPU và API ảnh gốc | Điểm kết hợp | Kết luận |
|---|---|---|---|---|
| `rolls-royce-cc0.jpg` | `LD-45-58-BI` | `LD4558BI` | 0,5642 | Khớp khi bỏ dấu phân cách |
| `colorado-cc0.jpg` | `AWY-U50` | `no_plate`, không có gợi ý | Không có | **Thất bại nhận diện** |

Hai POST thực tế đều HTTP 201, ảnh ở trạng thái `pending` và nguồn `manual_upload`. HTTP 201 chỉ chứng minh tiếp nhận ảnh, không chứng minh đọc đúng biển.

Với Colorado, kiểm tra đầu ra thô của detector cho điểm cao nhất **0,012762**, thấp hơn ngưỡng phát hiện **0,3**, không có hộp ứng viên. OCR không được gọi vì detector không tìm thấy biển. Đây là trường hợp model phát hiện bỏ sót, không phải lỗi quyền camera hay thiếu thư viện. Không sửa expected thành thành công, không hạ ngưỡng, không ghép biển số biết trước vào kết quả.

Trong browser, canvas video mô phỏng rồi nén JPEG cho Rolls trả đúng `LD4558BI`, giao diện làm tròn điểm thành `0,57`. Nguồn video là ảnh công khai, **không phải kiểm tra thiết bị vật lý**. Hai mẫu nước ngoài không đủ để công bố độ chính xác trên biển Việt Nam.

## Chạy lại bộ biển Việt Nam đã đóng băng

Đây là phép đo mới ngày **24/09/2026, 09:24–09:26 giờ Việt Nam**, không chép số lịch sử. Dùng nguyên `edge/evaluate_plates.py`, ONNX đã ghim và các nhãn từ manifest. Hash cả hai manifest, hai archive, model và toàn bộ 520 ảnh đều khớp dữ liệu đã ghi trong [PHONE_VN_ACCEPTANCE.md](PHONE_VN_ACCEPTANCE.md). Không thay nhãn, ngưỡng, weights, bộ tiền xử lý hay backend đang chạy.

| Tập và cách chạy | Đúng toàn biển | Sai / không có gợi ý | Giới hạn |
|---|---:|---:|---|
| 20 frame toàn xe, YOLO → OCR | **20/20** | 0/20 | Pilot một camera, 18 biển khác nhau; nhãn do agent gán, chưa được người kiểm tra độc lập |
| 500 crop, YOLO → OCR như pipeline ứng dụng | **64/500** | **436/500** | Ô tô 64/250; xe máy **0/250**. Không giấu nhóm thất bại này |
| 500 crop, chỉ đọc OCR trực tiếp tại crop có nhãn | **457/500** | **43/500** | Ô tô 225/250, xe máy 232/250; bỏ qua detector nên không phải accuracy của website |

Pilot toàn xe: detector ghép đúng 20 hộp, **9 hộp thừa**, 0 hộp nhãn bị bỏ sót ở IoU ≥ 0,5. Không có ảnh âm tính nên chưa đo được tỷ lệ báo biển giả trên ảnh không có biển. Cả hai lần chạy có 0 lỗi runtime; kết thúc chương trình thành công không có nghĩa tất cả biển đều đọc đúng.

Phân tích 436 crop thất bại từ dự đoán mới: **413 ảnh không có detection** (163 ô tô + toàn bộ 250 xe máy), 3 ảnh có hộp nhưng không đọc được chữ, 20 ảnh có gợi ý sai. `failure-breakdown.json` giữ số liệu này; nhãn/đáp án không được dùng để sửa dự đoán.

Crop được lấy trước suy luận theo lựa chọn đóng băng 250 ô tô + 250 xe máy, có nhãn publisher; chưa có gán nhãn độc lập lại toàn bộ. Tập crop đo hạn chế với đầu vào cắt sát biển, không suy ra khả năng phát hiện trên ảnh toàn xe. Các tập này không đại diện cho mọi camera/điện thoại, ban đêm, xe máy toàn cảnh hoặc bãi thực; chưa loại trừ trùng dữ liệu huấn luyện của publisher.

Bằng chứng mới:

- `backend/artifacts/camera-scan-uat/vn-current-20260924/hash-validation.json` — kiểm tra provenance/hash.
- `vn-current-20260924/cctv/results.json` và `predictions.jsonl` — 20 kết quả toàn xe; đo lúc `2026-09-24T02:24:44.974260+00:00`.
- `vn-current-20260924/crops/results.json` và `predictions.jsonl` — đủ 500 mẫu, kể cả sai/không phát hiện; đo lúc `2026-09-24T02:26:44.962230+00:00`.
- Runtime Windows, Python 3.12.14, ONNX Runtime 1.23.2, RapidOCR 1.4.4; JSON giữ hash mã runtime/evaluator và model.
- Browser chọn cố định **phần tử đầu tiên của manifest**, `cctv-01`, không chọn theo dự đoán: `51F21255` → `51F-212.55`, điểm 0,7891, có thêm 1 hộp thừa không đọc được chữ. `backend/artifacts/camera-scan-uat/5e62903f91/result.json`: **27/27 kiểm tra quy trình**, không lỗi API/runtime, không tự nhận xe; nhãn vẫn `human_reviewed=false`. Colorado đi kèm vẫn thất bại, báo cáo giữ `ocr_accuracy_passed=false`. Đây là video mô phỏng từ ảnh VN, chưa phải thiết bị thật.

## Kiểm tra và bằng chứng

- 7/7 kiểm tra Node cho chụp ảnh và lọc ảnh tự động; ESLint các tệp thay đổi không lỗi.
- 10/10 `test_vision_runtime_budget.py`, có đặt `PARKING_VISION_TEST_MODEL` tới model ONNX cục bộ; không bỏ qua bài runtime tùy chọn.
- 21/21 `test_plate_evaluation.py` sau khi chạy lại bộ VN.
- Browser trước sửa: `backend/artifacts/camera-scan-uat/c801ff88e4/result.json` — thiếu nút quét, 6/7.
- Browser sau sửa luồng quét: `backend/artifacts/camera-scan-uat/1fafb4e5a3/result.json` — 22/22 kiểm tra giao diện/quy trình, không lỗi API/runtime. Ảnh không nhận diện được được báo rõ, nhân viên sửa rồi chuyển sang biểu mẫu thủ công, không có yêu cầu tự nhận/trả xe.
- Browser tái hiện lỗi sửa ảnh đã xác nhận: `backend/artifacts/camera-scan-uat/bce28ea62a/result.json` — 25/26, ghi nguyên lỗi bỏ qua giá trị vừa sửa.
- Browser cuối sau build: **27/27 kiểm tra giao diện/quy trình**, `backend/artifacts/camera-scan-uat/00e83b7fc3/result.json`. Xác minh trường đã xác nhận chỉ đọc và có hướng dẫn sửa bằng ảnh mới; 3 ảnh chụp màn hình desktop/mobile; không lỗi API/runtime và đã xóa profile riêng. Cùng báo cáo ghi rõ **OCR khớp 1/2 mẫu, `ocr_accuracy_passed=false`**; kết quả xanh của quy trình không biến mẫu Colorado thành nhận diện thành công.
- `cpu-fixtures.json`, `api-fixtures.json`, `detector-diagnosis.json` trong cùng thư mục bằng chứng giữ cả kết quả Colorado thất bại.
- Lần browser đầu tiên trong sandbox Windows dừng trước giao diện vì Chrome GPU không chạy (`9a1bab40f7`). Các lần sau chạy Chrome riêng ngoài sandbox theo quyền được duyệt. Mỗi lần đều xóa profile riêng; không lưu mật khẩu/token.

Chạy lại từ thư mục dự án:

```powershell
.\.venv\Scripts\python.exe frontend/tests/browser/camera_scan_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json
$env:PARKING_VISION_TEST_MODEL = (Resolve-Path backend/artifacts/vision/license-plate-yolov8n.onnx).Path
.\.venv\Scripts\python.exe -m pytest tests/test_vision_runtime_budget.py -q -o addopts=''
.\.venv\Scripts\python.exe edge/recognize_image.py backend/artifacts/vision/colorado-cc0.jpg --model backend/artifacts/vision/license-plate-yolov8n.onnx
.\.venv\Scripts\python.exe frontend/tests/browser/camera_scan_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --positive-fixture vn-first
# Chọn thư mục kết quả mới; evaluator không ghi đè bằng chứng cũ.
.\.venv\Scripts\python.exe edge/evaluate_plates.py backend/artifacts/phone-vn-acceptance/manifest-cctv.json --model backend/artifacts/vision/license-plate-yolov8n.onnx --output backend/artifacts/camera-scan-uat/vn-reproduction/cctv
.\.venv\Scripts\python.exe edge/evaluate_plates.py backend/artifacts/phone-vn-acceptance/manifest-crops.json --model backend/artifacts/vision/license-plate-yolov8n.onnx --output backend/artifacts/camera-scan-uat/vn-reproduction/crops
```

## Phạm vi chưa đạt nghiệm thu

Lỗi không gửi ảnh từ màn hình webcam đã được sửa và có kiểm tra browser gọi OCR thật. Bộ VN lưu sẵn đã được đo lại, nhưng khả năng đọc mọi biển chưa đạt: mẫu Colorado vẫn bỏ sót và pipeline crop sai/không đọc được 436/500 mẫu. Chưa có ảnh lấy từ camera đang gây lỗi của người dùng để xác minh góc chụp, độ nét, ánh sáng hoặc sai ký tự. Cần khung hình thực tế đó để đánh giá tiếp; phép đo tập lưu sẵn và video mô phỏng không thay thế nghiệm thu phần cứng hoặc độ chính xác ngoài thực địa.
