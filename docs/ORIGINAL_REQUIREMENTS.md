# Phạm vi nộp đồ án theo đề bài gốc

Ngày đối chiếu: 08/09/2026. Mã ứng dụng đã kiểm tra: `3afc56c`; tài liệu trước điều chỉnh: `fd6de30`. Yêu cầu người dùng nhắc lại trong cuộc trao đổi là căn cứ ưu tiên, cao hơn các đề xuất mở rộng trước đó.

## 1. Mục tiêu bắt buộc

Một bãi đỗ xe gồm nhiều khu vực và vị trí, phục vụ hai vai trò nghiệp vụ chính: **quản lý** và **nhân viên bãi xe**. Hệ thống quản lý phương tiện, vé tháng/khách quen, lượt vào/ra, thời gian gửi, bảng giá, phí, chỗ trống và thống kê. Admin hiện có phục vụ cấu hình; tài khoản khách là phần bổ sung.

AI cốt lõi là **sinh báo cáo lưu lượng ngày/tuần, hỏi đáp dữ liệu bãi xe và gợi ý bố trí nhân sự theo cao điểm**. Backend tổng hợp số liệu từ CSDL; AI chỉ diễn giải dữ liệu được cung cấp. Phải phân biệt dữ liệu demo, thống kê thực, giả định về năng suất nhân viên và dữ liệu không đủ để kết luận.

Giữ FastAPI/React, SQLite cho chạy cục bộ và PostgreSQL trên website. Dùng tích hợp AI Engine theo đề, không yêu cầu thay kiến trúc, huấn luyện model mới hoặc tăng gói Fly. Quyết định giữ Gemini tắt trước đó vẫn là trạng thái triển khai hiện tại; đây là hạng mục cần giải quyết để nghiệm thu AI, không phải lý do bỏ ba yêu cầu AI khỏi bản nộp.

## 2. Ma trận yêu cầu – mã – kiểm thử – khoảng thiếu

“Có mã/test” chứng minh phần triển khai tương ứng, không có nghĩa toàn bộ hành trình đã được nghiệm thu trên website. Các đường dẫn mã và test dưới đây là file hiện có.

