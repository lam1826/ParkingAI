# Phương án nâng cấp ParkingAI — một bãi phục vụ đồ án

Ngày: 15/09/2026. Mã nguồn đối chiếu: `3ef172e`.

**Cập nhật sau phê duyệt:** người dùng đã duyệt triển khai. Theo dõi mã đã sửa, kiểm chứng và các bước còn lại tại [IMPLEMENTATION.md](IMPLEMENTATION.md); các nhận xét mã bên dưới là baseline lúc lập phương án, không tự trở thành kết quả nghiệm thu.

**Phạm vi người dùng đã chốt:** chỉ một bãi duy nhất, có nhiều khu/vị trí, phục vụ đồ án. “Như hệ thống thật” được hiểu là nghiệp vụ khép kín, đúng quyền, đúng tiền, xử lý được tình huống lỗi, giao diện dễ trình diễn và có bằng chứng kiểm thử.

**Trạng thái:** người dùng đã hủy yêu cầu tham vấn Claude. Codex chốt cấu trúc phương án theo chỉ đạo mới: giữ đủ F01–F13, sau đó mở rộng QR nhận tiền, camera/OCR, computer vision và website khách mua vé giờ/ngày/tháng, đặt chỗ, thanh toán hóa đơn. Đã tham khảo website thật; đây là phương án, chưa phải kết quả triển khai.

Đọc cùng [tham khảo 5 hệ thống thực tế](REAL_WORLD_REFERENCES.md) và [thiết kế phần mở rộng E01–E08](EXTENSION_PLAN.md). Các chính sách chi tiết bên dưới là mặc định thiết kế đề xuất; không có bước chờ Claude.

## 1. Quyết định tổng thể

1. Giữ FastAPI + React/MUI + SQLAlchemy/Alembic + Gemini hiện có. Nâng cấp tại chỗ, theo từng luồng sử dụng.
2. Bản nộp có một bộ dữ liệu demo độc lập, chỉ một bãi. Hai vai trò trình diễn chính là **quản lý** và **nhân viên**; admin phục vụ cài đặt.
3. Ưu tiên đủ đề bài, sau đó hoàn thiện ca thu tiền, biên nhận, xử lý nhầm/mất vé và trải nghiệm vận hành.
4. AI cốt lõi là báo cáo, hỏi đáp và gợi ý nhân sự dựa trên số liệu. Giai đoạn sau có camera/OCR hỗ trợ nhập biển cần người xác nhận, và CV theo dõi ô đỗ; hai phần này không thay AI phân tích.
5. Nghiệm thu bằng hành trình đầy đủ của hai vai trò và các bất biến dữ liệu. Tổng số test không thay cho nghiệm thu chức năng.

## 2. Mã hiện tại đã có gì, khoảng thiếu nằm ở đâu?

Các nhận định dưới đây là kiểm tra mã tại HEAD nêu trên; không phải kiểm tra website đang chạy.

