# Phạm vi nộp đồ án theo đề bài gốc

**Kiểm lại mới nhất 24/09:** [Sửa tài khoản/camera và kiểm thử tổng thể](COMPREHENSIVE_RETEST_2026-09-24.md), [AI thật đã đối chiếu đủ sáu loại ca nhưng có ba lần 503](AI_LIVE_RETEST_2026-09-24.md), [OCR thật gồm các mẫu đọc sai/không đọc được](CAMERA_SCAN_DIAGNOSIS_2026-09-24.md). Các kết quả ngày23/09 bên dưới là mốc lịch sử, không thay cho kết quả mới; không coi model mock hay trang mở được là nghiệm thu đầy đủ.

**Triển khai demo đã duyệt:** xem [bản tích hợp FastAPI/React ngày23/09](DEMO_IMPLEMENTATION_2026-09-23.md). Các màn lõi được giữ và nhóm lại; bổ sung Customer tra phí/đặt trước, loại xe không biển số, camera tự động có điều kiện. Kết quả AI thật hiện còn503; không dùng bản mô phỏng thay nghiệm thu mô hình.

Cập nhật 23/09/2026: **đề bài gốc là tiêu chí nghiệm thu ưu tiên**; prototype giao diện và các phần mở rộng không thay thế chức năng thật. Đã rà ứng dụng tại HEAD `5922894` và sửa bổ sung trong working tree. Kết quả mới, ma trận F01–F13 và giới hạn nằm ở [CORE_ACCEPTANCE_2026-09-23.md](CORE_ACCEPTANCE_2026-09-23.md). Nghiệp vụ qua HTTP cục bộ đạt 79 bước; nghiệm thu AI thật đợt này còn mở vì Gemini trả 503 UNAVAILABLE. Không gọi kết quả live cũ là kết quả mới.

## 1. Mục tiêu bắt buộc

Một bãi đỗ xe gồm nhiều khu vực và vị trí, phục vụ hai vai trò nghiệp vụ chính: **quản lý** và **nhân viên bãi xe**. Hệ thống quản lý phương tiện, vé tháng/khách quen, lượt vào/ra, thời gian gửi, bảng giá, phí, chỗ trống và thống kê. Admin hiện có phục vụ cấu hình; tài khoản khách là phần bổ sung.

AI cốt lõi là **sinh báo cáo lưu lượng ngày/tuần, hỏi đáp dữ liệu bãi xe và gợi ý bố trí nhân sự theo cao điểm**. Backend tổng hợp số liệu từ CSDL; AI chỉ diễn giải dữ liệu được cung cấp. Phải phân biệt dữ liệu demo, thống kê thực, giả định về năng suất nhân viên và dữ liệu không đủ để kết luận.

Giữ FastAPI/React, SQLite cục bộ và PostgreSQL trên website. Gemini đã được tích hợp; phải kiểm trạng thái cấu hình và provider ở môi trường trình diễn. Ba nhóm AI có bằng chứng live lịch sử nhưng lần kiểm lại 23/09 chưa sinh được output. Không yêu cầu thay kiến trúc, huấn luyện model mới hoặc tăng gói Fly.

## 2. Ma trận yêu cầu – mã – kiểm thử – khoảng thiếu

“Có mã/test” chứng minh phần triển khai tương ứng, không có nghĩa toàn bộ hành trình đã được nghiệm thu trên website. Các đường dẫn mã và test dưới đây là file hiện có.