| Mục đề bài | Mã và bằng chứng | Điều còn phải bảo đảm ở bản nộp một bãi |
| --- | --- | --- |
| Đăng nhập, phân quyền quản lý/nhân viên | `backend/services/auth_service.py`, `backend/expansion/site_scope.py`; `tests/test_auth.py`, `tests/test_expansion_sites.py` | Hai vai trò thực hiện được phần việc của mình; không phải dùng admin thay quản lý hoặc bỏ guard để mở chức năng |
| Khu vực, vị trí, loại xe | `backend/routers/zone.py`, `parking_slot.py`, `vehicle_type.py`; `backend/expansion/site_router.py`; `tests/test_management_api.py`, `tests/test_zone_slot_integrity.py` | Khu/chỗ đã có đường theo bãi. Quản lý loại xe và bảng giá hiện còn phụ thuộc API toàn hệ thống/admin trên website; cần chốt luồng quản lý đúng quyền |
| Xe vào/ra, thời gian gửi | `backend/services/parking_service.py`, `backend/expansion/site_router.py`; `tests/test_session_lifecycle_integrity.py`, `tests/test_checkout_quote_contract.py` | Nhập biển thủ công phải hoàn tất được hành trình; OCR là lựa chọn hỗ trợ |
| Tính phí theo loại xe và thời gian | `ParkingService.calculate_fee`, `backend/routers/price_config.py`; `tests/test_fee.py`, `tests/test_price_config_api.py` | Hiển thị cách tính/phí trước trả xe; số tiền do server xác định, giữ xác nhận thu tiền |
| Chỗ trống theo khu vực | `ParkingService.get_available_slots_summary`, `backend/expansion/site_service.py`; `tests/test_slots.py`, `tests/test_expansion_sites.py` | Phân biệt chỗ có xe, chỗ bị giữ và chỗ có thể nhận xe; cập nhật sau vào/ra |
| Tra cứu theo biển số và thời gian | `ParkingService.search_sessions`; `backend/expansion/site_router.py` và `frontend/src/pages/Expansion/SitesWorkspace.jsx` | Luồng một bãi hiện có biển số/trạng thái, **chưa có tham số lọc khoảng thời gian** ở API sessions v2; cần bổ sung cả API và giao diện |
| Vé tháng hoặc khách quen | `backend/routers/monthly_pass.py`, `customer.py`, `backend/expansion/portal_router.py`; `tests/test_monthly_pass_api.py`, `tests/test_monthly_coverage_snapshot.py` | Demo vé còn hạn/hết hạn và phí tương ứng; thanh toán QR hoặc tự đăng ký của khách không phải điều kiện để chứng minh yêu cầu này |
| Lưu lượng, doanh thu, khung giờ cao điểm | `backend/services/report_service.py`, `backend/routers/report.py`, `backend/expansion/site_finance.py`; `tests/test_report_period_consistency.py` | Báo cáo hiện có ở luồng cũ; menu `/reports` bị ẩn trong chế độ một bãi. Cần màn hình ngày/tuần và dữ liệu đúng bãi, đúng kỳ, phân biệt thu demo |
| AI báo cáo ngày/tuần | `AIService.generate_daily_report`, `generate_weekly_report`; `backend/routers/ai_report.py`; `tests/test_ai.py`, `tests/test_ai_integrity.py` | Có mã và test mock; chưa có nghiệm thu provider thật cho bản hiện tại. API `/ai/*` còn dùng guard toàn hệ thống |
| AI hỏi đáp cao điểm/chỗ trống | `AIService.answer_question`, `ask_dashboard_question`; `tests/test_ai.py`, `tests/test_ai_integrity.py` | Menu `/ai` bị ẩn; tài khoản staff/manager theo bãi bị chặn ở luồng cũ. Cần ngữ cảnh đúng bãi, đúng thời điểm và quyền truy cập |
| AI gợi ý nhân sự | `AIService.suggest_staff_schedule`; `tests/test_ai.py`, `tests/test_ai_provider_fail_closed.py` | `insights/staff-plan` hiện tính kịch bản theo quy tắc. Hữu ích để cung cấp căn cứ, nhưng không thay bằng chứng chạy luồng AI Engine theo đề |
| Test cho vào/ra, phí, chỗ trống, AI | Các file test ở trên; `tests/conftest.py` chặn provider thật trong pytest | Giữ kiểm thử tự động; ghi riêng phiên chạy model thật, không gọi mock là kết quả live |
| AI trong SDLC: KT1/KT2/KT3/cuối kỳ | `docs/AI_SDLC.md`, `docs/EXPANSION_SDLC.md`, code/test/commit | Minh chứng chính phải bám nghiệp vụ và AI báo cáo. Phân biệt prompt tái lập với bản ghi prompt đã thực sự sử dụng; không tạo lại lịch sử như bằng chứng gốc |

## 3. Những khoảng thiếu đã xác nhận bằng mã

1. `frontend/src/layouts/MainLayout.jsx` ẩn `/reports` và `/ai` khi `singleSiteMode` bật; `PermissionRoute` cũng bảo vệ các trang legacy.
2. `backend/main.py` gắn `require_legacy_workspace` cho `/ai`, `/reports` và API v1. `backend/expansion/system_router.py` chặn tài khoản không phải admin khi CSDL còn nhiều bãi, kể cả bãi đã đóng. Ẩn bộ chọn bãi trên frontend không thay đổi điều này. Không sửa bằng cách cấp quyền toàn hệ thống cho mọi người hoặc xóa dữ liệu bãi cũ.
3. `/api/v2/sites/{site_id}/sessions` chỉ nhận `license_plate`, `status`, `limit`, `offset`; thiếu lọc thời gian cho luồng một bãi.
4. Gemini đang tắt theo phạm vi phát hành trước. Camera YOLO hoạt động và test AI mock đạt không chứng minh ba chức năng AI phân tích đã hoạt động trên website.

