# ParkingAI — vận hành bản trình diễn nhiều bãi

Phạm vi: một đơn vị, FastAPI/React modular monolith. Đây là bản đồ án dùng website hiện tại. QR tạo giao dịch mô phỏng, không chuyển tiền; Gemini tắt. Lịch sử do công cụ seed tạo được gắn `demo://synthetic-history/<namespace>`, phí bằng 0 và không sinh chứng từ thu.

## Sử dụng theo vai trò

- **Staff:** vào **Bãi xe**, chọn bãi được cấp quyền. Tab **Ca & chứng từ** cho mở ca, xem khoản mình thu và chốt theo số tiền thực đếm. Chỉ có một ca mở cho mỗi nhân viên; không nhận khoản của bãi khác vào ca đó. Nhận xe và xem báo phí/xác nhận xe ra tại màn hình nghiệp vụ.
- **Manager:** xem ca, chứng từ và tổng thu của bãi mình; chốt ca hoặc lập chứng từ hoàn có lý do. Tab **Cấu hình bãi** sửa khu/vị trí; các ràng buộc chỗ đang dùng hoặc có cam kết vẫn được kiểm tại server.
- **Admin:** quản trị toàn hệ thống, xem lịch sử chưa xác định bãi và audit. API v1 toàn hệ thống vẫn chặn staff/manager khi có nhiều bãi.
- **Customer:** cổng khách hiển thị xe đã xác minh, vị trí hiện tại, lịch sử được cấp quyền, vé và đơn. Trong **Đăng ký & QR**, chọn xe/gói rồi giả lập kết quả. Hoàn QR đi qua yêu cầu của khách và người duyệt, không dùng đường hoàn tiền quầy.

Tổng thu theo ngày thu/hoàn, trừ khoản hoàn và loại `method=demo`. Khoản chưa thuộc ca hiển thị riêng. `site_id` chứng từ do server suy từ nguồn bất biến của đơn hoặc lượt gửi; lịch sử thiếu căn cứ giữ null và chỉ admin xem qua workspace toàn hệ thống.

## Camera điện thoại và dự báo

Mở website HTTPS trên điện thoại, vào **Camera**, chọn bãi/camera, chụp hoặc tải JPEG/PNG. Sau OCR, xem ảnh toàn cảnh, crop và các ứng viên; sửa biển số rồi xác nhận để chuyển tới màn hình xử lý xe. OCR chỉ lưu nhận xét, không tự nhận/trả xe hoặc thu tiền. Điểm detector/OCR là điểm nội bộ, không phải accuracy đã kiểm chứng. Tối đa một ảnh đang xử lý; nếu nhận 429, chờ theo `Retry-After` rồi thử lại.

Đã thử viewport 390×844 trên Chrome. Chụp bằng điện thoại vật lý, biển Việt Nam và các điều kiện mưa/tối chưa được nghiệm thu. Không thay kết quả đó bằng screenshot hoặc ảnh biển nước ngoài.

Dự báo giữ mô hình hiện tại. Bảng so sánh naive, seasonal naive và trung bình cùng thứ/giờ dùng cùng cửa sổ rolling-origin; sai số và độ phủ khoảng chỉ tính từ quá khứ. Lịch sử tổng hợp phù hợp minh họa giao diện, không dùng để công bố hiệu quả dự báo thực tế.

## Model và runtime

Docker mặc định có thể build API gọn; cấu hình Fly bản đồ án đặt `INSTALL_VISION=1`. CPU một luồng, một worker. Model tải khi build, API không tải Python/model từ yêu cầu người dùng.

