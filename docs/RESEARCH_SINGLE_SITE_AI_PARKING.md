# ParkingAI — Tham khảo hệ thống AI parking để tối ưu đồ án một bãi

Ngày truy cập nguồn: **08/09/2026**. Baseline mã ParkingAI khi khảo sát: `8182c3fe152514870bdc988d2c241b27bdfe7c78`.

Phạm vi hiện tại là **một bãi để trình diễn và nộp đồ án**: FastAPI/React, PostgreSQL/SQLite, Fly 1 CPU/1 GB, điện thoại chụp hoặc tải ảnh, QR mô phỏng, Gemini tắt. Tài liệu này ghi kết quả nghiên cứu và đề xuất; **không xác nhận các đề xuất đã được triển khai hoặc phát hành**. Kết quả triển khai phải đối chiếu commit và bằng chứng kiểm thử riêng. Phạm vi nhiều bãi trong `REVIEW_ROUND3_RESEARCH.md` là lịch sử, không phải yêu cầu mở rộng hiện tại.

## 1. Kết luận áp dụng

Nên tối ưu các luồng đã có trước khi thêm model hoặc hạ tầng: tra chỗ trống ít truy vấn hơn, danh sách nhận diện không tải dữ liệu ảnh không dùng, và ghép các đoạn chữ biển số theo hình học thay vì chia tọa độ Y thành các dải cố định. Đây là ba cải tiến nhỏ, có thể đo và giải thích được khi bảo vệ đồ án.

Giữ quy trình **chụp → phát hiện vùng biển → đọc chữ → nhân viên kiểm tra/sửa → chuyển sang nghiệp vụ**. Việc xe vào, xe ra và thu tiền vẫn do các dịch vụ nghiệp vụ kiểm quyền, giữ chỗ và transaction quyết định. Số chỗ có thể nhận xe phải lấy từ trạng thái gửi xe/đặt chỗ trong CSDL; số xe nhìn thấy trong một ảnh không đủ thay thế dữ liệu đó.

## 2. Bảy hệ thống/dự án đã đối chiếu

Chỉ dùng nguồn do nhà cung cấp hoặc tác giả dự án công bố. Các bài sản phẩm chứng minh họ mô tả một khả năng, không chứng minh accuracy độc lập hoặc SLA cho cấu hình ParkingAI. Không lấy số camera, khách hàng, tốc độ hoặc doanh thu quảng bá làm benchmark của đồ án.

### 2.1. Ba hệ thống thương mại