**Nghiệm thu đầy đủ theo đề gốc: NOT READY**, do các khoảng thiếu trên. Kết quả READY của các release trước chỉ áp dụng cho phạm vi demo/kiểm thử đã ghi, không phải xác nhận đủ đề bài.

## 4. Thứ tự công việc đã điều chỉnh

1. **PARK-217 — AI phân tích theo đúng bãi:** dùng lại các chức năng AI hiện có; tổng hợp dữ liệu ở server, kiểm quyền, lưu nguồn/kỳ báo cáo. Hoàn tất ngày/tuần, hỏi đáp chỗ trống/cao điểm và gợi ý nhân sự; kiểm thử rỗng/sai/provider lỗi và nghiệm thu model thật trên cấu hình được phép dùng. Không tự bật provider hoặc tải LLM vào Fly 1 GB trong lần đối chiếu phạm vi này.
2. **PARK-218 — Hành trình nghiệp vụ đúng đề:** đưa báo cáo và AI vào điều hướng chính sau khi API đúng phạm vi; thêm lọc thời gian, bảo đảm cấu hình loại xe/bảng giá đúng quyền quản lý. Giữ khóa, transaction, phân quyền và dữ liệu hiện có.
3. **PARK-219 — Minh chứng và nghiệm thu bản nộp:** đối chiếu từng yêu cầu với thao tác, dữ liệu, test và kết quả thật; hoàn thiện KT1/KT2/KT3/cuối kỳ. Ghi rõ phần nào là số liệu mẫu và phần nào là mô phỏng; giữ hồ sơ Word/ảnh/credentials ngoài Git.

Các ticket trên là công việc còn mở, chưa được tính là đã sửa. Các tối ưu truy vấn, tránh đọc ảnh thừa và sắp chữ OCR đã phát hành vẫn giữ nguyên.

## 5. Phần bổ sung và phần không phát triển tiếp

- Camera/YOLO: minh họa hỗ trợ nhập biển; không phải trọng tâm chấm ba chức năng AI phân tích.
- Portal khách, QR mô phỏng, đặt chỗ, danh sách chờ, quản lý nhóm xe: giữ phần đã có để giới thiệu nếu còn thời gian; chưa tiếp tục mở rộng trước khi hoàn tất mục bắt buộc.
- Không đưa nhiều bãi, video liên tục, ngân hàng thật, tự mở barie, GPU hoặc microservices thành yêu cầu của đồ án cơ bản.
- Tham khảo hệ thống lớn chỉ để học cách bảo vệ dữ liệu, tối ưu truy vấn và trình bày kết quả; không lấy độ phức tạp của chúng làm mục tiêu phát triển.

## 6. Kịch bản nghiệm thu theo đề

Đây là kịch bản mục tiêu, chưa phải biên bản đã thực hiện đầy đủ trên website.

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

## 7. Bằng chứng của lần đối chiếu này

Đã đọc các guard, route, màn hình và test nêu trên. Chạy lại `tests/test_ai.py`, `tests/test_ai_integrity.py`, `tests/test_ai_provider_fail_closed.py`, `tests/test_fee.py`, `tests/test_slots.py`, `tests/test_session_lifecycle_integrity.py`, `tests/test_report_period_consistency.py`: **167 passed**, 42,32 giây. AI dùng mock, DB riêng trong bộ test; không gọi Gemini hoặc ghi dữ liệu website. Log ở `backend/artifacts/original-spec-alignment/core-regression.log` ngoài Git.

Lần này điều chỉnh tài liệu phạm vi và ưu tiên; chưa thay mã ứng dụng, cấu hình provider, schema hoặc dữ liệu production. Hoàn tất nghiệp vụ/AI trong ticket phải có kiểm thử và release gate mới trước khi kết luận đủ đề.