| Nhóm | Bằng chứng trong mã | Hướng nâng cấp |
|---|---|---|
| Đăng nhập/phân quyền | `backend/services/auth_service.py`, `backend/expansion/site_scope.py` | Chốt quyền theo thao tác; staff không sửa giá/cấu hình hay nâng quyền tài khoản |
| Khu/chỗ/loại xe | `backend/expansion/site_router.py`, `backend/routers/vehicle_type.py`, `SiteConfiguration.jsx` | Quản lý làm được toàn bộ trong giao diện một bãi; staff chỉ đọc cấu hình |
| Vào/ra và chỗ trống | `ParkingService`, `CheckoutService`, `parking_sessions` có unique index phiên active theo xe/chỗ | Giữ giao dịch nguyên tử và chống trùng; làm rõ thao tác thành công/lỗi/lặp trên UI |
| Phí và xác nhận thu | `calculate_fee`, quote có TTL 120 giây, `PaymentService` | Giữ xác nhận phí; bổ sung giá được chốt khi vào và quy tắc quá hạn vé tháng rõ ràng |
| Vé tháng/khách quen | `monthly_subscription_service.py`, `monthly_pass.py`, các trang legacy | Đưa về hành trình chính cho manager/staff, không bắt đăng nhập portal khách |
| Thu tiền/chốt ca/hoàn tiền | `backend/expansion/site_finance.py`, `frontend/src/pages/Expansion/SiteFinance.jsx` | Tái sử dụng; không viết thêm một hệ thống thu tiền song song |
| Báo cáo/AI | `site_analytics.py`, `AIService.generate_scoped_analysis`, `CoreAnalyticsPage.jsx` | Bổ sung lưu lượng ra theo giờ, định nghĩa chỉ số và đối chiếu AI; giữ số liệu do server tổng hợp |
| Tra cứu | API/UI đã có biển số, trạng thái, ngày vào từ/đến, phân trang | Bổ sung tìm mã vé; ghi rõ lọc theo ngày vào, không ngầm hiểu là xe có mặt trong khoảng |
| Ngoại lệ nghiệp vụ | `parking_session.py` có xóa phiên cho admin; chứng từ chặn xóa | Thay đường thao tác vận hành bằng hủy có lý do/lưu vết; không xóa lịch sử bằng nút nhân viên |
| Hồ sơ | `docs/AI_SDLC.md`, `ORIGINAL_REQUIREMENTS.md`, `CORE_AI_COMPLETION.md` | Đối chiếu lại toàn đề; phân biệt log thật, prompt mẫu, test mock và AI live |

### Hai vấn đề cần xử lý trước

**Một bãi trên màn hình chưa đồng nghĩa một bãi trong dữ liệu.** `legacy_workspace_allowed` đếm cả bãi đã đóng; nếu có hơn một bãi, manager/staff bị chặn các route legacy. `PermissionRoute` và `MainLayout` tiếp tục lọc menu. Do đó chỉ bật menu hoặc ẩn bộ chọn bãi không giải quyết được đầy đủ quyền quản lý.

**Quyền CRUD cần tách theo thao tác.** Router tổng `/api/v1` có mức tối thiểu staff; route loại xe/bảng giá hiện không có chặn manager riêng cho các thao tác ghi. Việc một màn hình bị ẩn do guard nhiều bãi không phải bằng chứng rằng quyền ghi đã được thiết kế đúng cho bản một bãi.

**Cách xử lý đề xuất:** tạo CSDL demo riêng với đúng một `ParkingSite`, membership rõ ràng và các bản ghi thuộc đúng bãi; dùng lại guard hiện có. Khôi phục đầy đủ menu lõi cho bản một bãi và bổ sung quyền ghi manager ở backend. Giữ dữ liệu/bản web cũ nguyên trạng. Nếu đưa bản mới lên web, dùng database/schema demo riêng và cấu hình đồng bộ; chưa chuyển dữ liệu hoặc deploy trong task lập phương án này.

Không chọn xóa bãi cũ hay gỡ guard để làm giao diện hoạt động. Không thêm hệ thống đa khách thuê để giải bài toán đồ án một bãi.

## 3. Bộ chức năng của bản nộp

### Bắt buộc theo đề

