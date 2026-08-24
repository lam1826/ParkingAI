# Minh chứng sử dụng AI trong SDLC – ParkingAI

## 1. Phân tích và thiết kế (KT1)

### Bài toán nghiệp vụ

Một lượt gửi xe chỉ được mở khi phương tiện chưa có lượt `active` và còn vị trí hoạt động đúng loại xe. Check-in khóa vị trí; check-out tính phí rồi giải phóng vị trí trong cùng giao dịch. Vé tháng chỉ miễn phí khi đang hoạt động và ngày ra nằm trong thời hạn vé.

### Prompt minh chứng

> Hãy phân tích các bất biến của luồng xe vào/ra cho bãi xe có nhiều khu vực, nhiều loại xe, vé tháng và bảng giá theo giờ. Đề xuất mô hình dữ liệu tránh một xe có hai phiên đang hoạt động và tránh một vị trí bị cấp cho hai xe.

### Kết quả áp dụng

Các thực thể chính: `Zone`, `ParkingSlot`, `VehicleType`, `Vehicle`, `Customer`, `MonthlyPass`, `PriceConfig`, `ParkingSession`, `User`, `Role`, `AiReport`. `ParkingSession` dùng UUID làm mã vé; trạng thái vị trí và phiên được cập nhật cùng giao dịch.

## 2. Xây dựng và debug (KT2)

### Prompt minh chứng

> Sinh API CRUD FastAPI/SQLAlchemy 2 cho khu vực, vị trí, loại xe, khách hàng, phương tiện, vé tháng và bảng giá. Review logic tính phí: vé tháng bằng 0; giá theo giờ/ngày làm tròn lên; cấu hình mới nhất có hiệu lực được ưu tiên; thời gian ra trước thời gian vào phải bị từ chối.

### Kết quả áp dụng

- CRUD dưới `/api/v1`, bắt buộc JWT.
- API nghiệp vụ dưới `/parking` cho check-in, check-out, chỗ trống và tìm kiếm.
- Bảng giá chọn bản ghi đang hoạt động, đã đến ngày hiệu lực và mới nhất.
- Chuẩn hóa biển số; từ chối loại xe gửi lên không khớp xe đã đăng ký.
- `manager/admin` mới truy cập quản lý tài khoản và vai trò.

## 3. Prompt AI và kiểm thử (KT3)

### Nguyên tắc prompt

Prompt luôn truyền dữ liệu có cấu trúc JSON, yêu cầu chỉ trả lời từ dữ liệu được cung cấp và quy định câu trả lời khi thiếu dữ liệu. Tên model đặt bằng `GEMINI_MODEL` để có thể nâng cấp mà không sửa mã.

Từ `gemini-3.7-flash`, việc ràng buộc tính xác định của câu trả lời do prompt đảm nhiệm hoàn toàn, không còn dùng "nhiệt độ thấp".

Theo migration guide chính thức, các **legacy sampling parameter** đã bị loại khỏi luồng hiện tại của model này: `temperature`, `top_p`, `top_k`, `candidate_count`, `thinking_budget` (trong đó `thinking_budget` có hướng thay thế bằng `thinking_level`). Các configuration được hỗ trợ khác **vẫn có thể tồn tại** — migration guide không cấm toàn bộ `config`.

**Chính sách migration hiện tại của dự án:** năm luồng gọi AI (`generate_daily_report`, `generate_weekly_report`, `answer_question`, `ask_dashboard_question`, `suggest_staff_schedule`) **chọn không truyền `config`** vào `generate_content()`, để model chạy ở thinking level mặc định `medium`. Đây là lựa chọn của dự án cho đợt migration này, không phải ràng buộc bắt buộc từ phía provider.

Nguồn: <https://ai.google.dev/gemini-api/docs/latest-model> và <https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash>.

### Prompt báo cáo mẫu

> Bạn là chuyên gia vận hành bãi xe. Chỉ dùng JSON được cung cấp, không tự tạo số liệu. Trả kết quả gồm: Tóm tắt, Đánh giá lưu lượng, Khung giờ cao điểm, Khuyến nghị. Nếu dữ liệu rỗng, nói rõ chưa đủ dữ liệu và không suy đoán.