| Mục đề bài | Mã và bằng chứng | Điều còn phải bảo đảm ở bản nộp một bãi |
| --- | --- | --- |
| Đăng nhập, phân quyền quản lý/nhân viên | `backend/services/auth_service.py`, `backend/expansion/site_scope.py`; `tests/test_auth.py`, `tests/test_expansion_sites.py` | Hai vai trò thực hiện được phần việc của mình; không phải dùng admin thay quản lý hoặc bỏ guard để mở chức năng |
| Khu vực, vị trí, loại xe | `backend/routers/zone.py`, `parking_slot.py`, `vehicle_type.py`; `backend/expansion/site_router.py`; `tests/test_management_api.py`, `tests/test_zone_slot_integrity.py` | Manager CRUD loại xe/bảng giá đã được triển khai và kiểm lại HTTP trong DB một bãi; giữ guard quyền và dữ liệu legacy |
| Xe vào/ra, thời gian gửi | `backend/services/parking_service.py`, `backend/expansion/site_router.py`; `tests/test_session_lifecycle_integrity.py`, `tests/test_checkout_quote_contract.py` | Nhập biển thủ công phải hoàn tất được hành trình; OCR là lựa chọn hỗ trợ |
| Tính phí theo loại xe và thời gian | `ParkingService.calculate_fee`, `backend/routers/price_config.py`; `tests/test_fee.py`, `tests/test_price_config_api.py` | Hiển thị cách tính/phí trước trả xe; số tiền do server xác định, giữ xác nhận thu tiền |
| Chỗ trống theo khu vực | `ParkingService.get_available_slots_summary`, `backend/expansion/site_service.py`; `tests/test_slots.py`, `tests/test_expansion_sites.py` | Phân biệt chỗ có xe, chỗ bị giữ và chỗ có thể nhận xe; cập nhật sau vào/ra |
| Tra cứu theo biển số và thời gian | `ParkingService.search_sessions`; `backend/expansion/site_router.py` và `frontend/src/pages/Expansion/SitesWorkspace.jsx` | Đã có date_from/date_to tại API/UI, tính trọn ngày Việt Nam; kiểm thử ranh giới, phân trang và online đạt |
| Vé tháng hoặc khách quen | `backend/routers/monthly_pass.py`, `customer.py`, `backend/expansion/portal_router.py`; `tests/test_monthly_pass_api.py`, `tests/test_monthly_coverage_snapshot.py` | Demo vé còn hạn/hết hạn và phí tương ứng; thanh toán QR hoặc tự đăng ký của khách không phải điều kiện để chứng minh yêu cầu này |
| Lưu lượng, doanh thu, khung giờ cao điểm | `backend/services/report_service.py`, `backend/routers/report.py`, `backend/expansion/site_finance.py`; `tests/test_report_period_consistency.py` | Đã mở `/reports` theo capability/quyền bãi, thống kê ngày/7 ngày và tiền demo tách riêng; đối chiếu online với session/sổ thu đạt |
| AI báo cáo ngày/tuần | `AIService.generate_daily_report`, `generate_weekly_report`; `backend/routers/ai_report.py`; `tests/test_ai.py`, `tests/test_ai_integrity.py` | Đã nghiệm thu ngày/tuần bằng Gemini thật qua API v2 theo bãi; legacy giữ guard. Service mới: generate_scoped_analysis(kind=report) |
| AI hỏi đáp cao điểm/chỗ trống | `AIService.answer_question`, `ask_dashboard_question`; `tests/test_ai.py`, `tests/test_ai_integrity.py` | Đã mở menu và API đúng quyền; staff hỏi Gemini thật, câu trả lời khớp số lượt/cao điểm/chỗ trống có thời điểm riêng |
| AI gợi ý nhân sự | `AIService.suggest_staff_schedule`; `tests/test_ai.py`, `tests/test_ai_provider_fail_closed.py` | Đã nghiệm thu kind=staff bằng Gemini thật; phân biệt tổng cùng giờ của cả tuần, dữ liệu xe ra/năng suất còn thiếu. staff-plan quy tắc không thay phần này |
| Test cho vào/ra, phí, chỗ trống, AI | Các file test ở trên; `tests/conftest.py` chặn provider thật trong pytest | Giữ kiểm thử tự động; ghi riêng phiên chạy model thật, không gọi mock là kết quả live |
| AI trong SDLC: KT1/KT2/KT3/cuối kỳ | `docs/AI_SDLC.md`, `docs/EXPANSION_SDLC.md`, code/test/commit | Minh chứng chính phải bám nghiệp vụ và AI báo cáo. Phân biệt prompt tái lập với bản ghi prompt đã thực sự sử dụng; không tạo lại lịch sử như bằng chứng gốc |

## 3. Kết quả ba mục sửa ngày 09/09 — lịch sử

**READY cho ba mục người dùng yêu cầu sửa:** Gemini thật cho báo cáo ngày/tuần, hỏi đáp và nhân sự; Báo cáo/AI đúng quyền quản lý–nhân viên; lọc ngày vào trong lịch sử. Đã kiểm kỳ rỗng, retry, lịch sử và một lần sinh qua giao diện. Đọc kết quả live phát hiện lỗi đơn vị giờ, đã sửa prompt rồi nghiệm thu lại. [Biên bản](CORE_AI_COMPLETION.md) có bằng chứng và giới hạn.

Không xóa bãi cũ, không bỏ guard legacy. Nghiệm thu toàn bộ đề gốc và vận hành bãi thật chưa được chốt.

## 4. Công việc còn theo dõi — cập nhật 23/09