| Mã | Chức năng | Điều kiện đạt |
|---|---|---|
| F01 | Đăng nhập, đăng xuất, phân quyền | Hai tài khoản manager/staff dùng đúng chức năng; gọi API trái quyền bị từ chối |
| F02 | Khu vực, vị trí, loại xe | Thêm/sửa/ngừng dùng; mã không trùng; chỗ phù hợp loại xe; không giảm sức chứa dưới số chỗ đang có |
| F03 | Nhận xe | Nhập biển, loại xe, chọn/tự gợi ý chỗ, giờ server, mã vé duy nhất; không trùng xe/chỗ |
| F04 | Trả xe | Tra cứu → xem phí → xác nhận thu → kết thúc lượt và giải phóng chỗ; retry không thu hai lần |
| F05 | Bảng giá/tính phí | VND số nguyên, theo loại và thời gian; hiển thị đơn giá/số block/căn cứ miễn phí; có test biên |
| F06 | Theo dõi chỗ | Tổng, có xe, có thể nhận xe, ngừng dùng theo khu/loại; làm mới sau thao tác thành công |
| F07 | Tra cứu | Biển số/mã vé/trạng thái/ngày vào; chi tiết xe, chỗ, giờ vào/ra, người thao tác và chứng từ |
| F08 | Khách quen/vé tháng | Hồ sơ khách, xe, đăng ký/gia hạn, trạng thái còn hạn/sắp hết/hết hạn; không có hai kỳ active chồng ngày cho cùng xe |
| F09 | Thống kê | Lượt vào/ra, xe đang gửi, thu/hoàn/thu ròng, cao điểm; lọc ngày/tuần, xuất bảng số liệu |
| F10 | AI báo cáo | Sinh báo cáo ngày và tuần từ dữ liệu đúng kỳ; lưu kết quả/nguồn/model/thời gian |
| F11 | AI hỏi đáp | Trả lời chỗ trống/cao điểm/doanh thu từ dữ liệu được phép; thiếu dữ liệu phải nói rõ |
| F12 | AI nhân sự | Nêu khung giờ cần chú ý; số người chỉ là giả định có căn cứ và phải được người quản lý xem xét |
| F13 | Test và SDLC | Test vào/ra/phí/chỗ/AI; minh chứng KT1/KT2/KT3/cuối kỳ truy được tới artifact thật |

### Hoàn thiện cảm giác vận hành thực tế

- Mở ca, tiền đầu ca, thu trong ca, tiền thực đếm, chênh lệch và chốt ca.
- Biên nhận có mã, thời gian, xe, loại thu, số tiền; xem/in lại từ cùng chứng từ.
- Hủy lượt vào nhầm có lý do và người thực hiện; trả chỗ đúng; giữ lịch sử.
- Mất vé: tra cứu bằng biển, quản lý xác nhận, ghi lý do và tiếp tục quy trình trả xe; không mặc định thu “phạt” khi chưa có chính sách.
- Sai biển: trước xác nhận cho sửa; sau khi đã nhận xe dùng quy trình điều chỉnh có lịch sử, không sửa âm thầm dữ liệu các lượt cũ.
- Hoàn tiền có lý do, liên kết chứng từ gốc, không vượt phần còn được hoàn. Dùng lại nghiệp vụ đã có.
- Cảnh báo đầy bãi, không có bảng giá, vé sắp hết hạn, ca chưa mở, dữ liệu vừa thay đổi hoặc mạng lỗi.
- Sao lưu/khôi phục dữ liệu demo, tài liệu cài mới và bộ dữ liệu trình diễn có thể tái tạo.

### Phần mở rộng đã đưa vào lộ trình sau nghiệm thu lõi

Website khách đăng ký/đăng nhập, quản lý xe, mua vé giờ/ngày/tháng, đặt chỗ, thanh toán QR, xem hóa đơn/biên nhận; camera nhận diện biển tại làn và computer vision nhận biết ô có xe/trống. Đây là phạm vi người dùng muốn phát triển tiếp, không chỉ là phần trình diễn nếu rảnh. Xem E01–E08 và P4–P8 trong [EXTENSION_PLAN.md](EXTENSION_PLAN.md).

QR nhận tiền cần adapter cổng thanh toán và đối soát server; QR mô phỏng hiện có chỉ phục vụ test/demo có nhãn. Không mở rộng nhiều bãi/SaaS hoặc bắt buộc barrier tự mở, GPU, microservices. Danh sách chờ, nhóm xe và dự báo nâng cao chưa được đưa thành ưu tiên chính.

## 4. Quyền của hai vai trò

