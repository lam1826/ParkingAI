# Nghiệm thu camera điện thoại và biển số Việt Nam

## Phạm vi nộp đồ án

Theo điều chỉnh ngày 08/09/2026, bản trình diễn chỉ dùng **một bãi**: bãi DEMO A, ID 2 trên website hiện tại. Bốn vai trò dùng tài khoản admin, manager_a, staff_a và customer_a trong tệp bàn giao cục bộ. Không cần trình diễn bãi B, phân bổ giữa nhiều bãi hoặc so sánh chuỗi bãi.

`frontend/public/config.js` đặt `SINGLE_SITE_ID: 2`: trang vào mặc định mở vận hành bãi; camera, dự báo, đặt chỗ và gói vé dùng bãi này; ẩn đổi/tạo bãi. Người không có quyền bãi 2 không được tự chuyển sang bãi khác. Đây là phạm vi **giao diện đồ án**; quyền server và dữ liệu lịch sử vẫn theo các guard hiện có. Khi chạy trên DB khác phải đặt đúng ID bãi. Bỏ thuộc tính này để khôi phục giao diện tổng quát; không cần migration hay xóa dữ liệu.

## 1. Cách thử nhanh trên điện thoại

1. iQOO Neo 9 dùng Chrome; iPhone dùng Safari. Mở `https://parkingai.am/vision`.
2. Đăng nhập nhân viên demo bãi A. Mật khẩu nằm trong `backend/artifacts/phone-vn-acceptance/private/TAI_KHOAN_DO_AN_MOT_BAI.md`, không đưa vào tài liệu Git.
3. Chọn camera/làn **Xe vào**. Giao diện một bãi đã chọn sẵn bãi đỗ; nếu đang dùng bản cũ, chọn bãi DEMO A.
4. Bấm **Chụp bằng điện thoại**, chụp xe của mình hoặc xe được phép dùng làm mẫu. Giữ được phần xe xung quanh biển, đủ sáng, tránh chói; không chỉ đưa ảnh đã cắt sát vùng biển cho YOLO.
5. Chọn **Dùng ảnh/OK**, đợi kết quả. Ghi biển thật trước khi đối chiếu gợi ý. Kiểm tra ảnh gốc, khung và ảnh cắt. Nếu sai hoặc không có gợi ý, nhập biển đúng tại **Biển số đã kiểm tra**.
6. Bấm **Xác nhận và xử lý xe**. Màn hình vận hành phải nhận đúng biển đã sửa, đúng bãi. Dừng tại đây khi chỉ nghiệm thu camera; bước này chưa tạo lượt gửi, trả xe hay thu tiền.

Ghi lại từng máy theo mẫu: `Tên máy / OS / trình duyệt / giờ thử / mở camera / tải ảnh / OCR đúng-sai / sửa và chuyển màn hình / lỗi nếu có`. Không gửi mật khẩu, JWT hoặc ảnh giấy tờ cá nhân.

## 2. Các ca cần có để nghiệm thu thiết bị thật

Chạy lần lượt trên từng máy, tránh hai ảnh nhận diện đồng thời. Kết quả người dùng thực hiện và bằng chứng ảnh/mã quan sát được lưu cục bộ. Chỉ biết tên điện thoại hoặc mô phỏng viewport không đủ đánh dấu PASS.

| Mã | Thao tác | Điều kiện đạt |
|---|---|---|
| P01 | Đăng nhập, mở camera, chụp trực tiếp ảnh đủ sáng | Camera mở; ảnh được tải; giao diện có kết quả hoặc trạng thái không đọc được rõ ràng; trang không treo |
| P02 | Chọn ảnh JPEG từ thư viện, thử dọc/ngang | Ảnh không xoay sai; khung và crop khớp ảnh; không tràn ngang |
| P03 | Chụp biển ô tô một dòng và xe máy hai dòng | Ghi riêng biển thật/gợi ý, đúng toàn biển hay cần sửa; không lấy confidence làm accuracy |
| P04 | Chụp nghiêng và thiếu sáng/chói | Ghi kết quả kể cả thất bại; vẫn cho kiểm tra/nhập tay; không tự nhận xe |
| P05 | Hủy hộp chụp/chọn ảnh, sau đó chụp lại | Không tạo ảnh/lượt gửi khi hủy; lần thử tiếp theo hoạt động |
| P06 | Sửa một ký tự, xác nhận kết quả | Màn hình vận hành nhận biển **đã sửa**, chưa phát sinh lượt gửi hoặc khoản thu |
| P07 | Mất mạng trước khi tải ảnh, bật lại và thử tiếp | Có thông báo lỗi, nút dùng lại được; không ghi nghiệp vụ trùng |
| P08 | Bấm tải/xác nhận lặp khi đang xử lý | Không phát sinh thao tác kép; kết quả cuối hiển thị rõ |

