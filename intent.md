# Intent — ParkingAI theo đề bài gốc

## Mẫu giao diện bắt buộc — 24/09/2026

Người dùng phản hồi bản triển khai chưa đúng và chỉ rõ `http://127.0.0.1:8790/?v=full-demo`. Mẫu này là căn cứ bố cục trực tiếp: cùng tỷ lệ panel, điều hướng, form gọn, bảng và responsive; không chỉ giữ màu xanh hoặc nhóm menu. Đang sửa ứng dụng React thật theo cấu trúc mẫu, bảo toàn API, quyền, nghiệp vụ và dữ liệu. Không sửa bản mẫu, không xin duyệt lại một thiết kế khác.

## Phê duyệt hiện hành — triển khai bản demo đã duyệt (23/09/2026)

Người dùng đã phê duyệt rõ: **“được hãy triển khai theo bản demo này”**. Bước duyệt trước đã hoàn tất; triển khai giao diện/luồng trong `frontend/prototypes/parking-simple` vào ứng dụng thật FastAPI/React. Phần “chỉ demo/chờ duyệt” bên dưới là lịch sử và không còn chặn công việc. Giữ một bãi, các chức năng lõi, Admin kế thừa Manager và quyền Staff, bảo toàn dữ liệu/phí/thu tiền/lịch sử. Khách đặt trước tùy chọn; nhận khách vãng lai vẫn là luồng cốt lõi.


## Đính chính hiện hành — xem demo trước khi triển khai (23/09/2026)

Người dùng làm rõ: **cần xem và duyệt demo trước khi triển khai**. Đợt sửa ứng dụng thật bên dưới xuất phát từ việc Codex hiểu sai yêu cầu ưu tiên đề bài; không phải phê duyệt thiết kế/triển khai mới. Hiện chỉ trình bày và chỉnh prototype theo phản hồi. Giữ các thay đổi mã thật đã có ở dạng nháp cục bộ, chưa commit/push/deploy; không tiếp tục backend hoặc gọi AI thật trước khi demo được duyệt. F01–F13 là danh sách đối chiếu cho thiết kế demo, không phải lý do bỏ qua bước duyệt.

Bản xem trước: `frontend/prototypes/parking-simple/index.html` / `http://127.0.0.1:8790/`. Phải nói rõ màn hình còn thiếu và chức năng đang mô phỏng. Kế hoạch/kết quả triển khai bên dưới là lịch sử và đã bị đính chính về phạm vi.

## Ưu tiên hiện hành — hoàn thành đề bài gốc (23/09/2026)

Người dùng xác nhận đề bài là tiêu chí nghiệm thu bắt buộc. Bản HTML ở `frontend/prototypes/parking-simple` chỉ dùng duyệt giao diện, không chứng minh hoàn thành backend, CSDL hoặc AI. Đợt này đối chiếu và hoàn thiện trên ứng dụng FastAPI/React hiện có, giữ một bãi cùng dữ liệu hiện hữu.

Thứ tự ưu tiên: xác thực/phân quyền quản lý–nhân viên; CRUD khu vực/chỗ/loại xe/giá; phương tiện, vào/ra, thời gian và phí; chỗ trống theo khu; tra cứu biển số/thời gian; vé tháng hoặc khách quen; lưu lượng/doanh thu/cao điểm; ba chức năng AI báo cáo ngày/tuần, hỏi đáp và gợi ý nhân sự; kiểm thử và minh chứng KT1/KT2/KT3/cuối kỳ. Admin kế thừa khả năng Manager, Customer là tác nhân bổ sung; không bỏ Staff khỏi yêu cầu lõi.

Tiêu chí hoàn thành: mỗi yêu cầu có mã chạy thật, đường thao tác đúng quyền và bằng chứng kiểm chứng; ghi tách test provider giả với nghiệm thu model thật, tách dữ liệu tổng hợp với dữ liệu thực. Không dựa vào số nút, tổng test hoặc demo mô phỏng để đánh dấu đủ đề.

Camera/OCR/CV, QR ngân hàng, portal/đặt chỗ là phần mở rộng sau nghiệm thu lõi. Giữ các chức năng đã có nhưng không thêm phạm vi cho chúng trong đợt này. Không xóa dữ liệu/guard, không đổi DB đang dùng; kiểm trên DB tổng hợp riêng. Không push/deploy trong đợt kiểm chứng local này.