| Thao tác | Nhân viên | Quản lý |
|---|---|---|
| Nhận/trả xe, xem chỗ, tra cứu lượt | Có | Có |
| Xem bảng giá/loại xe | Có | Có |
| Sửa khu/chỗ/loại xe/bảng giá | Không | Có |
| Xem hồ sơ khách/vé để phục vụ xe | Có, phạm vi cần thiết | Có |
| Cấp/gia hạn/ngừng vé tháng | Không mặc định; có thể thêm quyền riêng sau | Có |
| Mở/chốt ca của mình, biên nhận của giao dịch được phép | Có | Có |
| Xem đối soát toàn bãi, hoàn tiền, điều chỉnh ngoại lệ | Không | Có, có lý do |
| Xem lưu lượng/chỗ trống; AI vận hành | Có | Có |
| Báo cáo tài chính toàn bãi; AI doanh thu | Không mặc định | Có |
| Tạo/khóa tài khoản nhân viên | Không | Có; không tự tạo admin/nâng quyền bản thân |
| Nhật ký quản trị | Không | Có, chỉ đọc |

Đây là ma trận mục tiêu. Cần sửa cả menu, API lẫn dữ liệu đưa vào AI; ẩn nút không thay cho phân quyền. Nếu staff hỏi về tài chính không được phép, backend phải loại dữ liệu trước khi gọi AI, không chỉ bảo model đừng nói.

## 5. Các quy tắc nghiệp vụ đề xuất chốt

### Vào/ra và trạng thái

- Một xe chỉ có một lượt `active`; một vị trí chỉ giữ một lượt `active`. Một request thất bại không để lại xe/chỗ/tiền cập nhật dở.
- Trạng thái lượt: `active → completed` hoặc `active → cancelled`. Phiên completed không mở lại. Hủy khác với hoàn tiền; hoàn tiền không tự đưa xe trở lại bãi.
- Chỗ có xe được suy ra/đối soát với phiên active; nhân viên không tự bật “trống”. Chỗ ngừng dùng không nhận xe mới; khi có xe chỉ được cho xe ra hoặc xử lý theo quy trình.
- Thời gian nghiệp vụ lấy từ server, trình bày theo Việt Nam; không chuyển toàn bộ mô hình thời gian đang có trong đợt này. Các mốc ngày dùng khoảng đầu ngày bao gồm, đầu ngày tiếp theo không bao gồm.
- Chỗ có thể nhận xe phải trừ mọi cam kết còn hiệu lực nếu dữ liệu cũ còn reservation/allocation. Tắt menu không tự giải phóng chỗ đã cam kết.

### Phí: giữ đơn giản nhưng giải thích được

- HOURLY: `ceil(thời_gian_tính_phí / 3600) × đơn_giá`. DAILY: block 24 giờ, không phải cứ qua 00:00 là thêm một ngày.
- Thời gian 0 giây thu 0; thời gian dương tính ít nhất một block. Không thêm biểu phí đêm/cuối tuần hay thời gian miễn phí tùy ý trong bản lõi.
- Ví dụ dữ liệu demo, không phải giá vận hành: 5.000đ/giờ thì 59 phút = 5.000đ; 60 phút = 5.000đ; 60 phút 1 giây = 10.000đ. 50.000đ/24 giờ thì 24 giờ 1 giây = 100.000đ.
- Đề xuất nâng cấp: chốt bản giá/cách tính vào lượt khi nhận xe. Đổi giá chỉ áp dụng lượt mới; lưu phiên bản và giá trị sử dụng để in lại đúng căn cứ. Hiện tại code chọn giá active lúc tính và chặn thay giá đang dùng; không được tuyên bố đã có snapshot giá lúc vào.
- Đề xuất nâng cấp vé tháng: quyền lợi đến hết ngày đã chốt khi nhận xe; nếu ra quá hạn chỉ tính phần sau thời điểm hết hạn, không thu lại cả thời gian đã được bao phủ. Ví dụ vé hết 15/09, vào 23:00 và ra 00:30 ngày 16/09: tính 30 phút quá hạn → một block giờ. **Đây là thay đổi so với mã hiện tại đang tính cả lượt khi ra ngoài thời hạn.**
- Gia hạn được thanh toán trước nhận xe có thể nối các kỳ liên tục theo logic hiện có. Gia hạn sau nhận xe không ngầm sửa snapshot của lượt đang mở.
- Quote giữ 120 giây như hiện có; quá hạn thì xem lại phí. Giá tiền frontend gửi không quyết định số thu. Thu tiền, chứng từ và trả chỗ phải nhất quán; trường hợp miễn phí vẫn phải chống xác nhận lặp.