### Các trường hợp kiểm thử

- Check-in thành công, sai loại xe, xe đã ở trong bãi, bãi hết chỗ.
- Check-in chọn đích danh vị trí: thành công, vị trí không tồn tại (404), vị trí đã có xe (409),
  vị trí không hỗ trợ loại xe (400).
- Check-out thành công, xe không tồn tại, check-out hai lần, giải phóng vị trí;
  đường check-out phụ `/api/v1/parking-sessions/{id}/check-out` do server tính phí
  (bỏ qua phí client gửi) và không cho check-out hai lần.
- Phí theo giờ/ngày (nhánh DAILY có test riêng), vé tháng thật miễn phí (fee == 0),
  giá 0, thiếu bảng giá, khoảng thời gian sai.
- Boundary tính phí: 0 giây, đúng 1 giờ (3600s), thiếu 1 giây (3599s), vượt 1 giây (3601s).
- Chỗ trống khi có chỗ/hết chỗ, nhóm theo khu vực, lọc đúng loại xe.
- AI hỏi đáp, báo cáo ngày, báo cáo tuần và gợi ý nhân sự thành công.
- AI từ chối câu hỏi chỉ có khoảng trắng, dữ liệu rỗng và khoảng ngày tuần sai.
- AI xử lý provider lỗi/timeout và prompt bắt buộc không bịa dữ liệu.
- Thiếu `GEMINI_API_KEY`: endpoint AI trả 503 rõ ràng, thống kê cơ bản vẫn chạy.
- Backend tự tổng hợp dữ liệu cho AI khi client không gửi số liệu
  (daily-report/staff-suggestion kiểm tra prompt chứa số liệu backend tổng hợp).

## 4. Hoàn thiện và triển khai cuối kỳ

AI được dùng để review độ phủ yêu cầu, phát hiện API đăng nhập không tương thích OAuth2, luồng frontend check-out bỏ qua tính phí, route giao diện thiếu và dependency biểu đồ đặt sai package. Các lỗi đã được sửa, sau đó xác minh bằng pytest, ESLint và bản build production.

Khi demo: tạo dữ liệu khu vực → loại xe → vị trí → bảng giá → phương tiện; thực hiện check-in/check-out; xem Dashboard/Báo cáo; cuối cùng hỏi AI “Khung giờ nào đông nhất?” và sinh gợi ý nhân sự.

## 5. Ma trận truy vết yêu cầu

| Yêu cầu | Phần triển khai | Minh chứng kiểm thử |
| --- | --- | --- |
| Đăng nhập và phân quyền | JWT, `RoleChecker`, vai trò customer/staff/manager/admin; đăng ký manager/admin bằng mã bí mật | `tests/test_auth.py`, `tests/test_management_api.py` |
| Khu vực, vị trí, loại xe | CRUD dưới `/api/v1`; giao diện quản lý tương ứng | `tests/test_management_api.py` |
| Xe vào/ra và thời gian gửi | `/parking/check-in` (chọn vị trí cụ thể hoặc tự cấp phát), `/parking/check-out`, lịch sử phiên | `tests/test_check_in.py`, `tests/test_check_out.py` |
| Tính phí | Theo giờ/ngày, bảng giá có hiệu lực, vé tháng hợp lệ miễn phí | `tests/test_fee.py`, `tests/test_check_out.py` |
| Theo dõi chỗ trống | Thống kê toàn bãi và nhóm theo khu vực/loại xe | `tests/test_slots.py` |
| Tra cứu theo biển số/thời gian | Bộ lọc API và màn hình phiên đỗ xe | `tests/test_check_in.py`, `tests/test_check_out.py` |
| Vé tháng/khách quen | CRUD khách hàng, phương tiện và vé tháng | `tests/test_management_api.py` |
| Lưu lượng, doanh thu, cao điểm | Dashboard và `/reports/traffic`, `/reports/revenue` | `tests/test_dashboard.py`, `tests/test_extensions.py` |
| Sơ đồ chỗ đỗ | Trình bày vị trí theo khu vực, loại xe và ba trạng thái màu; chuyển đổi sơ đồ/danh sách | ESLint và production build |
| Xuất báo cáo | `/reports/export/xlsx`, `/reports/export/pdf`; nút tải trên trang Báo cáo | `tests/test_extensions.py` |
| Nhật ký hoạt động | Middleware ghi thao tác thay đổi dữ liệu; `/api/v1/audit-logs` chỉ dành cho manager/admin | `tests/test_extensions.py` |
| AI báo cáo ngày/tuần | `/ai/daily-report`, `/ai/weekly-report`; nút nhanh trong chatbot | `tests/test_ai.py` |
| AI hỏi đáp dữ liệu | `/ai/question` tự lấy Dashboard; `/ai/ask` nhận dữ liệu có cấu trúc | `tests/test_ai.py` |
| AI gợi ý nhân sự | `/ai/staff-suggestion`; nút “Gợi ý nhân sự” trong chatbot | `tests/test_ai.py` |
| AI tích hợp giao diện | Trang **AI Analytics** (`/ai`) trong menu và chatbot nổi dùng chung trong `MainLayout` | ESLint và production build |