- [Nguồn model](https://huggingface.co/ml-debi/yolov8-license-plate-detection), revision `8062e8e86734e272c60fa9a819433327ebdb66d7`.
- SHA256 `85d236280a1301ad98907947d284951dd2b20c23a6786ff50f7e6a8ec515bd50`; kiểm khi tải và khi khởi tạo engine.
- Model card ghi MIT nhưng metadata ONNX ghi AGPL-3.0; nguồn dữ liệu huấn luyện không được nhà phát hành nêu rõ. Giữ provenance trong image, ghi nhận xung đột và chưa kết luận quyền phân phối thương mại. [Thông tin giấy phép Ultralytics](https://www.ultralytics.com/license).
- ONNX Runtime/RapidOCR/OpenCV/NumPy ghim tại `backend/requirements-vision.txt`. Model, ảnh đánh giá và output OCR không đưa vào Git.

Đo trực tiếp trên Fly hiện có: 1 CPU, khoảng 962 MiB RAM hệ điều hành; tiến trình benchmark đạt RSS đỉnh 693,6 MiB, khởi tạo 1,846 giây. Ảnh có vùng biển mất 1,719–3,361 giây; ảnh không phát hiện biển 0,173–0,205 giây. Chỉ hai ảnh ngoài Việt Nam, một trường hợp OCR đọc sai. Đây là benchmark tài nguyên, chưa thay phép thử API đồng thời sau phát hành hoặc đánh giá accuracy.

## Backup, migration và seed

Trước phát hành đã tạo dump PG17 của **public schema ParkingAI** ngay trên Fly; chuỗi kết nối chỉ dùng trong môi trường tiến trình trên server. Dump bao gồm dữ liệu, sequence, hàm và trigger; không bao gồm managed Auth/Storage/roles của Supabase. Gate recovery point của nhà cung cấp vẫn bắt buộc trong CD.

Dump 186.390 bytes, SHA256 `924e4ffca951b52d1c4d1f494635c1d2427234660d613dfcbf3cbc8241f1f747` đã phục hồi vào PostgreSQL 17 riêng: 36 bảng khớp số dòng, revision `20260908_01`. Clone tiếp theo nâng lên `20260908_02`, vượt deep readiness và seed/replay. Dump, manifest và credentials nằm trong `backend/artifacts/round3/private/` ignored.

Revision `20260908_02` thêm cột nullable/index/FK và trigger ca/chứng từ; không phân loại lại lịch sử hoặc đổi số tiền. Schema tương thích ứng dụng trước đó. Không chạy downgrade xóa cột tài chính.

Trên môi trường đã cấu hình DATABASE_URL, chạy từ `backend`:

```text
python -m expansion.showcase_seed --namespace demo260908
python -m expansion.showcase_seed --namespace demo260908 --apply --hashes /tmp/parkingai-demo-hashes.json --manifest /tmp/parkingai-demo-manifest.json
```

Lệnh đầu chỉ kiểm tra. Lệnh apply yêu cầu đủ bảy bcrypt hash được tạo cục bộ; công cụ khóa namespace trên PostgreSQL, kiểm tài khoản có sẵn, không reset DB hoặc ghi đè dữ liệu. Manifest ghi ID trước commit và trạng thái sau commit; chạy lại giữ nguyên ID, không nhân đôi. Không dùng `demo_server.py` hoặc script seed SQLite để ghi Supabase.

## Phát hành theo thứ tự

1. Lưu release/config và xác nhận backup/restore evidence, kiểm gate Supabase còn hiệu lực.
2. Stage secret `AI_ENABLED=false` vì secret Fly hiện có có ưu tiên hơn `fly.toml`. Các cờ đồ án/QR/YOLO đặt trong `fly.toml`; giữ 1 GB, không nâng gói.
3. Push commit backend trước, giữ frontend chưa cập nhật. CI/CD build và migration theo SHA cố định; Cloudflare có thể build frontend cũ an toàn.
4. Sau `/ready`, `/` release ID và API mới đạt, push frontend. Chờ CI/CD và kiểm bundle website/final SHA, CORS, banner đồ án và các tài khoản.
5. Seed namespace, lưu manifest riêng, chạy UAT sau đăng nhập và kiểm tải OCR/API. Ghi rõ lỗi còn lại trong release gate.

Cloudflare Web Analytics mặc định không cần cho đồ án. Nếu dashboard đang tự chèn beacon, tắt automatic setup cho hostname tại Cloudflare; giữ nguyên CSP. Chỉnh mã frontend không gỡ được script do nhà cung cấp chèn sau build. [Hướng dẫn Cloudflare](https://developers.cloudflare.com/web-analytics/get-started/).

## Tra lỗi và rollback

Response có `X-Request-ID`; cung cấp mã đó khi báo lỗi. Admin lọc audit bằng tham số `request_id`, hoặc tìm log JSON `http_request`/`unhandled_request_error` cùng ID. Log ghi route template, status, thời gian và loại lỗi; không ghi body, JWT, mật khẩu, ảnh hoặc prompt. Request ID không phải khóa idempotency và không dùng để quyết định đã thu tiền.

Nếu bản mới lỗi, ưu tiên deploy image/SHA trước đó và khôi phục cấu hình trước phát hành; database giữ schema additive và dữ liệu mới. Frontend Cloudflare rollback deployment tương ứng. Phục hồi DB chỉ theo runbook trên đích riêng đã xác minh, đối chiếu chứng từ phát sinh trước khi chuyển; không chạy restore đè, reset hoặc xóa dữ liệu để làm mất lỗi. Công cụ tạo demo không có chức năng xóa hàng loạt.