Các thay đổi giá/vé tháng phải có migration và phiên bản chính sách. Lượt đã hoàn tất giữ nguyên phí/chứng từ. Phiên cũ không đủ thông tin không được bịa snapshot; duy trì nhánh tương thích hoặc xử lý có xác nhận riêng.

### Thu tiền và báo cáo

- Ở giai đoạn lõi, demo thu tiền mặt; chuyển khoản thủ công phải có bằng chứng. Giai đoạn P5 thêm QR nhận tiền với provider, xác minh webhook/đối soát. QR mô phỏng phải ghi nhãn và không được coi là tiền ngân hàng đã nhận.
- Thu ròng trong kỳ = chứng từ thu phát sinh trong kỳ − chứng từ hoàn phát sinh trong kỳ. Tách tiền gửi lượt/vé tháng/tiền demo; không cộng lại `parking_fee` và chứng từ cho cùng khoản.
- Cao điểm theo lượt vào, theo lượt ra và theo tổng giao dịch là ba chỉ số khác nhau. Báo cáo phải nêu đang dùng chỉ số nào.
- Lấp đầy hiện tại = xe đang chiếm chỗ / số vị trí thuộc mẫu số được công bố, kèm thời điểm. Mẫu số bằng 0 thì không có tỷ lệ. Chưa có lịch sử năng lực chỗ thì không công bố phần trăm lấp đầy trung bình lịch sử; có thể báo số xe hiện diện theo giờ từ giao nhau của khoảng vào/ra.

## 6. Giao diện mục tiêu

Một menu chính theo công việc: **Tổng quan — Vào/ra — Sơ đồ bãi — Lượt gửi — Khách & vé tháng — Thu tiền & ca — Báo cáo — Trợ lý AI — Cấu hình**. Các mục hiển thị theo ma trận quyền.

- Nhân viên đăng nhập vào màn hình Vào/ra, thao tác bằng bàn phím được; có tìm biển/mã vé nhanh, danh sách xe đang gửi và báo lỗi sát trường.
- Quản lý đăng nhập vào Tổng quan, thấy số xe/chỗ theo khu, các cảnh báo và báo cáo đúng kỳ.
- Trả xe hiển thị rõ biển, giờ, thời lượng, vé tháng, quy tắc giá, số thu và nút xác nhận. Không gộp nút xem phí với thu tiền.
- Sơ đồ chỗ có cả chữ/biểu tượng trạng thái, không chỉ màu. Bấm chỗ có xe mở chi tiết; chỗ ngừng dùng có nhãn riêng.
- Thành công cập nhật ngay dữ liệu liên quan; lỗi giữ đầu vào; nút đang xử lý không gửi lặp. Mạng hỏng không hiện thông báo thu tiền thành công giả.
- Tải lại trang giữ bộ lọc/kỳ báo cáo hợp lý; không để kết quả AI kỳ cũ trông như kết quả kỳ vừa chọn.

## 7. AI có kiểm soát và đủ để bảo vệ đồ án

Luồng: CSDL → tổng hợp có phân quyền → payload định nghĩa chỉ số → Gemini → kiểm tra kết quả → lưu lịch sử → hiển thị cùng bảng số liệu gốc.

Payload gồm kỳ, múi giờ, số vào/ra theo ngày và giờ, giờ cao điểm, thu/hoàn, chỗ hiện tại và `as_of`, cờ dữ liệu demo, các mục còn thiếu. Không gửi biển số, tên khách, số điện thoại hoặc thông tin đăng nhập.

Ba nhiệm vụ rõ ràng:

1. **Báo cáo ngày/tuần:** tóm tắt, biến động, cao điểm, khuyến nghị; mọi con số đều đối chiếu được với payload.
2. **Hỏi đáp:** câu hỏi “Khu A còn mấy chỗ?” dùng snapshot hiện tại; “Tuần này giờ nào đông?” dùng kỳ được chọn. Câu hỏi vượt dữ liệu trả lời giới hạn đó.
3. **Nhân sự:** ưu tiên gợi ý tương đối và khung giờ. Chỉ hiển thị số người khi có tham số năng suất/nhân sự tối thiểu do quản lý cung cấp, ghi rõ giả định; không gọi đó là lịch tối ưu đã được đo.

