# Minh chứng xây dựng bản demo — 23/09/2026

Phạm vi là bản xem trước theo đề tài, trước khi tích hợp ứng dụng thật. Người dùng yêu cầu: “thêm đủ chức năng của đề tài”. Mã, dữ liệu và kiểm chứng sau đây thuộc prototype, không phải kết quả gọi LLM hoặc backend thật.

## KT1 — phân tích và mô hình

Quyết định: một bãi nhiều khu; một khu có loại xe phục vụ và sức chứa; các vị trí được đặt mã riêng. Nhận xe không cần đặt trước. Một xe/một chỗ chỉ có một lượt active; chỗ giữ trước/ngừng hoạt động không nhận khách vãng lai. Admin kế thừa Manager, Staff vận hành, Customer thông tin của mình. Đây là quyết định dùng trong demo, còn chờ người dùng duyệt.

Dữ liệu ở `engine.js`: zones, slots, vehicleTypes, rates, customers, vehicles, monthlyPasses, sessions, reservations, transactions, audit. Vé tháng và giá được chốt khi xe vào; giá sửa sau đó không đổi phí lượt cũ. Gia hạn tạo kỳ riêng, giữ lịch sử đã dùng/đã thu.

## KT2 — mã và test nghiệp vụ

- `engine.js`: state/reducer thuần, giá theo giờ, coverage vé tháng, availability cùng quy tắc nhận xe, CRUD/dữ liệu tham chiếu.
- `core.js`: form danh mục, khách/xe/vé tháng, tìm lịch sử; `app.js`, `auth.js`: liên kết các màn, đăng nhập/đăng xuất mô phỏng và giới hạn thao tác theo vai trò.
- `engine.test.cjs`: nhận/trả/trùng/thiếu chỗ, mức phí và snapshot, vé tháng/ngoài hạn, giữ chỗ/ngừng dùng, toàn vẹn danh mục và quyền CRUD.
- `review_browser.py`: thao tác form trên HTML đã build, đối chiếu state và giao diện; ảnh desktop/mobile lưu trong artifacts ngoài Git.

Prompt tái lập (soạn lại để tái lập, không giả làm bản chép prompt đã dùng): “Hoàn thiện prototype bãi xe: thêm khu/chỗ/loại/khách/xe/vé tháng; giữ một nguồn tính phí và chỗ trống, kiểm nhận trùng, giữ chỗ, loại ngừng hoạt động. Người dùng phải thử được từng form; không sửa backend/CSDL/provider thật.”

## KT3 — prompt và AI mô phỏng

`analytics.js` tổng hợp dữ liệu theo ngày Việt Nam và 7 ngày kết thúc tại ngày chọn. Số lượt/phiếu thu đến từ state; thời điểm chỗ hiện tại tách khỏi kỳ báo cáo. `generate()` dựng văn bản mô phỏng có kỳ/nguồn/quyền, dữ liệu rỗng/sai được nêu rõ. Nhân sự gợi ý theo giờ có nhiều lượt vào+ra, không chốt định biên khi không có năng suất nhân viên.

`reports.js` lưu snapshot đầu vào/kết quả trong `state.aiReports`, tách vai trò; `chat.js` dùng cùng analytics, Customer chỉ dữ liệu công khai, Staff không hỏi doanh thu. `analytics.test.cjs` kiểm ngày biên, ledger, rỗng/sai, grounded numbers, quyền và snapshot bất biến. Đây là test hành vi mẫu, chưa phải đánh giá LLM.

Prompt dự kiến khi tích hợp AI thật:

```text
System: Bạn là trợ lý phân tích bãi đỗ xe. Không tự tạo số liệu, chỉ nhận xét từ dữ liệu được cung cấp. Phân biệt lượt vào, lượt ra và tổng giao dịch; tổng theo giờ của cả tuần khác với tốc độ một ca. Chỗ trống là ảnh chụp tại thời điểm riêng. Nêu thiếu dữ liệu và giả định khi gợi ý nhân sự.
User: Dữ liệu ngày/tuần {{parking_stats}}. Hãy tóm tắt cao điểm và gợi ý bố trí nhân sự.
```

## Cuối kỳ — hồ sơ và hướng dẫn

[README.md](README.md) ánh xạ mỗi yêu cầu tới màn và cách thử. Nút “Đối chiếu chức năng với đề tài” hiển thị hướng dẫn ngay trong HTML. `build.mjs` ghép một `index.html` tự chứa, có thể mở trực tiếp hoặc qua localhost. Bản này là cơ sở duyệt giao diện, không thay báo cáo triển khai hệ thống hoặc Word/slide cuối kỳ.

## Kết quả kiểm chứng

- `node --test .../engine.test.cjs .../analytics.test.cjs`: **30/30 đạt** (12 nghiệp vụ, 18 phân tích/AI mô phỏng).
- `review_browser.py`: **65/65 kiểm tra đạt**, gồm đăng nhập, quản lý danh mục, cấp/gia hạn vé tháng, vào/ra, phí, tra cứu, báo cáo/AI và quyền; có kiểm bố cục desktop/mobile. Không lỗi JavaScript hoặc gọi API/provider. Profile Chrome riêng đã được dọn sau kiểm tra.
- Kết quả và ảnh: `backend/artifacts/simple-ui-demo/core-completion/7049b00faf/`; các ảnh mobile sau sửa bố cục bảng đã được xem trực tiếp ở lượt xác nhận `d18e11550e`.
- `node --check` cho toàn bộ module JavaScript đạt; build HTML **210523 bytes**. HTTP200 tại localhost8790, nội dung khớp chính xác file đã build.
- `git diff --check` đạt. Hash diff nháp ứng dụng thật trước/sau giữ nguyên; không sửa thêm mã backend/React thật, CSDL hoặc gọi provider.

Đây là bằng chứng cho prototype tương tác. Chưa nghiệm thu xác thực máy chủ, lưu CSDL, LLM, thiết bị camera hay giao dịch ngân hàng thật.
