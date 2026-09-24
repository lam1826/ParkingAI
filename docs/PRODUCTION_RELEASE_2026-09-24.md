# Phát hành ParkingAI ngày 24/09/2026

Trạng thái: **NOT READY — backend đã phát hành và xác minh; đang phát hành/kiểm giao diện.**

Người dùng yêu cầu đưa bản ứng dụng mới lên Fly.io thay bản cũ và đã xác nhận riêng **cho phép commit/push mã nguồn và test lên repository GitHub công khai** sau yêu cầu của bộ xét duyệt tự động. DB, mật khẩu, API key và bộ nhớ riêng không được đưa lên GitHub. Chặn xuất bản ban đầu đã được giải quyết bằng sự đồng ý rõ ràng, không đi đường khác để vượt chặn.

## Đích và dữ liệu được giữ

- Backend Fly: `parkingai-api-lam1826`, region `sin`, API `https://api.parkingai.am`.
- Frontend Cloudflare Pages: `https://parkingai.am`, Git integration `main`, API build URL `https://api.parkingai.am`, bãi hiển thị ID2.
- Repository: `lam1826/ParkingAI`, công khai. Baseline trước phát hành `5922894d18e6d991b3ab01470c9a6562d453e5b3`; backend đã push `2e73887bbd51c68b413a39adecf60bf0abd5820a`.
- Backend baseline: release `9c6aa58f9414b532e8c6dfa75e90bdee02c0911c`, schema `20260916_07`. Backend mới `2e73887bbd51c68b413a39adecf60bf0abd5820a` đã lên production, schema `20260923_09`.
- Image trước thay đổi: `registry.fly.io/parkingai-api-lam1826:deployment-01M2MAC4RZPQ3GNV89G93FW3HR`. Metadata release lưu trong artifact cục bộ.
- Probe chỉ đọc trên Fly xác nhận deep readiness: 11 tài khoản, 4 vai trò, 3 bãi, 5 khu, 32 vị trí, 22 phương tiện, 2.253 lượt gửi (1 active, 2.252 completed), 6 thanh toán, 3 khách, 3 vé tháng, 0 ảnh camera. Không đưa dữ liệu khách hoặc credential vào báo cáo; không reset/seed DB production từ DB demo.

## Gói đã chuẩn bị

1. Commit backend trước: 62 file gồm API/migration08–09/test và cấu hình vận hành. Hai migration bổ sung bảng/cột/guard; không xóa lịch sử. Tắt `PARKINGAI_SHOWCASE_MODE` và `DEMO_PAYMENTS_ENABLED`; giữ thu tiền tại quầy. Online cần cấu hình nhà cung cấp thật, không thay QR mô phỏng thành xác nhận tiền thật.
2. Chờ CI với PostgreSQL16, cổng sao lưu Supabase và CD backend đạt. Cổng phục hồi yêu cầu PITR hoặc backup hoàn tất trong36giờ; không bỏ qua để triển khai.
3. Sau khi API/schema mới sẵn sàng mới commit/push giao diện mới. Cách này giữ Pages không phát giao diện mới trước backend. Toàn bộ thay đổi vẫn đi qua pipeline hiện có.
4. Kiểm đúng SHA, `/ready`, CORS, frontend bundle, đăng nhập/phân quyền và camera sau phát hành; đối chiếu dữ liệu trước/sau. Không gọi các ca chưa chạy là đạt.

## Kiểm chứng đã thực hiện

- 72/72 test preflight PostgreSQL contract, migration luồng mới, camera passage/retention và demo server; 18/18 test cấu hình sau thêm assertion cấm thanh toán/showcase mô phỏng trên Fly.
- Frontend production build thành công với API URL thật, ghi ra thư mục artifact riêng, không thay bundle demo cục bộ. Kiểm lại frontend293/293 (0 skip), lint đạt.
- 62 file backend đã stage; kiểm đường dẫn cấm và mẫu secret không phát hiện DB, `.env`, artifact, bộ nhớ riêng hoặc token thật. Không phải cam kết tuyệt đối thay cho review; danh sách file đã được kiểm.
- [CI backend](https://github.com/lam1826/ParkingAI/actions/runs/35961260578) đạt: 1.997 backend pass/28 skip/125 warning trên Linux; 18 PostgreSQL integration pass riêng sau Alembic09; 326 Windows release-safety pass/1 skip; OCR Docker resource gate đạt. Backend CI chỉ cài dependency cơ bản nên một số test runtime thị giác tùy chọn bị skip, cùng các điều kiện nền tảng/PG. Không cộng các nhóm chồng lặp thành số ca duy nhất. Frontend cũ ở phase1 đạt221; frontend mới cục bộ293/lint/build đạt.
- Kết nối SSH agent Fly trên Windows thất bại trước khi chạy lệnh; probe chỉ đọc sau đó thành công qua Machines API. Không thay cấu hình bảo mật để kết nối.
- [CD backend](https://github.com/lam1826/ParkingAI/actions/runs/35962141541) đạt: backup Supabase, deploy/migration, đúng SHA, readiness và CORS. Probe sau release xác nhận deep readiness/schema09, showcase=false/demo_payments=false; toàn bộ số lượng và trạng thái lượt trong baseline không đổi.
- Probe production chỉ đọc ban đầu dùng kỳ vọng một bãi đạt12/16, giữ nguyên bằng chứng lỗi: Manager/Staff bị403 tại API v1 toàn hệ thống vì DB thực tế có3bãi. Đối chiếu `system_router.legacy_workspace_allowed` xác nhận đây là ranh giới quyền hiện hữu. Probe theo đúng fixture3bãi đạt29/29 (hồ sơ/quyền/các API bãi2); thêm OCR status đạt30/30. Không đổi quyền để pass. Manager/Staff hiện dùng nghiệp vụ bãi được giao; các danh mục toàn hệ thống vẫn thuộc Admin khi DB có nhiều bãi. Chưa chuyển đổi DB về duy nhất một bãi.
- Engine `yolo_rapidocr` báo available và có camera active cho hai hướng. Đây là kiểm cấu hình, không phải nghiệm thu độ chính xác camera vật lý.

## Phục hồi

Ghi lại image/SHA trước thay đổi và giữ recovery gate trước migration. Migration08/09 chỉ cho tiến lên; không gọi downgrade để xóa bảng có lịch sử. Runtime health của backend cũ kiểm hợp đồng catalog thay vì đòi schema revision bằng tuyệt đối, nên được thiết kế cho giai đoạn schema bổ sung. Release gate của image cũ vẫn đòi revision07: **không chạy mù lệnh deploy/migration cũ sau khi DB đã lên09**. Khi cần phục hồi, dùng image tương thích schema đang có hoặc bản sửa tiến lên; việc quay image cũ phải xác minh tương thích dữ liệu và không chạy lại migration cũ. Frontend có thể quay về production deployment trước qua Pages trong lúc backend mới vẫn giữ API cũ.

Fly chạy `release_command` trước khi thay máy; lỗi lệnh này dừng deployment. Xem [tài liệu Fly](https://fly.io/docs/reference/configuration/). Hướng dẫn vận hành sẵn có: [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).

Artifact riêng: `backend/artifacts/release-20260924/`. Token chỉ được dùng qua credential helper/Fly CLI; không lưu nội dung credential trong tài liệu hoặc Git.