Tuần hiện tại là **7 ngày kết thúc ngày chọn**. Tổng lượt cùng giờ của 7 ngày không phải lượt/giờ của một ngày. Cần thêm lượt ra theo từng giờ/ngày nếu muốn gợi ý tốt hơn; không suy ra “không cần nhân viên” từ 0 lượt vào.

Kết quả nên tách các phần tóm tắt, nhận xét, khuyến nghị, giới hạn và tham chiếu metric. Có thể dùng structured output khi model cấu hình hỗ trợ; schema đúng chỉ bảo đảm cấu trúc, không chứng minh con số đúng. Backend phải kiểm tham chiếu/giá trị dùng trong các trường có cấu trúc; phần văn bản vẫn phải được đối chiếu trong UAT. Không cam kết loại bỏ tuyệt đối ảo giác chỉ bằng prompt hoặc JSON schema.

Khi timeout/quota/lỗi/mất mạng: báo lỗi rõ, xem được báo cáo số liệu, cho thử lại có kiểm soát. Nếu dùng kết quả AI thật đã lưu để trình diễn khi mạng lỗi, ghi đúng thời gian/kỳ và nhãn “kết quả đã lưu”; không gọi đó là lượt sinh mới.

## 8. Lộ trình thực hiện

| Giai đoạn | Việc làm và file hiện có liên quan | Phụ thuộc | Nghiệm thu |
|---|---|---|---|
| P0 — Thống nhất bản một bãi | Bộ seed demo riêng; `system_router.py`, `site_scope.py`, `routers/api.py`, các router CRUD; `MainLayout.jsx`, `AppRoutes.jsx`, `SiteConfiguration.jsx` | Chốt phạm vi đã có | Một DB có đúng một bãi; manager cấu hình được tất cả mục lõi; staff bị chặn ghi trái quyền; UI/API không mâu thuẫn |
| P1 — Vòng đời và tiền | `parking_service.py`, `checkout_service.py`, `monthly_subscription_service.py`, `payment_service.py`, model/schema và migration mới; trang vé tháng/checkout/`SiteFinance.jsx` | P0 | Test biên phí/quá hạn/snapshot; retry; 2 yêu cầu giành chỗ; thu/hoàn/ca đối soát; hủy có lý do giữ lịch sử |
| P2 — Màn hình vận hành và AI | `SitesWorkspace.jsx`, `CoreAnalyticsPage.jsx`, `site_analytics.py`, `ai_service.py`, `analytics_models.py`, các trang báo cáo | Hợp đồng số liệu từ P1 | F06/F07/F09–F12 đủ hành trình; dữ liệu AI đúng quyền/kỳ; 3 nhóm AI live và ca rỗng/lỗi có bằng chứng |
| P3 — Đóng gói nghiệm thu | tests/backend/frontend/browser hiện có; `docs/AI_SDLC.md`, hướng dẫn deploy/demo; hồ sơ tài liệu theo yêu cầu sau | P0–P2 | F01–F13 đều có PASS gắn artifact; trình diễn 2 vai trò; cài mới và khôi phục được dữ liệu demo |

Không ấn định số ngày chắc chắn khi chưa triển khai. P0–P3 là cổng nghiệm thu lõi; sau đó P4 portal/gói/đặt chỗ → P5 QR/hóa đơn/đối soát → P6 camera OCR → P7 CV ô đỗ → P8 nghiệm thu tích hợp. Một API hoặc màn hình đã có thì sửa/nối lại trước khi tạo bản mới. Chi tiết phụ thuộc và tiêu chí nằm trong [EXTENSION_PLAN.md](EXTENSION_PLAN.md).

## 9. Kịch bản nghiệm thu và dữ liệu demo

