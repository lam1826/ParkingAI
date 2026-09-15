# Đối chiếu nghiệm thu lõi F01–F13

Ngày 15/09/2026; Git base `3ef172e`, mã nâng cấp chưa commit. Bảng này đối chiếu chức năng với bằng chứng cụ thể; không lấy tổng số test thay cho một ca nghiệp vụ. Trạng thái: lõi đủ bằng chứng SQLite/local để tiếp tục mở rộng. Bộ full có hai lỗi fixture đã sửa và kiểm lại riêng; không gọi lần full ban đầu là xanh. Năm output Gemini sau sửa và UI lịch sử đã được đối chiếu. Chi tiết giới hạn ở cuối bảng.

| Mã | Kết quả đã kiểm | Bằng chứng chính | Còn chốt |
|---|---|---|---|
| F01 | API/UI đúng quyền quản lý–nhân viên; manager tạo/khóa staff theo bãi, không nâng quyền | `test_core_crud_permissions.py`, `test_manager_staff_accounts.py`, P0 UI thật24; P1 HTTP79 | Đã kiểm, xem ghi chú full/fixture |
| F02 | Khu/chỗ/loại xe/giá đủ CRUD và ngừng dùng; slot/vehicle_type được kiểm lại khi khóa | Core CRUD, seed một bãi, kiểm tranh chấp loại/chỗ | Đã kiểm, xem ghi chú full/fixture |
| F03 | Nhận xe đúng loại/chỗ/biển; một xe/một chỗ không có hai lượt active | `test_check_in_concurrency.py`, lifecycle/scoped tests, P1 HTTP/UI | Đã kiểm, xem ghi chú full/fixture |
| F04 | Quote → xác nhận thu → trả xe/trả chỗ; miễn phí/retry không ghi thêm thu | `test_checkout_quote_contract.py`, `test_check_out_concurrency.py`, HTTP79 | Đã kiểm, xem ghi chú full/fixture |
| F05 | Giá lúc vào, giờ/24h làm tròn chính xác, snapshot bất biến; vé tháng chỉ thu phần quá hạn của entry-v1 | `test_billing_snapshot.py`, migration/concurrency, UAT thay giá | Đã kiểm, xem ghi chú full/fixture |
| F06 | Chỗ theo khu/loại, phân biệt tổng vật lý/ngừng dùng/có thể nhận; nhận/ra/hủy cập nhật đúng | Site availability tests, seed34 chỗ trống, P1 UI trả về35 | Đã kiểm, xem ghi chú full/fixture |
| F07 | Biển/mã lượt chính xác/trạng thái/ngày vào/phân trang, detail và lịch sử ngoại lệ, in lại vé | `test_session_id_search.py`, exceptions tests, Chrome38 và PDF1trang | Đã kiểm, xem ghi chú full/fixture |
| F08 | Hồ sơ khách/xe, vé tháng/gia hạn/coverage; nhãn sắp hết7ngày | `test_monthly_pass_api.py`, `test_monthly_coverage_snapshot.py`, seed và UI | Đã kiểm, xem ghi chú full/fixture |
| F09 | Lượt vào/ra/tổng, thu/hoàn/thu ròng/ca, CSV cùng quyền/kỳ; cancelled không đếm | `test_core_site_analytics.py`, `test_cancelled_analytics.py`, `test_finance_and_shifts.py`, HTTP/UI | Đã kiểm, xem ghi chú full/fixture |
| F10 | Gemini thật báo cáo ngày/tuần, lưu model/context/result, replay/history | 5ca trong `p2-live-ai-acceptance.json`; 30 kiểm tra transport+persistence | PASS bộ ca sau sửa |
| F11 | Hỏi đáp đúng chỗ/cao điểm; staff context không chứa tài chính và bị chặn history tài chính | Live operational_question, permissions/AI integrity tests | PASS bộ ca sau sửa |
| F12 | Nhân sự dùng tổng vào+ra, không đưa định biên vô căn cứ | Live staffing đối chiếu context | PASS:17đếntrước19,240cộng dồn |
| F13 | Minh chứng KT1/KT2/KT3, seed/cài mới, backup/restore và UAT có nguồn | [SDLC_EVIDENCE.md](SDLC_EVIDENCE.md), [IMPLEMENTATION.md](IMPLEMENTATION.md), [demo](../SINGLE_LOT_DEMO.md) | Đã đối chiếu; Word/slide cũ chưa xuất lại |