Các mốc bên dưới là lịch sử; phần ưu tiên mới này có hiệu lực khi có khác biệt. Minh chứng mới sẽ được liên kết tại `docs/ORIGINAL_REQUIREMENTS.md`.

## Yêu cầu hiện hành — nâng cấp đồ án một bãi (15/09/2026)

Người dùng đã phê duyệt phương án ngày 15/09/2026 và cho phép triển khai. Phạm vi vẫn là **một bãi duy nhất phục vụ đồ án**: giữ đầy đủ lõi gốc trước, sau đó thêm QR nhận tiền, camera quét biển, computer vision, website khách mua vé giờ/ngày/tháng, đặt chỗ và thanh toán hóa đơn. Không cần tham vấn Claude. Triển khai theo các giai đoạn trong plan.md; phê duyệt không thay cho nghiệm thu hoặc giao dịch ngân hàng thật.

Mục tiêu: hai vai trò quản lý/nhân viên có hành trình khép kín từ cấu hình → nhận xe → tra cứu → tính phí/thu tiền → trả xe → báo cáo/AI; có vé tháng/khách quen, kiểm thử và minh chứng KT1/KT2/KT3/cuối kỳ. Giữ FastAPI/React và các nghiệp vụ đã có. Dùng bộ dữ liệu demo một bãi độc lập, không xóa bãi/lịch sử cũ hoặc bỏ guard để mở chức năng.

Điều kiện thành công: ma trận F01–F13 đạt nghiệm thu, quyền backend/UI/AI nhất quán, tiền/chỗ đúng khi thao tác lặp hoặc lỗi, số liệu AI đối chiếu được, hướng dẫn demo/cài mới có thể thực hiện. Đề xuất cụ thể và các chính sách giá/quá hạn **chưa triển khai** ở [PROPOSAL.md](docs/upgrade-2026-09-15/PROPOSAL.md).

Codex đã đối chiếu HEAD `3ef172e`; sau khi được duyệt đã triển khai nền một bãi và phần báo cáo/AI theo quyền, có UAT HTTP và kiểm tra khôi phục DB riêng. Xem [tiến độ triển khai](docs/upgrade-2026-09-15/IMPLEMENTATION.md). Nghiên cứu trước đó tham khảo JustPark, Q-Park, SKIDATA, Futech iParking, Parquery và tài liệu payOS/VietQR. [Nguồn thực tế](docs/upgrade-2026-09-15/REAL_WORLD_REFERENCES.md), [thiết kế E01–E08](docs/upgrade-2026-09-15/EXTENSION_PLAN.md). Không chờ Claude; lần tham vấn thất bại chỉ còn là [lịch sử](docs/upgrade-2026-09-15/DISCUSSION.md).

Lộ trình: P0–P3 hoàn thiện/nghiệm thu lõi F01–F13 → P4 portal/gói vé/đặt chỗ → P5 QR/hóa đơn/đối soát → P6 camera OCR → P7 CV ô đỗ → P8 nghiệm thu tích hợp. Phần mở rộng là mục tiêu chính thức giai đoạn sau, không bị loại bỏ vì độ khó cơ bản của đề. Mỗi giai đoạn phải giữ các kiểm thử lõi và bảo toàn dữ liệu/chứng từ.

Các phần phía dưới là bối cảnh và kết quả lịch sử; khi khác với yêu cầu 15/09, phần này được ưu tiên.

## Phạm vi hiện tại — đề bài gốc là căn cứ ưu tiên

Ngày 08/09/2026, người dùng yêu cầu bám sát đề **Hệ thống quản lý bãi đỗ xe có tích hợp AI**, mức cơ bản, một bãi có nhiều khu/vị trí. Hai vai trò nghiệp vụ chính là quản lý và nhân viên. Không phát triển tiếp nhiều bãi.

**Kết quả bắt buộc:** quản lý khu/vị trí/loại xe, phương tiện, vào/ra và thời gian gửi, tính phí, chỗ trống theo khu, tra cứu biển số/thời gian, vé tháng hoặc khách quen, thống kê lưu lượng/doanh thu/cao điểm. Ba chức năng AI chính là báo cáo ngày/tuần, hỏi đáp dữ liệu bãi xe và gợi ý nhân sự; có minh chứng sử dụng AI ở KT1/KT2/KT3/cuối kỳ và test tương ứng.