## 6. Truy vết prompt → code → test

### Báo cáo ngày

- Prompt: chỉ phân tích JSON trong ngày; kết quả gồm Tóm tắt, Đánh giá lưu lượng, Khung giờ cao điểm, Khuyến nghị.
- Code: `backend/services/ai_service.py::generate_daily_report` và `POST /ai/daily-report`;
  client chỉ gửi `target_date`, backend tự tổng hợp thống kê ngày từ database.
- Giao diện: nút **Báo cáo ngày** gọi thẳng `/ai/daily-report`.
- Test: `test_ai_daily_report_success`, `test_ai_daily_report_server_side_aggregation`, `test_ai_reports_reject_empty_data`.

### Báo cáo tuần

- Prompt: so sánh các ngày, nêu xu hướng lưu lượng/doanh thu có trong JSON và không tự tạo số liệu.
- Code: `backend/services/ai_service.py::generate_weekly_report` và `POST /ai/weekly-report`;
  client chỉ gửi khoảng ngày, backend tổng hợp lượt vào/ra và doanh thu theo từng ngày
  (`ParkingService.get_daily_summaries`).
- Giao diện: nút **Báo cáo tuần** gửi khoảng 7 ngày gần nhất.
- Test: `test_ai_weekly_report_success`, `test_ai_weekly_report_rejects_invalid_date_range` và ca dữ liệu rỗng.

### Hỏi đáp dữ liệu

- Prompt: chỉ dùng dữ liệu Dashboard hoặc JSON do client gửi; nếu thiếu phải trả lời không đủ dữ liệu.
- Code: `ask_dashboard_question`, `answer_question`, `POST /ai/question`, `POST /ai/ask`.
- Giao diện: ô chat và các câu hỏi gợi ý thay đổi theo trang hiện tại.
- Test: prompt hợp lệ/rỗng, dữ liệu rỗng, chống ảo giác, provider lỗi và timeout.

### Gợi ý nhân sự

- Prompt: nhận lưu lượng theo giờ, doanh thu và tỷ lệ lấp đầy; trả giờ cao điểm, số nhân viên và ca trực.
- Code: `suggest_staff_schedule` và `POST /ai/staff-suggestion`; client gửi body rỗng,
  backend tự tổng hợp lưu lượng theo giờ, doanh thu và tỷ lệ lấp đầy từ database.
- Giao diện: nút **Gợi ý nhân sự** gọi thẳng `/ai/staff-suggestion`.
- Test: `test_ai_staff_suggestion_success`, `test_ai_staff_suggestion_server_side_aggregation` và ca lưu lượng rỗng.

## 7. Kết quả xác minh

### 7.1. Bằng chứng LỊCH SỬ — ngày 18/08/2026 (model `gemini-3.6-flash`)

> Mục này là bằng chứng lịch sử, giữ nguyên đúng số liệu và model **thực tế
> đã chạy tại thời điểm đó**. Không cập nhật theo model mới — xem 7.2 cho
> trạng thái hiện hành.