1. PARK-217 có bằng chứng đạt lịch sử; kiểm lại provider hiện tại còn mở do 503 UNAVAILABLE. Cần đủ ngày/tuần/hỏi đáp/nhân sự/kỳ rỗng và review nội dung trước khi chốt AI mới.
2. PARK-218: luồng manager cấu hình loại xe/bảng giá đã có, được kiểm lại trong HTTP 79 bước. Menu nghiệp vụ ưu tiên trước phần mở rộng; sửa chỗ đang giữ không được tính là nhận xe được. Không còn coi các mục này là thiếu triển khai.
3. PARK-219: đã cập nhật ma trận, code/test và minh chứng Markdown. Chưa chốt toàn đề trong phiên này khi AI thật chưa kiểm lại thành công; Word/slide cũ chưa xuất lại. Xem biên bản mới để phân biệt phần đạt cục bộ và phần còn mở.

## 5. Phần bổ sung và phần không phát triển tiếp

- Camera/YOLO: minh họa hỗ trợ nhập biển; không phải trọng tâm chấm ba chức năng AI phân tích.
- Portal khách, QR mô phỏng, đặt chỗ, danh sách chờ, quản lý nhóm xe: giữ phần đã có để giới thiệu nếu còn thời gian; chưa tiếp tục mở rộng trước khi hoàn tất mục bắt buộc.
- Không đưa nhiều bãi, video liên tục, ngân hàng thật, tự mở barie, GPU hoặc microservices thành yêu cầu của đồ án cơ bản.
- Tham khảo hệ thống lớn chỉ để học cách bảo vệ dữ liệu, tối ưu truy vấn và trình bày kết quả; không lấy độ phức tạp của chúng làm mục tiêu phát triển.

## 6. Kịch bản nghiệm thu theo đề

Đây là kịch bản bảo vệ. Bước nghiệp vụ đã có kiểm chứng HTTP cục bộ mới; không thay cho nghiệm thu trên website đã triển khai. Các bước AI thật phải kiểm lại khi provider hoạt động. Xem biên bản 23/09 ở đầu tài liệu.

1. Quản lý đăng nhập, xem/cấu hình khu vực, vị trí, loại xe và bảng giá đúng quyền.
2. Nhân viên nhập biển và nhận xe; kiểm chứng lượt vào, giờ vào và chỗ trống theo khu vực giảm đúng.
3. Tra cứu xe theo biển và khoảng thời gian; xem vị trí và thời gian gửi.
4. Xem phí trước trả xe, xác nhận thu, trả xe; thử lại không thu trùng và chỗ được giải phóng đúng.
5. Minh họa vé tháng còn hạn/hết hạn hoặc hồ sơ khách quen.
6. Mở thống kê ngày/tuần: lưu lượng, doanh thu, giờ cao điểm; đối chiếu vài bản ghi mẫu với số tổng hợp.
7. AI sinh báo cáo ngày và tuần từ dữ liệu của đúng bãi; nội dung nêu đúng kỳ và nguồn số liệu.
8. Hỏi “Khu A còn bao nhiêu chỗ?” và “Khung giờ nào đông nhất?”; so câu trả lời với số liệu server.
9. AI gợi ý bố trí nhân sự; nếu đề xuất số người phải nêu giả định năng suất, không trình bày giả định như số đo.
10. Thử dữ liệu rỗng/provider không khả dụng, trình bày test và minh chứng SDLC. Camera/QR có thể giới thiệu sau phần bắt buộc.

## 7. Bằng chứng lịch sử trước đợt sửa

Đã đọc các guard, route, màn hình và test nêu trên. Chạy lại `tests/test_ai.py`, `tests/test_ai_integrity.py`, `tests/test_ai_provider_fail_closed.py`, `tests/test_fee.py`, `tests/test_slots.py`, `tests/test_session_lifecycle_integrity.py`, `tests/test_report_period_consistency.py`: **167 passed**, 42,32 giây. AI dùng mock, DB riêng trong bộ test; không gọi Gemini hoặc ghi dữ liệu website. Log ở `backend/artifacts/original-spec-alignment/core-regression.log` ngoài Git.

Mốc đối chiếu08/09 chỉ điều chỉnh tài liệu; bản `038d6c9` sau đó đã sửa mã/cấu hình/schema và có UAT riêng tại CORE_AI_COMPLETION.md. Hoàn tất nghiệp vụ/AI trong ticket phải có kiểm thử và release gate mới trước khi kết luận đủ đề.