Bộ dữ liệu đề xuất: một bãi, 3 khu, 40 vị trí (24 xe máy, 12 ô tô, 4 dự phòng/ngừng dùng), 2 tài khoản nghiệp vụ và một admin cài đặt; lịch sử tổng hợp 14 ngày để có ngày thường/cuối tuần/cao điểm. Đây là dữ liệu giả lập có nhãn, không phải số đo bãi thật. Có khách vé còn hạn/sắp hết/hết hạn và một kỳ rỗng. Seed vào DB mới, không ghi đè dữ liệu đang dùng.

Các ca phải có kết quả và artifact trước khi đánh dấu hoàn tất:

1. Manager cấu hình khu/chỗ/loại/giá và vé tháng; staff gọi cùng API ghi bị từ chối.
2. Nhận xe đúng loại; sai loại, thiếu giá, đầy bãi, biển đang trong bãi bị từ chối đúng.
3. Hai người nhận đồng thời vào cùng chỗ: đúng một lượt được tạo, không âm số chỗ.
4. Nhận/trả thành công cập nhật sơ đồ; request thất bại không để trạng thái dở.
5. Phí tại 0s, 3599s, 3600s, 3601s, 24h, 24h+1s; qua nửa đêm; sai thứ tự giờ.
6. Đổi bảng giá lúc có xe: lượt cũ theo bản đã chốt, lượt mới theo bản mới; lịch sử không bị tính lại.
7. Vé tháng còn hạn, hết hạn, liên tục và gia hạn sau vào; phần quá hạn theo đúng phiên bản chính sách.
8. Quote hết 120s, thay session, sửa số tiền, bấm hai lần và retry sau mất phản hồi: không thu sai/trùng.
9. Mất vé, hủy vào nhầm và điều chỉnh biển: đúng quyền, có lý do và lịch sử.
10. Mở/chốt ca, thu/hoàn, kiểm đếm lệch và in lại: đối chiếu được; không sửa chứng từ gốc.
11. Tìm biển/mã vé/ngày/trạng thái và phân trang; ngày cuối gồm đủ ngày Việt Nam.
12. Số vào/ra/thu/hoàn và peak khớp dữ liệu oracle đã tính trước cho bộ demo.
13. AI ngày/tuần, hỏi đáp, nhân sự trên cùng payload; tổng theo giờ cả tuần không bị gọi là tốc độ một ca.
14. AI kỳ rỗng, câu hỏi ngoài dữ liệu, prompt injection, provider lỗi và thiếu cấu hình: trả kết quả/giới hạn đúng; không lộ dữ liệu trái quyền.
15. Tắt mạng: CRUD cục bộ vẫn dùng được nếu chạy local; gọi AI báo lỗi/kết quả đã lưu có nhãn. Không giả định bản web hoạt động offline.
16. Cài mới, seed, backup và restore DB demo riêng; chạy lại kịch bản ngắn sau restore.

Trình diễn 10–15 phút: manager cấu hình/xem tổng quan → staff nhận hai loại xe → tìm/chỗ trống → vé tháng → trả xe và biên nhận → chốt ca → manager xem báo cáo và 3 nhiệm vụ AI → giới thiệu test/SDLC. Thời lượng là mục tiêu trình diễn, không phải số đã đo.

## 10. Bằng chứng SDLC phải bàn giao

| Giai đoạn | Bộ chứng cứ |
|---|---|
| KT1 | Yêu cầu gốc, câu hỏi/đáp nghiệp vụ, use case hai vai trò, ERD và giải thích các bất biến |
| KT2 | Prompt thực tế, thay đổi code tương ứng, diff/commit, lỗi phát hiện, test trước/sau khi có |
| KT3 | Phiên bản prompt, payload đã bỏ dữ liệu cá nhân, output AI thật, kiểm đối chiếu số; test mock ghi riêng |
| Cuối kỳ | Ma trận F01–F13, UAT, ảnh/video demo, hướng dẫn cài mới/sử dụng, báo cáo và slide |

Prompt mẫu viết lại phải gắn nhãn “tái lập”, không coi là log lịch sử. Hồ sơ Word/ảnh riêng tư vẫn ngoài Git theo quy tắc dự án. Không có phản hồi Claude để tính vào minh chứng; người dùng đã bỏ bước tham vấn này.