JPEG/PNG/WebP là phạm vi giao diện đang hỗ trợ. HEIC chưa nằm trong hợp đồng; ghi rõ nếu Safari trả HEIC hoặc không cho chọn, không chuyển một ca lỗi thành PASS bằng cách bỏ qua. Thử thêm JPEG và ghi riêng kết quả. Tốc độ mạng và lần khởi động OCR đầu tiên có thể khác thời gian suy luận cục bộ.

## 3. Bộ đo độc lập ngày 08/09/2026

Model YOLO ONNX giữ nguyên bản phát hành: revision `8062e8e86734e272c60fa9a819433327ebdb66d7`, SHA-256 `85d236280a1301ad98907947d284951dd2b20c23a6786ff50f7e6a8ec515bd50`. Runtime: Python 3.12.14, ONNX Runtime 1.23.2, RapidOCR 1.4.4 trên Windows. Không huấn luyện, đổi ngưỡng hoặc sửa dự đoán dựa vào nhãn của tập đo. Không chạy benchmark tải trên Fly.

### 3.1. 500 ảnh đã cắt vùng biển, có nhãn từ publisher

Nguồn: [Vietnamese License Plate OCR, topkek69, version 9](https://www.kaggle.com/datasets/topkek69/vietnamese-license-plate-ocr/versions/9). Metadata Kaggle ghi Apache 2.0; metadata và archive được giữ ngoài Git. Nguồn ảnh gốc trước publisher chưa được đối chiếu độc lập. Chỉ lấy nhóm ảnh thật `cropped/car_*.jpg` và `cropped/mb_*.jpg`; không lấy `generated/`.

Chọn trước suy luận: sắp theo SHA256 của `ParkingAI-PARK209-frozen-v1|filename`, lấy 250 ảnh ô tô và 250 xe máy, loại trùng biển chuẩn hóa. Nhãn lấy từ `labels/crop_labels.csv`; kiểm tra trực quan 20 nhãn đầu trước chạy. Chưa gán nhãn lại độc lập toàn bộ 500 ảnh.

| Phép đo | Đúng toàn biển | Cần sửa/nhập tay | Ý nghĩa |
|---|---:|---:|---|
| OCR trực tiếp trên vùng biển có sẵn — ô tô | 225/250 (90,0%) | 25/250 | Chất lượng đọc chữ khi đã có crop đúng |
| OCR trực tiếp trên vùng biển có sẵn — xe máy | 231/250 (92,4%) | 19/250 | Chất lượng đọc chữ khi đã có crop đúng |
| OCR trực tiếp — tổng | **456/500 (91,2%)** | **44/500 (8,8%)** | Không phải accuracy của website |
| Cả YOLO → OCR trên chính các ảnh crop | **64/500 (12,8%)** | **436/500 (87,2%)** | Đầu vào cắt sát; khác ảnh toàn xe, bộc lộ hạn chế của detector với loại đầu vào này |

CER của OCR trực tiếp là 2,5487%; CER cả pipeline trên crop là 84,6357%. Pipeline trên crop xe máy không đúng ảnh nào trong 250 mẫu; không được giấu nhóm này hoặc lấy số OCR trực tiếp thay cho số pipeline. Detection trên ảnh toàn xe **không được suy ra** từ tập crop.

### 3.2. Pilot 20 ảnh toàn xe từ một camera

Nguồn: [license-plate-dataset, raidendg, version 1](https://www.kaggle.com/datasets/raidendg/license-plate-dataset/versions/1). Metadata ghi MIT; mô tả cho phép nghiên cứu/thử nghiệm phi thương mại. Lần chạy này dùng cục bộ cho đồ án, không phân phối lại ảnh trong Git.

Chọn 20 tên ảnh đầu theo SHA256 của `parkingai-vn-cctv-v1|member` trước suy luận. Agent đọc biển và gán bounding box trên ảnh gốc 472×303, sau đó kiểm tra contact sheet crop trước chạy model. **Nhãn này chưa được con người kiểm tra độc lập**, vì vậy kết quả là pilot tạm thời. Có 18 biển khác nhau trong 20 frame; các frame cùng góc camera có tương quan.

| Chỉ số | Kết quả |
|---|---:|
| Tìm đúng biển tại IoU ≥ 0,5 | 20/20 |
| Vùng đánh dấu thừa so với nhãn | 9 |
| Detection precision / recall ở ngưỡng hiện tại | 20/29 = 68,97% / 20/20 = 100% |
| Đọc đúng toàn biển sau YOLO → OCR | 20/20 |
| Gợi ý cần sửa hoặc nhập tay | 0/20 |
| Thời gian cục bộ p50 / p95, gồm decode + pipeline | 0,656 / 0,794 giây |

Không gọi kết quả này là “100% chính xác biển Việt Nam”. Tập chưa có xe máy toàn cảnh, ca ban đêm, ảnh không có biển, nhiều camera hoặc điện thoại thật. Chưa đo tỷ lệ false-positive trên ảnh âm tính. Đây là precision/recall tại ngưỡng cố định, không phải mAP. Điểm model không phải xác suất đọc đúng đã hiệu chuẩn.

### 3.3. Cách chấm điểm và tái lập

`edge/evaluate_plates.py` kiểm tra tất cả hash/ID/nhãn trước suy luận, không loại lỗi khỏi mẫu số. So khớp biển chỉ bỏ dấu cách/chấm/gạch và chuyển chữ hoa; không đổi O↔0, I↔1 bằng đáp án. Detection ghép một-một ở IoU 0,5. CER là tổng edit distance chia tổng ký tự nhãn. Tỷ lệ cần sửa gồm không có gợi ý, gợi ý sai và lỗi nhận diện. OCR trên crop nhãn được báo cáo riêng.

```powershell
# Tải archive version 9 từ trang nguồn vào thư mục ngoài Git trước.
.venv/Scripts/python.exe edge/prepare_vn_benchmark.py backend/artifacts/phone-vn-acceptance/vn-ocr-v9.zip --output backend/artifacts/vn-reproduction
.venv/Scripts/python.exe edge/evaluate_plates.py backend/artifacts/vn-reproduction/manifest-crops.json --model backend/artifacts/vision/license-plate-yolov8n.onnx --output backend/artifacts/vn-reproduction/run-01
.venv/Scripts/python.exe -m pytest tests/test_plate_evaluation.py -q
```

Archive crop SHA-256: `34c5c11d6bd73e9f403a67d8b970c598a144d74a8e4e23689876e3caff9105de`. Manifest 500 mẫu: `4f4545a4f07b732aedc53ee7d9fc098da8adb40494dccc3584eb2188da763a64`. Manifest pilot 20 ảnh: `cca84266dbb4c290c111ed18a186808a8aa9e5aebd667c14e023440aed497887`. Không thay manifest sau khi thấy dự đoán; sửa nhãn phải tạo phiên bản mới và ghi lý do.

Kết quả từng ảnh và dữ liệu gốc: `backend/artifacts/phone-vn-acceptance/`. Mọi tỷ lệ chỉ mô tả mẫu đã đo. Tập huấn luyện model publisher không được công bố nên chưa xác minh được không trùng dữ liệu training. Khoảng Wilson trong JSON là mô tả có điều kiện, không thay cho lấy mẫu đại diện ngoài bãi.

## 4. Biên bản và phần còn thiếu

| Hạng mục | Trạng thái hiện tại |
|---|---|
| Công cụ chấm điểm, hash/provenance, chạy model thật | Đã có bằng chứng; xem kết quả từng nhóm ở trên |
| iQOO Neo 9 / Chrome trên thiết bị vật lý | **PENDING** — người dùng đã nêu máy, chưa gửi kết quả thao tác |
| iPhone / Safari trên thiết bị vật lý | **PENDING** — chưa có mẫu máy, iOS và kết quả thao tác |
| Kiểm tra độc lập nhãn pilot 20 ảnh | **PENDING** |
| Tuyên bố accuracy cho bãi thực | **NOT READY** — còn thiếu ảnh điện thoại/xe máy toàn cảnh/điều kiện khó và dữ liệu độc lập |

Đợt này đã có số đo OCR Việt Nam có giới hạn; chưa được đóng PARK-209 hoặc ghi “đã nghiệm thu điện thoại thật”. Khi có kết quả từ hai thiết bị, cập nhật mẫu biên bản ngoài Git, đối chiếu quan sát server trong thời hạn lưu ảnh, rồi chốt từng ca bằng PASS/FAIL/SKIP cùng lý do.