**Điều kiện thành công:** từng yêu cầu có đường thao tác đúng quyền trên bản nộp; dữ liệu AI do backend tổng hợp đúng bãi/kỳ, không tự tạo số liệu; nghiệm thu AI Engine thật phải ghi riêng với test mock. Camera nhận diện biển không thay phần AI báo cáo. Không lấy tổng số test hoặc số tính năng mở rộng để công bố phần trăm hoàn thành đề bài.

**Ràng buộc:** giữ FastAPI/React, SQLite/PostgreSQL và cấu trúc hiện tại; không xóa dữ liệu đang có, không nới guard để mở menu. QR chỉ mô phỏng, không tăng tài nguyên có phí. Credentials, model, ảnh và hồ sơ báo cáo Word ngoài Git. Người dùng cho phép bật Gemini hiện có, gửi thống kê tổng hợp bãi demo tới provider và lưu kết quả; không gửi biển số hoặc thông tin khách.

**Không phải trọng tâm:** camera, portal khách, QR, đặt chỗ, waitlist và quản lý đội xe là phần bổ sung; giữ phần đã chạy nhưng không mở rộng trước khi hoàn tất yêu cầu bắt buộc. Điện thoại thật còn chờ người dùng; không để hạng mục tùy chọn này thay thế ưu tiên AI phân tích.

**Trạng thái sau sửa:** bản `0b8c54c` đã phát hành và nghiệm thu đủ ba mục: menu Báo cáo/AI đúng quyền, lọc ngày và ba nhóm Gemini thật. Đã sửa diễn giải đơn vị giờ từ bằng chứng live, kiểm kỳ rỗng và nút sinh báo cáo. Chi tiết [CORE_AI_COMPLETION.md](docs/CORE_AI_COMPLETION.md). Cấu hình loại xe/bảng giá của manager và minh chứng toàn đề còn theo dõi riêng.

**Căn cứ và công việc:** [docs/ORIGINAL_REQUIREMENTS.md](docs/ORIGINAL_REQUIREMENTS.md), PARK-217/218/219 và đầu `plan.md`. Những mục dưới đây là intent lịch sử vòng 3, không phải yêu cầu mở rộng hiện tại.

## Problem / Opportunity
Release caaef39 đã lên website nhưng thiếu dữ liệu/tài khoản trình diễn, QR và OCR chưa bật. Vận hành nhiều bãi còn thiếu chốt ca theo bãi; audit v2 phân loại chung và chưa có request ID.

## Desired Outcome
Một modular monolith cho một đơn vị vận hành nhiều bãi, nghiệp vụ và phân quyền chính xác, demo online trên website hiện tại với QR mô phỏng và YOLO/OCR cần nhân viên xác nhận.

## Success Criteria
Kiểm thử hai bãi/bốn vai trò, SQLite và PostgreSQL thực; chứng từ/ca không lẫn bãi; giữ quote 120 giây, idempotency và quyền lịch sử. Phát hành sau backup/restore rehearsal, chạy UAT sau đăng nhập, báo cáo riêng những giới hạn OCR và thiết bị chưa kiểm chứng.

## Constraints / Non-goals
Không SaaS, microservices, ngân hàng thật, tự mở barrier; không tăng tài nguyên có phí. Gemini mặc định tắt. Giữ hồ sơ báo cáo, credentials, DB, model và ảnh ngoài Git. Không sửa/xóa dữ liệu đang có để seed demo.

## Risks / Assumptions
Website được chủ dự án chọn cho trình diễn đồ án. OCR CPU phải đo trên máy Fly 1GB; chưa có bộ đánh giá biển Việt Nam. Dữ liệu production phải kiểm tra lại trước thay đổi, không dựa vào thống kê cũ.

## References
Kế hoạch người dùng duyệt ngày 08/09/2026; plan.md; docs/REVIEW_ROUND2_RESOLUTION_2026-09-08.md. Nghiên cứu vòng 3 ghi riêng nguồn primary và giới hạn bằng chứng.