## Bộ kiểm chứng dùng để đọc bảng

- P0: backend1359passed/20skipped, frontend155, HTTP58, fixtureUI34, realUI24, restore36. Mốc này trước schema P1; không cộng vào testP1.
- P1: frontend171/lint/build; HTTP79; Chrome38 chức năng,16 kiểm ảnh; migration rehearsal và restore37. Bộ hồi quy baseline1491ca:1469pass/20skip/2fixturefail; cả hai đã sửa và kiểm lại3+69ca đạt. Lỗi fixture import riêng đã được tái hiện: copy database.py nhưng thiếu module billing_guards mới; ba test import sau sửa đạt (5,58s), không thay điều kiện filesystem read-only.
- AI live: provider Gemini cấu hình cục bộ, dữ liệu bãi tổng hợp có nhãn. Transport thành công không có nghĩa tất cả diễn giải đúng. Output đầu được giữ để minh chứng lỗi và vòng sửa; không gọi output đó là semantic đạt.
- PostgreSQL thực, ngân hàng thật và camera vật lý không nằm trong bằng chứng SQLite/local này. E01–E08 được nghiệm thu riêng ở giai đoạn mở rộng.

## Hành trình bảo vệ đồ án

1. Manager xem một bãi/3khu/40chỗ, cấu hình loại/giá và tài khoản staff.
2. Staff nhận xe, tìm mã vé, xem số chỗ thay đổi; API không cho staff sửa giá.
3. Manager đổi giá; staff xem phí lượt đã nhận vẫn theo giá lúc vào. Trả xe, xem/in biên nhận, kiểm chỗ được giải phóng.
4. Xem vé tháng còn/sắp/hết; trình bày test biên quá hạn và luồng ngoại lệ có lý do.
5. Manager xem thu/hoàn/ca và CSV; staff chỉ thấy thống kê vận hành.
6. Chọn kỳ demo có dữ liệu để sinh ba nhóm AI; chọn kỳ rỗng, xem giới hạn và context đối chiếu. Lịch sử cũ được ghi thời điểm, không giả là sinh mới.
7. Mở artifact migration/restore/test để chứng minh bảo toàn dữ liệu, quyền và chống trùng.

Thời lượng mục tiêu10–15phút, chưa đo buổi trình diễn hoàn chỉnh. Chỉ trình bày giao dịch tổng hợp, không mô tả đó là tiền ngân hàng đã nhận.

Ghi chú phiên bản kiểm: bộ hồi quy toàn bộ đã nạp baseline P1 trước bản sửa prompt khoảng giờ P2. Prompt mới được kiểm bằng suite AI riêng và gọi lại provider; không dùng lần full này để khẳng định prompt mới đã qua kiểm toàn bộ.

## Giới hạn kết luận

Kết quả hỗ trợ demo một bãi SQLite cục bộ và ba chức năng Gemini trên bộ số liệu tổng hợp đã kiểm. P2 mới có122testAI/analytics và5outputthật/30checks; UI lịch sử26checksđạt, hai vai trò, chỉ audit đăng nhập. Không bảo đảm mọi output tương lai đều đúng; người dùng vẫn đối chiếu dữ liệu nguồn. E01–E08 đang được triển khai riêng; bank/device live không được suy từ test giả. Các bản Word/slide lịch sử chưa xuất lại trong đợt này; bộ minh chứng Markdown/code/test hiện hành có thể truy xuất từ [SDLC_EVIDENCE.md](SDLC_EVIDENCE.md).