## 11. Kiến trúc, triển khai và phục hồi

- Một ứng dụng FastAPI với các module nghiệp vụ hiện có; frontend React gọi cùng backend. Giữ một nguồn tính phí và một nguồn tổng hợp báo cáo.
- SQLite cho bản local cài đơn giản; giữ PostgreSQL cho bản web nếu dùng. Không buộc người dùng đổi CSDL để làm đủ đề. SQLite chỉ có một writer tại một thời điểm; vì vậy vẫn cần các test tranh chấp và giao dịch, kể cả khi có hai trình duyệt. [SQLite isolation](https://www.sqlite.org/isolation.html).
- PostgreSQL có cơ chế khóa hàng để phối hợp truy cập; giữ cách khóa/constraint đã triển khai và kiểm thử trên môi trường được chọn, không suy kết quả SQLite sang PostgreSQL. [PostgreSQL explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- Không thêm Redis/Celery cho các lượt AI bấm sinh theo nhu cầu nếu chưa có vấn đề đo được. Giới hạn đang có theo tiến trình không tự trở thành giới hạn toàn hệ thống khi tăng worker. [FastAPI workers](https://fastapi.tiangolo.com/deployment/server-workers/).
- Kết quả AI có cấu trúc là lựa chọn triển khai cần kiểm tra model hỗ trợ; vẫn phải xác thực ý nghĩa dữ liệu. [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
- Migration theo kiểu thêm trường trước, đọc tương thích, chuyển luồng mới sau khi test; không bỏ guard giá/lịch sử trước khi có cơ chế thay thế. Chạy trên bản sao DB trước.
- Nếu có lỗi: rollback ứng dụng trong phạm vi schema tương thích; giữ chứng từ mới. Restore vào DB kiểm tra riêng trước, không phục hồi đè lên DB đã phát sinh giao dịch mà chưa đối soát.

## 12. Kết quả kiểm tra trong task lập phương án

Đã chạy lệnh trong `VERIFICATION.md`: **115 passed, 0 failed**, 37,49 giây, exit 0. Phạm vi gồm vào/ra, phí, chỗ trống, báo cáo theo kỳ, analytics theo bãi, snapshot quyền lợi vé tháng và hợp đồng quote. Fixture ép SQLite in-memory và chặn provider thật.

Không chạy lại toàn bộ backend/frontend, không UAT trình duyệt, không gọi Gemini hay kiểm tra website trong task này. Kết quả 115 test kiểm hợp đồng đang có, không chứng minh các chính sách nâng cấp ở mục 5 đã được thực hiện. Lịch sử AI live 09/09 trong tài liệu cũ không được gọi là lần nghiệm thu mới.

## 13. Kết luận thiết kế theo yêu cầu cập nhật

Giữ trọn phần lõi F01–F13; mở rộng E01–E08 theo từng giai đoạn và chạy lại kiểm thử lõi sau mỗi giai đoạn. Vẫn chỉ một bãi, nhưng có ba khu vực sử dụng: khách hàng, nhân viên và quản lý. Khách không được truy cập số liệu quản trị.

Các mẫu thực tế dùng để tham khảo hành trình: JustPark cho đặt/mua vé, Q-Park cho tài khoản–hóa đơn, SKIDATA và Futech iParking cho luồng làn/camera/thanh toán, Parquery cho theo dõi ô bằng camera. Nguồn và giới hạn ở [REAL_WORLD_REFERENCES.md](REAL_WORLD_REFERENCES.md); các quyết định áp dụng là thiết kế của ParkingAI, không phải tính năng đã được triển khai trong repo.

Tài khoản thanh toán/thiết bị camera sẽ được cấu hình khi tới bước tương ứng. Không cần chờ Claude hoặc thay đổi phạm vi một bãi. Việc triển khai sẽ theo `plan.md`; task hiện tại hoàn tất nghiên cứu và cập nhật phương án, chưa sửa mã ứng dụng.