| Nguồn chính chủ | Khả năng được nguồn mô tả | Quyết định cho ParkingAI |
|---|---|---|
| **Metropolis** — [Engineering: giám sát sự kiện từ thiết bị](https://www.metropolis.io/blog/serverless-data-pipeline-for-near-real-time-monitoring-on-billions-of-edge-events); [cách ứng dụng computer vision](https://www.metropolis.io/blog/engineering-the-future-of-machine-learning) | Computer vision liên kết xe vào/ra với thời gian gửi. Bài engineering mô tả log sự kiện, dữ liệu đã chuẩn hóa và tập dữ liệu nhỏ phục vụ dashboard; dashboard giám sát có độ trễ mục tiêu 15 phút. | **ADAPT:** sự kiện có cấu trúc, request/observation ID và màn hình lịch sử gọn. Chỉ đọc trường cần hiển thị. **KEEP:** nhân viên xác nhận và QR mô phỏng. **REJECT:** bê AWS/Snowflake hoặc cơ chế tự thu tiền vào đồ án. Độ trễ dashboard giám sát của họ không phải độ trễ chấp nhận được cho thao tác nhận xe của mình. |
| **SKIDATA** — [AI-Based Mobility](https://www.skidata.com/en-ie/skidata-blog/ai-based-mobility); [LPR trong vận hành](https://www.skidata.com/en-ie/skidata-blog/streamline-parking-operations-lpr) | Mô tả nhận diện biển/đặc điểm xe, đếm xe và theo dõi video; LPR hỗ trợ tra cứu và dữ liệu sử dụng bãi. Các tuyên bố sửa biển tự động/đếm chính xác hơn không kèm tập đo Việt Nam trong nguồn đã đọc. | **ADAPT:** trình bày rõ biển, xe và lượt gửi liên quan; hiển thị chỗ trống dễ hiểu. **KEEP:** phân biệt chỗ vật lý trống với chỗ được phép nhận xe. **FUTURE:** đối soát camera đếm xe khi có camera cố định và tập đo. **REJECT:** tự sửa O/0 hoặc ghép xe gần đúng rồi tính phí khi chưa có bằng chứng. Không triển khai lại nhiều bãi. |
| **Flash Vision** — [AI-enabled LPR camera](https://www.flashparking.com/vision-2/) | Mô tả xử lý tại thiết bị, hai cảm biến và hai loại chiếu sáng; đọc biển và đặc điểm xe. Nguồn nêu dữ liệu huấn luyện xe/biển Bắc Mỹ, gồm ký tự xếp chồng. | **ADAPT:** hướng dẫn chụp đủ sáng, giữ vùng xe quanh biển; kiểm riêng ảnh một dòng, hai dòng, nghiêng và chói. **FUTURE:** camera/edge chuyên dụng. **REJECT:** dùng tuyên bố độ chính xác của họ để suy ra kết quả biển Việt Nam hoặc điện thoại. Không mua thiết bị cho phạm vi đồ án. |

Các sản phẩm thương mại trên không cung cấp mã pipeline trong các trang đã đọc, vì vậy không có revision hoặc giấy phép mã để sử dụng lại. Bài học rút ra là cách tổ chức luồng và bằng chứng; không sao chép mã, giao diện hay thương hiệu.

### 2.2. Bốn dự án GitHub/tài liệu kỹ thuật

Metadata được đọc từ GitHub API công khai; giấy phép được đối chiếu file `LICENSE` tại đúng SHA. Nhánh khảo sát và release mới nhất được ghi riêng: đọc nhánh phát triển không đồng nghĩa đã kiểm thử release đó. Mọi mốc dưới đây là ảnh chụp tại ngày truy cập.

| Dự án | Revision đã đọc | Release hiển thị tại ngày truy cập | Giấy phép mã |
|---|---|---|---|
| [fast-alpr](https://github.com/ankandrew/fast-alpr) | `master`, `c5a94706f175590b2bc09aa86f46182d4c267fae` — 16/03/2026 UTC | `v0.4.0` — 15/03/2026 UTC | [MIT](https://github.com/ankandrew/fast-alpr/blob/c5a94706f175590b2bc09aa86f46182d4c267fae/LICENSE) |
| [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr) | `master`, `9ce7a5b64a939aa421c243b331d42e6bc25ffd44` — 14/03/2026 UTC | `v1.1.0` — 14/03/2026 UTC | [MIT](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/LICENSE) |
| [Frigate](https://github.com/blakeblackshear/frigate) | `dev`, `77a66e75c61862b048a07c1295877f4b31343504` — 06/09/2026 UTC | `v0.17.2` — 28/06/2026 UTC | [MIT](https://github.com/blakeblackshear/frigate/blob/77a66e75c61862b048a07c1295877f4b31343504/LICENSE) |
| [Ultralytics](https://github.com/ultralytics/ultralytics) | `main`, `7066defb44651ae88f165c711a34d47a363e2a29` — 08/09/2026 UTC | `v8.4.143` — 07/09/2026 UTC | [AGPL-3.0](https://github.com/ultralytics/ultralytics/blob/7066defb44651ae88f165c711a34d47a363e2a29/LICENSE) |

**fast-alpr.** Trong [`ALPR.predict`](https://github.com/ankandrew/fast-alpr/blob/c5a94706f175590b2bc09aa86f46182d4c267fae/fast_alpr/alpr.py#L119), detector tìm box, chương trình cắt ảnh rồi gọi OCR; kết quả giữ hai phần detection/OCR. [`test_alpr.py`](https://github.com/ankandrew/fast-alpr/blob/c5a94706f175590b2bc09aa86f46182d4c267fae/test/test_alpr.py) có kiểm biển, tọa độ box và miền confidence. **KEEP:** hai bước độc lập và ảnh crop để nhân viên đối chiếu. **ADAPT:** test lỗi detector khác lỗi OCR; lỗi bước nào phải thấy được. **FUTURE:** benchmark model thay thế sau khi ghim nguồn gốc, dữ liệu và tài nguyên. Không cần cài thư viện chỉ để đạt cùng cấu trúc mà ParkingAI đã có.

**fast-plate-ocr.** [README tại SHA khảo sát](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/README.md) nêu đầu vào OCR là ảnh đã cắt biển; bảng tốc độ dùng NVIDIA RTX 3090. [`plate_recognizer.py`](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/fast_plate_ocr/inference/plate_recognizer.py) hỗ trợ ONNX model/config riêng, nhận confidence từng ký tự khi yêu cầu. **ADAPT có điều kiện:** chế độ người dùng chủ động chọn “ảnh đã cắt biển” nếu sau này bổ sung; phải ghi rõ nguồn crop và đường suy luận. **REJECT:** tự chuyển ảnh toàn cảnh sang OCR khi YOLO thất bại hoặc lấy kết quả benchmark GPU làm thời gian CPU 1 GB. Chưa có phép đo dự án này trên tập Việt Nam của ParkingAI.

**Frigate.** [Tài liệu LPR](https://docs.frigate.video/configuration/license_plate_recognition/) và [bản tài liệu đã ghim](https://github.com/blakeblackshear/frigate/blob/77a66e75c61862b048a07c1295877f4b31343504/docs/docs/configuration/license_plate_recognition.md) tách ngưỡng detection/recognition, ảnh debug và các trường hợp nhiều dòng. Tài liệu yêu cầu tối thiểu 4 GB RAM, CPU có AVX/AVX2. **ADAPT:** phân tích crop, tách điểm từng bước và kiểm thứ tự các đoạn chữ; thay đổi xử lý ảnh phải được đo riêng. **REJECT:** cài nguyên Frigate vào máy Fly 1 GB. **FUTURE:** video/đồng thuận nhiều frame khi có thiết bị phù hợp. Không chuyển fuzzy matching thành quyền vào bãi hoặc thao tác thu tiền.

**Ultralytics ParkingManagement.** [`parking_management.py`](https://github.com/ultralytics/ultralytics/blob/7066defb44651ae88f165c711a34d47a363e2a29/ultralytics/solutions/parking_management.py#L242) duyệt polygon chỗ đỗ, kiểm tâm box vật thể bằng `pointPolygonTest`, rồi trả số chỗ có xe/chỗ trống theo ảnh. [API reference](https://docs.ultralytics.com/reference/solutions/parking_management) mô tả các đầu ra này. **FUTURE:** lớp quan sát phụ để phát hiện lệch giữa ảnh và sổ gửi xe. **KEEP:** availability CSDL làm nguồn ra quyết định vì còn reservation, loại xe và trạng thái chỗ. **REJECT:** coi demo đếm polygon là toàn bộ hệ thống quản lý bãi hoặc nhận xe dựa trên ảnh đơn. Chưa sao chép mã hoặc thay weight; giấy phép framework không tự xác nhận quyền sử dụng mọi model/dataset bên ngoài.

## 3. Đối chiếu với ba điểm tối ưu trong mã hiện tại

Đây là kết luận từ mã ParkingAI ở baseline, không phải mô tả SQL/ORM nội bộ của Metropolis, SKIDATA hay Flash. Các nguồn bên ngoài cung cấp nhu cầu sản phẩm và cách phân ranh giới; thay đổi cụ thể dưới đây cần được chứng minh bằng regression của ParkingAI.

| Ưu tiên | Bằng chứng baseline | Phương án vừa sức đồ án | Điều kiện kiểm chứng |
|---|---|---|---|
| **1 — Tra chỗ trống** | `backend/expansion/site_service.py:47`, `availability()` gọi `admission_allowed(..., lock=False)` trong vòng lặp các chỗ trống. | Nạp các reservation còn hiệu lực cho cả bãi theo tập hợp rồi tính availability; tái sử dụng cùng ngữ nghĩa thời gian/giữ chỗ. Giữ kiểm tra có khóa trong luồng nhận xe, vì dữ liệu hiển thị có thể đổi trước lúc bấm xác nhận. | Đo số câu SQL với 1/10/100 chỗ để chứng minh không tăng theo từng chỗ; kiểm occupied, disabled, reserved, reservation hết hạn, biên thời gian và chỗ bãi khác. So payload trước/sau. Không dùng cache lâu để che N+1. |
| **2 — Lịch sử nhận diện** | `backend/expansion/vision_router.py:205`, danh sách lấy toàn entity `VisionObservation`; BLOB ảnh không cần cho dữ liệu lịch sử hiển thị. | Chỉ nạp các cột phục vụ serializer; ảnh tiếp tục đi qua endpoint riêng có guard, quota/retention như hiện tại. Tránh lazy-load ảnh trở lại khi serialize. | SQL list không chọn cột ảnh; số query không phát sinh theo số item; JSON/ảnh endpoint và phân quyền giữ nguyên; thử hết hạn/xóa ảnh trong lúc đọc. Đo payload truy vấn và bộ nhớ nếu có thể, không suy từ kích thước JSON. |
| **3 — Thứ tự chữ trên biển** | `backend/expansion/vision_service.py:200`, sort theo `round(min_y / 10)` rồi X. Chia dải Y cố định có nguy cơ đổi thứ tự các đoạn cùng dòng khi nghiêng hoặc thay độ phân giải. | Tái hiện bằng polygon OCR cố định trước; nhóm theo hình học và kích thước chữ, rồi đọc trái→phải trong từng dòng, trên→dưới giữa các dòng. Không đổi ký tự dựa vào biển đã biết. | Test một dòng nghiêng hai chiều, hai dòng, đoạn lẻ, khác tỷ lệ ảnh và thứ tự detector trả về. Chạy lại tập đóng băng; công bố đúng toàn biển/CER trước-sau và mọi nhóm giảm chất lượng. Giữ cách cũ nếu chưa có bằng chứng cải thiện đủ rõ. |

Giảm SQL hoặc BLOB là cải tiến tài nguyên có thể đo trực tiếp; không mặc định gán một tỷ lệ tăng tốc khi chưa đo độ trễ. Sửa thứ tự chữ cũng không chứng minh detector đã tốt hơn.

## 4. Những gì nên giữ và hướng mở rộng có điều kiện

| Quyết định | Phạm vi |
|---|---|
| **KEEP** | Một bãi; monolith có module; model/runtime ghim checksum; một ảnh suy luận đồng thời; giới hạn ảnh; nhập biển thủ công; nhân viên xác nhận; QR mô phỏng; Gemini tắt; dữ liệu ảnh/model/credentials ngoài Git. |
| **ADAPT tiếp theo** | Thống kê kết quả duyệt: giữ nguyên gợi ý, sửa gợi ý, không có gợi ý nên nhập tay, từ chối ảnh. Tính theo các observation đã được duyệt và ghi rõ mẫu số; không coi observation chưa duyệt là đúng. Dùng lại trường đã có trước khi thêm schema. Metadata vận hành không chứa ảnh, mật khẩu, JWT hoặc toàn bộ prompt. |
| **ADAPT có điều kiện** | Chế độ OCR ảnh crop do người dùng chủ động chọn, có nhãn đường xử lý và bộ test âm tính riêng. Đề xuất này chưa là yêu cầu triển khai ngay: có thể ưu tiên hướng dẫn chụp toàn xe trước để giữ hợp đồng đơn giản. Không lặng lẽ chạy OCR toàn ảnh khi detector không tìm thấy biển. |
| **FUTURE** | Model OCR chuyên biển Việt Nam, camera cố định/occupancy, nhiều frame, cảnh báo sai lệch ảnh–sổ gửi xe. Chỉ mở sau khi có tập đo hợp lệ, nguồn model, baseline và giới hạn tài nguyên rõ ràng. |
| **REJECT cho đồ án này** | Nhiều bãi, nhận diện mặt người, barrier tự mở, thanh toán thật, GPU/gói có phí, NVR đầy đủ, message broker/data warehouse chỉ để giống doanh nghiệp. |

Telemetry nhân viên sửa biển là bài học thiết kế đề xuất cho ParkingAI, không phải tính năng đã xác nhận trong cả ba sản phẩm thương mại. Dữ liệu sửa chỉ trở thành nhãn đánh giá/huấn luyện sau khi kiểm tra chất lượng và quyền sử dụng; không tự coi mọi thao tác nhân viên là đáp án chính xác.

## 5. Nền đánh giá hiện có và giới hạn kết luận

[PHONE_VN_ACCEPTANCE.md](PHONE_VN_ACCEPTANCE.md) ghi phép đo đã thực hiện trước đợt nghiên cứu này: OCR trên 500 crop có nhãn đúng 456/500 (91,2%); cả YOLO→OCR trên cùng đầu vào cắt sát chỉ đúng 64/500 (12,8%). Hai con số đo hai đường đầu vào khác nhau, không được gọi 91,2% là accuracy website. Pilot 20 frame toàn xe có nhãn do agent gán, chưa được người kiểm tra độc lập; không đại diện mọi biển Việt Nam.

Tối ưu lần này phải giữ manifest và mẫu số, so cùng đầu vào/phiên bản runtime, tách ô tô/xe máy và một dòng/hai dòng khi có nhãn phù hợp. Nếu dùng tập cũ để lựa chọn thuật toán thì nó trở thành tập phát triển; kết luận khả năng tổng quát cần tập kiểm tra mới chưa dùng để chỉnh. Không loại ảnh lỗi hoặc không nhận ra khỏi báo cáo.

Nghiệm thu iQOO Neo 9/iPhone vẫn cần thao tác thiết bị thật theo hướng dẫn. Nghiên cứu nguồn, test unit hoặc viewport mobile không thay thế bằng chứng mở camera, chọn ảnh, tải ảnh, sửa biển và chuyển đúng màn hình trên điện thoại.

## 6. Cách nghiên cứu và độ tin cậy

Đã đọc tài liệu sản phẩm, repository README, metadata release/commit/license; kiểm tra đoạn pipeline FastALPR, inference FastPlateOCR, tài liệu Frigate và thuật toán polygon Ultralytics tại SHA nêu trên. Đã đọc các assertion/test liên quan trong FastALPR và chữ ký test nguồn ảnh của FastPlateOCR. **Không chạy test bên ngoài, không benchmark các model tham khảo, không cài dependency, không tải model/ảnh/dataset và không thay đổi website trong phần nghiên cứu này.**

Có bảy hệ thống/dự án làm nguồn chính; nhiều liên kết trong cùng hàng chỉ để đối chiếu claim, mã và provenance của cùng nguồn. Không chọn theo số stars. Giấy phép mã được ghi lại để sàng lọc ban đầu; trước khi thay engine/weights phải kiểm riêng đúng artifact được dùng. Các kết luận **ADAPT/KEEP/FUTURE/REJECT** là đánh giá phù hợp với phạm vi một bãi và tài nguyên hiện tại của ParkingAI.