| Hạng mục | Kết quả |
| --- | --- |
| Toàn bộ backend | `79 passed` |
| Riêng AI | `17 passed` |
| Frontend ESLint | Đạt, không có lỗi |
| Frontend production build | Đạt, Vite build thành công |
| Kết nối Gemini thật | Đạt — **với `gemini-3.6-flash`**; khóa API hợp lệ, model trả về nội dung |
| Model cấu hình lúc đó | `gemini-3.6-flash` (đặt qua biến `GEMINI_MODEL`) |

### 7.2. Đợt 10C — nâng cấp lên `gemini-3.7-flash` (ngày 25/08/2026)

| Hạng mục | Kết quả |
| --- | --- |
| Model đích | `gemini-3.7-flash` (đặt qua `GEMINI_MODEL`, khớp `backend/core/config.py`) |
| Riêng AI (`tests/test_ai.py`) | `24 passed` (17 cũ + 7 test regression mới) |
| Toàn bộ backend | `196 passed` |
| Frontend test / ESLint / production build | Đạt |
| Phương thức kiểm thử | **Hoàn toàn bằng mock** (`services.ai_service.genai.Client` được patch ở mọi test) |
| Gọi provider live trong đợt này | **Không** — không có request nào tới Gemini |
| Kết nối Gemini 3.7 live | **CHƯA XÁC MINH** — chưa từng chạy thật với model này |

> ⚠️ Bằng chứng "Kết nối Gemini thật: Đạt" ở mục 7.1 **chỉ áp dụng cho
> `gemini-3.6-flash`** và **không** chứng nhận `gemini-3.7-flash`. Việc xác
> minh kết nối live với model mới là hạng mục riêng, chưa thực hiện.

Lệnh tái hiện:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests\test_ai.py -q
Set-Location frontend
npm.cmd run lint
npm.cmd run build
```

Tài liệu model chính thức: <https://ai.google.dev/gemini-api/docs/models>.

## 8. Kịch bản demo cuối kỳ

1. Đăng ký customer bình thường; đăng ký manager bằng `MANAGER_REGISTRATION_CODE`.
2. Đăng nhập manager, tạo khu vực, loại xe, vị trí đỗ và bảng giá.
3. Tạo khách hàng/phương tiện, check-in rồi kiểm tra số chỗ trống giảm.
4. Check-out, kiểm tra phí và vị trí được giải phóng; lặp lại với vé tháng để chứng minh miễn phí.
5. Mở Dashboard/Báo cáo để xem lưu lượng, doanh thu và cao điểm.
6. Mở chatbot nổi tại một trang bất kỳ; thử hỏi đáp, Báo cáo ngày, Báo cáo tuần và Gợi ý nhân sự.
7. Mở lịch sử báo cáo AI để chứng minh prompt và kết quả đã được lưu theo tài khoản.

## 9. Các phần mở rộng

### Sơ đồ chỗ đỗ trực quan

Trang vị trí đỗ có hai chế độ **Sơ đồ** và **Danh sách**. Sơ đồ nhóm vị trí theo khu vực, hỗ trợ lọc khu vực/loại xe/trạng thái và quy ước màu:

- Xanh: vị trí còn trống.
- Đỏ: vị trí đang có xe.
- Xám: vị trí bảo trì hoặc ngừng hoạt động.

### Xuất báo cáo

Trang báo cáo có nút tải Excel và PDF theo kỳ ngày/tuần/tháng/năm. Tệp bao gồm tổng lượt, doanh thu, phí trung bình, loại xe phổ biến và các bảng lưu lượng theo giờ/ngày/tuần/tháng.

### Nhật ký hoạt động

Middleware ghi các thao tác tạo, cập nhật, xóa, check-in, check-out và tác vụ AI. Mỗi bản ghi gồm tài khoản, hành động, đối tượng, API, mã HTTP, kết quả và thời gian. Hệ thống không đọc hoặc lưu request body nên mật khẩu, khóa API và mã đăng ký không xuất hiện trong nhật ký. Chỉ manager/admin được xem màn hình này.
