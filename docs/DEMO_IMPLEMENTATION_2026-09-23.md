# Triển khai giao diện đã duyệt — 23/09/2026

**Cập nhật24/09:** Người dùng không chấp nhận bố cục bản tích hợp đầu và yêu cầu đúng mẫu8790. Đã sửa/kiểm lại giao diện; kết luận và bằng chứng mới tại [PROTOTYPE_ALIGNMENT_2026-09-24.md](PROTOTYPE_ALIGNMENT_2026-09-24.md). Kiểm chứng backend bên dưới vẫn thuộc đợt23/09; không dùng đánh giá giao diện cũ thay cho đợt mới.

## Phê duyệt và ranh giới

Người dùng duyệt prototype `frontend/prototypes/parking-simple`: “được hãy triển khai theo bản demo này”. Triển khai trên FastAPI/React hiện có, dữ liệu một bãi; giữ toàn bộ yêu cầu học phần và quyền theo bãi. Prototype giữ nguyên để đối chiếu, không đưa role-switch hay dữ liệu RAM vào ứng dụng thật. Kiểm trên DB tổng hợp riêng, không thay DB khách đang dùng hoặc tự push/deploy.

## Giao diện

- Admin/Manager: Tổng quan, Vận hành, Bãi đỗ, Lịch sử, Khách & vé, Thu chi & báo cáo, Loại xe & giá. Các màn liên quan nằm trong tab, không thêm từng mục vào sidebar. Staff vận hành với quyền hạn chế. Admin bao gồm Manager.
- Customer: Phí gửi xe, Đặt chỗ trước, Vé & lịch sử, Hỗ trợ. Đặt trước không phải điều kiện nhận xe. Chatbot tròn góc phải cho các vai trò, nội bộ hỏi dữ liệu được cấp quyền; khách chỉ thông tin công khai.
- Giữ đường dẫn cũ và guard, các chức năng nâng cao trong Công cụ khác. Tổng quan/AI dùng API theo bãi; lịch sử AI kèm aggregate input đã lưu để đối chiếu.

## Các hợp đồng dữ liệu bổ sung

### Loại xe

`VehicleType.requires_plate` mặc định true để tương thích dữ liệu cũ; `code_prefix` tùy chọn, tối đa8 ký tự chữ/số. Loại không có biển số được server cấp mã riêng khi nhận xe. Không tạo biển giả ở trình duyệt.

### Thanh toán theo biển số/mã xe

`POST /api/v2/me/fee-lookup` xác thực Customer. Khách có quyền sở hữu được dùng quyền hiện tại; lượt vãng lai cần proof riêng trên vé. `session_ticket_credentials` quản lý phiên bản/revocation; `session_payment_access` cấp quyền hẹp user/session, gắn snapshot và thời hạn. Proof PAP1 ký theo mục đích riêng, không dùng mã lượt hoặc QR nhận/trả xe PA1 như chứng minh sở hữu. Quyền này không tự cấp Vehicle ownership, lịch sử của chủ xe hoặc chứng từ thu tại quầy. Các khoản online dùng quote/credit/ledger hiện tại; QR không chứng minh tiền đã nhận.

### Đặt trước

`declared_parking_reservations` lưu riêng user/biển hoặc mã xe/type/slot/thời gian/trạng thái/request-id và liên kết lượt khi đến. Không tạo/đổi chủ Vehicle khi đặt. Capacity và admission dùng chung predicates/DB guards để đặt chỗ không bị nhận trùng. Các đơn/vé trả trước lịch sử giữ nguyên chính sách và dữ liệu.

### Camera tự động có điều kiện

`vision_automation_policies` giữ cấu hình bật/tắt theo camera; `vision_passage_events` lưu quyết định theo observation chống lặp. Chỉ nhân viên đã xác thực xử lý; edge token không có quyền cho xe vào/ra. Chỉ một biển OCR đủ tin cậy, còn mới, xe đã có loại đăng ký rõ ràng được tự nhận. Loại xe lấy từ hồ sơ đăng ký, chưa phải bộ phân loại ảnh. Xe lạ/không chắc cần xác nhận thủ công. Tự trả chỉ khi kiểm quote và dư nợ bằng0; lượt/chứng từ/event cùng transaction.

### AI

Nội bộ tiếp tục dùng scoped report/analysis và lưu aggregate snapshot. Customer assistant chỉ gửi published public profile/catalog/capacity vào provider hiện có; không có biển, hồ sơ, lượt riêng hoặc doanh thu. Lỗi provider hiển thị đúng, không lưu kết quả giả.

## Kiểm chứng

Kết quả trên mã hiện hành, DB tổng hợp riêng; không dùng test của prototype thay nghiệm thu backend:

| Nhóm | Kết quả | Bằng chứng |
|---|---|---|
| Frontend toàn bộ Node tests | 272 đạt (gồm cả test prototype có sẵn), lint không lỗi, build đạt | `backend/artifacts/approved-implementation/frontend-final-tests.log`, `frontend-build.log` |
| Backend nghiệp vụ và tích hợp mới | 81 đạt: quyền tra phí/chứng từ, đặt chỗ/capacity/race, mã xe, AI/chat, camera/checkout, analytics | `backend/artifacts/approved-implementation/backend-final.log` |
| Schema, rollout và PostgreSQL contract | 348 đạt, 1 bỏ qua; gồm giữ dữ liệu cũ, guard/schema/readiness | `backend/artifacts/approved-implementation/release-schema-final.log` |
| Giao dịch qua UI và API thật | 42/42 đạt: walk-in, xe không biển, phí chính chủ/mã vé, đặt/hủy, hỗ trợ, thu/trả, lịch sử, gia hạn/ngừng vé tháng | `backend/artifacts/approved-demo-browser/ddeff4b775/result.json` |
| Giao diện desktop/mobile | Manager/Staff 60 kiểm tra đạt trước lần restart có chủ đích; Customer/Admin 33/33 đạt trong phần tiếp nối | `97250d2766/result.json`, `97250d2766/interruption.json`, `79e74636f1/result.json` dưới `backend/artifacts/approved-demo-browser/` |
| AI thật | Chưa đạt; API sinh báo cáo ngày trả503 cả trước và sau kiểm tra kết nối ngoài sandbox. Không có output mới để review; các ca tiếp theo không chạy | `backend/artifacts/approved-implementation/live-ai.json`, `live-ai-connected.json` |

Hai lỗi rollout được phát hiện và sửa: mặc định boolean SQLite phải khớp model; nguồn guard phải khớp snapshot migration đã đóng băng. Windows chọn nhầm module camera do tên khác chữ hoa đã được sửa bằng đổi tên helper. Admission nay dùng cùng biển chuẩn hóa, giữ nguyên biển lưu lịch sử và từ chối khi nhiều hồ sơ cũ cùng khớp.

Đã rà ảnh theo một đợt desktop/mobile; sửa duy nhất lỗi chip sơ đồ bãi không xuống dòng trên mobile. Ảnh xác nhận rộng390px, scale1, không tràn; reviewer chấm lỗi này **resolved**. Không tạo được reviewer mới vì giới hạn số agent, nên dùng lại agent triển khai cho lượt rà ảnh và ghi rõ giới hạn. Không coi rà ảnh là nghiệm thu camera/LLM. Thiết kế hiện có ghi ở `DESIGN.md` và `frontend/src/IMPLEMENTED_DESIGN.md`.

## Mở bản chạy thật cục bộ

- URL: **http://127.0.0.1:8793**. Cổng8790 vẫn là prototype cũ.
- Tài khoản thử: `admin_demo`, `manager_demo`, `staff_demo`, `customer_demo`. Mật khẩu chỉ có trong tệp cục bộ `backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json`; không chép vào tài liệu/bộ nhớ chung.
- DB riêng: `backend/artifacts/approved-implementation/approved-demo.db`; có dữ liệu giả lập14 ngày, xe máy/ô tô/xe đạp và dữ liệu từ các lượt UAT. Không xóa hoặc reset DB hiện có của người dùng.

Khởi động lại sau khi dừng bản đang chạy:

```powershell
./scripts/start_single_lot_demo.ps1 -Port 8793 -EnableAI -Database "$PWD/backend/artifacts/approved-implementation/approved-demo.db"
```

Thử theo thứ tự: Manager → Vận hành nhận xe không đặt trước → xem vé/mã thanh toán riêng → Customer tra phí hoặc đặt/hủy trước → Manager thu/trả → Lịch sử → Khách & vé → Báo cáo/AI. Admin có các thao tác của Manager cùng quản trị tài khoản; Staff chỉ xem và thao tác trong quyền vận hành.

## Dữ liệu và giới hạn còn lại

- Migration PostgreSQL cộng thêm08/09 đã render SQL offline; head là `20260923_09`. SQLite đã rollout và kiểm trên DB tổng hợp. Chưa chạy migration trên PostgreSQL thật hay DB của người dùng; khi áp dụng dùng quy trình copy-first hiện có trong `db_rollout.py` và bản sao lưu.
- Loại xe camera lấy từ hồ sơ xe đã biết, **chưa phân loại xe bằng ảnh**. Chỉ khung hình trực tiếp/edge đủ mới và đủ tin cậy mới đủ điều kiện tự động; ảnh tải tay luôn cần xử lý thủ công. Chưa nghiệm thu webcam/điện thoại thực tế hoặc độ chính xác OCR.
- Chưa có payOS của người dùng. Luồng quote/credit/thanh toán/chứng từ đã tích hợp và kiểm offline, không phát sinh tiền thật. Bản DB đồ án luôn tắt ngân hàng thật.
- Customer chưa liên kết hồ sơ vẫn tra phí bằng mã vé và đặt trước; yêu cầu hỗ trợ gắn hồ sơ/chứng từ cần liên kết hồ sơ theo quyền backend hiện có.
- Bắt mẫu mã bí mật PAP1 trong câu hỏi Customer trước khi gửi provider; prompt chỉ kèm dữ liệu công khai của bãi. Không có fallback AI giả khi provider lỗi.
- Chưa push/deploy website hoặc xuất lại Word/slide. Cần nghiệm thu5 ca AI thật và đối chiếu nội dung khi dịch vụ hoạt động trở lại để chốt toàn bộ yêu cầu AI của đề tài.

## Minh chứng SDLC trong vòng này

Yêu cầu gốc của người dùng: “được hãy triển khai theo bản demo này”. KT1 ghi hợp đồng quyền/đặt trước/camera bên trên và ở `intent.md`, `plan.md`; KT2 thể hiện trong mã React/FastAPI cùng các test nghiệp vụ/đồng thời; KT3 có `test_customer_assistant.py`, `test_core_site_analytics.py` và prompt/provider seam trong `AIService`. Các câu hỏi mô hình thử nghiệm và kết quả thất bại thật được giữ trong artifact đã loại thông tin bí mật. Tài liệu này mô tả công việc thực hiện, không dựng lại hội thoại hay bịa kết quả provider.
