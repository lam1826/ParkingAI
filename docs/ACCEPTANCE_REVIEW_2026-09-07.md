# Nghiệm thu độc lập ParkingAI — 07/09/2026

Phạm vi: bản đồ án SQLite, mã tracked và untracked đang có trong workspace dựa trên `f9e80a6`. Bốn nâng cấp A–D và ba bản sửa đợt 2 đã tồn tại khi bắt đầu lượt này. Giữ các thay đổi đó, kiểm chứng lại, sửa các lỗi mới có tái hiện; không dùng số liệu kiểm thử cũ để kết luận bản cuối. Kết luận cuối và tổng kiểm thử nằm tại [cổng nghiệm thu](EXPANSION_RELEASE_GATE.md).

## 1. Lỗi đã xác nhận và sửa

| Mức độ | Điều kiện và sai lệch trước sửa | Nguyên nhân / xử lý | Mã và hồi quy |
| --- | --- | --- | --- |
| P2 | Xe đổi chủ; chủ mới đặt cùng xe vào vị trí đang được bảo đảm cho chủ cũ, rồi nhận xe qua đặt chỗ. Nhận xe trực tiếp bị chặn nhưng đặt chỗ tạo được đường vòng | Miễn xung đột theo `vehicle_id` mà thiếu `customer_id`. Kiểm tra cùng xe và cùng khách ở cả tạo đặt chỗ và nhận xe; đặt chỗ cũ sai quyền cũng không dùng để vào được | `backend/expansion/reservations.py`; `tests/test_acceptance_security.py`: chủ mới bị 409, cùng chủ vẫn được nhận xe, hủy quyền cũ cho phép đặt mới, chặn dữ liệu đặt chỗ cũ |
| P2 | API danh mục gói vé/loại xe lỗi làm mất hồ sơ và toàn cổng khách; API yêu cầu thêm xe lỗi làm mất danh sách xe đã duyệt | `Promise.all` ghép các nguồn không phụ thuộc. Tách hồ sơ, danh mục, xe và yêu cầu; lỗi/retry riêng, khóa biểu mẫu thiếu danh mục, không coi lỗi tải là danh mục rỗng | `frontend/src/pages/Expansion/CustomerPortal.jsx`; ba tình huống component thật trong `tests/browser/remote_hook_regression.py` |
| P2 | Đang mở một đơn, tải lại danh sách đơn lỗi: cổng khách có thể crash với `Cannot read properties of null (reading 'find')` | `mergeSelectedOrder` nhận `orders.data=null` nhưng gọi `.find` trực tiếp. Dùng chi tiết đơn đã tải khi danh sách lỗi; đơn hoàn tất vẫn loại QR/token, không làm trạng thái lùi về pending | `frontend/src/pages/Expansion/portalState.js`; test mới trong `portalState.test.js`, RED 1 lỗi rồi GREEN 4/4 tại `acceptance-current/portal-order-*.log` |
| P2 | API nhân sự hoặc nhóm xe lỗi khiến loại xe không chọn được dù phần xe vào/ra vẫn hoạt động | Danh mục nhận xe bị ghép với quản trị nhân sự/nhóm. Tách từng nguồn và retry riêng; kiểm tra loại xe/vị trí đã tải trước nhận xe | `frontend/src/pages/Expansion/SitesWorkspace.jsx`; hai tình huống browser trong `workspace_sections_regression.py` |
| P2 | API chỗ trống lỗi làm mất lịch đặt chỗ khách và nút hủy | Hồ sơ và chỗ trống cùng một lần tải. Tách nguồn; giữ lịch/hủy và chỉ làm mới lịch cùng sức chứa sau hủy | `frontend/src/pages/Expansion/ReservationsPage.jsx`; browser lỗi availability, hủy thành công và đếm đúng request |
| P3 | Năm API danh sách đặt chỗ/phân bổ/chờ chấp nhận khoảng lọc rỗng hoặc đảo đầu/cuối với HTTP 200, có thể vẫn trả dữ liệu | Chuẩn hóa múi giờ trước so sánh; trả 422 khi `to_at <= from_at`; giữ quy tắc giao khoảng `[from_at,to_at)` | `backend/expansion/site_router.py`; `tests/test_acceptance_booking_fleet.py`: 10 ca khoảng sai, 5 ca múi giờ/giao khoảng |
| P3 | Id ảnh bãi đã đóng trả 404 nhưng nội dung khác id không tồn tại | Chuẩn hóa cả 403 và 404 từ kiểm tra bãi về cùng thông báo không tìm thấy ảnh | `backend/expansion/vision_router.py`; `tests/test_acceptance_security.py`: status và JSON giống nhau ở đọc ảnh/duyệt/xóa, bãi mở và đóng |
| P3 | Báo cáo đội xe lỗi có cảnh báo nhưng không có cách thử lại tại phần đó | Bổ sung retry dùng remote hiện tại | `frontend/src/pages/Expansion/FleetSection.jsx`; browser làm lỗi rồi thử lại, báo cáo hồi phục |

Đây là lỗi được tái hiện ở bản đầu vào của lượt nghiệm thu này. Bảy bản sửa đợt 1 và ba bản sửa đợt 2 được giữ trong lịch sử [review Claude](CLAUDE_REVIEW_RESPONSE.md); không tính lại thành lỗi mới.

## 2. Đối chiếu tiêu chuẩn và đặc tả

**Tiêu chuẩn mã/dữ liệu:** giữ kiến trúc và thư viện, giới hạn chỉnh sửa vào dịch vụ quyền giữ chỗ, kiểm tra bộ lọc, phản hồi ảnh và bốn component giao diện. Không đổi migration đã có để che lỗi dịch vụ; không sửa dữ liệu đang sử dụng. Bộ thử tranh chấp dùng transaction/kết nối độc lập, không lấy mock tuần tự làm bằng chứng khóa. Browser giả lỗi ở ranh giới HTTP vẫn chạy React và component thật.

**Đặc tả A:** kiểm thử đủ năm API, mỗi tập sau lọc vẫn hơn 100 mục (120/240 bản ghi, hai bãi, nhiều khách), thứ tự có khóa phụ và hợp các trang đúng tập được cấp quyền. Kiểm tra biên múi giờ và khoảng sai. Browser đi đến trang 5/mục 101, đổi trạng thái về trang đầu, chỉ tải danh sách liên quan và đổi bãi không nhận phản hồi cũ.

**Đặc tả B:** giữ DTO tường minh 8 trường; kiểm tra chính xác tập khóa, tổng toàn bộ 125 lượt qua 4 trang. Quyền nhóm/bãi/thời điểm tham gia được kiểm tra trong các bài cũ và lượt toàn bộ. Tổng phí là phí lượt gửi, chưa trừ hoàn, không gồm đơn vé tháng DEMO; giảm trường dư không được gọi là vá IDOR.

**Đặc tả C:** các lỗi ghép API còn sót đã sửa như bảng trên. Browser kiểm tra retry riêng, nhận xe từ đặt chỗ tải lại lịch/chỗ trống/phiên, đổi bộ lọc khi mutation cũ hoàn thành, đổi bãi nhanh và phân trang. UAT toàn hệ thống kiểm tra đơn/vé/chứng từ cập nhật, logout/login khách khác khi request cũ trả muộn. Kiểm tra mobile là viewport, không phải điện thoại vật lý.

**Đặc tả D:** giữ các trường giờ có xe vào/ra, giờ điền 0, cảnh báo lịch sử thưa và tuần tham chiếu. Không có nhật ký nguồn ghi nhận nên `observation_completeness=unknown`; không suy giờ không có bản ghi thành mất dữ liệu hay thật sự vắng xe. Bộ thử bao gồm rỗng, thưa, nhiễu, múi giờ và tương lai; UAT đối chiếu số giờ có xe + giờ điền 0 bằng cửa sổ và nhãn “Chưa xác định”. Dữ liệu tổng hợp không chứng minh độ chính xác trên bãi thật.

## 3. Bằng chứng tái hiện và kiểm tra phạm vi

- A/B: `backend/artifacts/acceptance-spec/new-red.xml` có 10 lỗi khoảng lọc; `green.xml` đạt 73 bài liên quan, gồm 21 bài mới.
- Quyền ảnh: `backend/artifacts/acceptance-security/object-red.xml`; quyền bảo đảm chỗ: `allocation-guards-red.xml`; sau sửa `fixes-green.xml` đạt 63 bài liên quan.
- Tranh chấp chuyển chủ giữa lần đọc quyền và lần ghi đầu tiên: `owner-transfer-race.xml`, hai kết nối SQLite thật; cập nhật chủ đã commit, yêu cầu cũ trả 409, không có đặt chỗ được tạo. Không xác nhận lỗi mới và không thêm sửa theo suy đoán.
- Portal: RED `backend/artifacts/review-remote/2c34ed6cb5/result.json`; GREEN cuối `9b27169a41/result.json`, 5/5 kịch bản gồm hai hồi quy hook được giữ.
- Workspace/đặt chỗ/đội xe: RED `backend/artifacts/workspace-sections/fae549ad13/result.json`; GREEN `cd87016113/result.json`, 6/6 kịch bản, 4 ảnh, không runtime exception.
- Toàn bộ pytest và frontend cuối: `backend/artifacts/acceptance-current/backend-final.xml`, `backend-final.log`, `frontend-test.log`, `frontend-lint.log`, `frontend-build.log`.

Các nhóm kiểm thử có giao nhau, không cộng các lượt chọn lọc vào tổng toàn bộ. Hai runner hồi quy trình duyệt (11 kịch bản) chạy riêng ngoài pytest và bộ frontend. Artifact chạy thử được giữ cục bộ, không đưa vào snapshot source nộp; runner và test được đồng bộ.

## 4. Nghi vấn và giới hạn

Không xác nhận lỗ hổng mới từ tình huống chuyển chủ trước lần ghi: guard SQLite đã rollback đúng. Các đường API/handler đã kiểm tra; khả năng chèn SQL trực tiếp trái hợp đồng không được coi là một đường vượt quyền API. Các bảng cũ có đặt chỗ sai chủ bị chặn tại nhận xe, không tự sửa lịch sử của người dùng.

PostgreSQL thực, quyền POSIX trên Windows, tiền ngân hàng, camera video, thiết bị điện thoại vật lý, tải bãi thật và độ chính xác biển Việt Nam chưa được nghiệm thu ở lượt này. Không push/deploy, không đổi DB hoặc cấu hình hiện có. Nghiệm thu SQLite không chứng minh cơ chế khóa PostgreSQL.

## 5. Tái lập

Tại thư mục dự án, chạy `.venv/Scripts/python.exe -m pytest -q --junitxml=backend/artifacts/acceptance-current/backend-final.xml`; tại `frontend` chạy `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`. Ba runner từ thư mục dự án: `tests/browser/remote_hook_regression.py`, `tests/browser/workspace_sections_regression.py`, `tests/browser/expansion_uat.py` bằng Python của dự án.

Runner trình duyệt dùng Chrome cục bộ và profile riêng. Hai runner component chạy Vite ở cổng 18970/18974; UAT dùng bản build ở 18960 và tạo DB mới mỗi lần. UAT nhận diện cần model/ảnh mẫu đã tải theo [hướng dẫn demo](DEMO_GUIDE.md); không gọi ngân hàng hoặc sửa DB hiện có. Kết quả lỗi do bộ chọn DOM của bài thử phải được phân biệt với lỗi sản phẩm; không giảm điều kiện nghiệm thu để có kết quả đạt.


## 6. Chốt bằng chứng cuối

Backend 1.141 đạt/7 bỏ qua/0 lỗi; frontend 130 đạt, lint/build exit 0; 11 kịch bản React và 9/9 nhóm UAT tại `backend/artifacts/uat/771c6a2fe6/summary.json`, 12 ảnh, không lỗi JavaScript/console/cảnh báo. Ảnh desktop/mobile đã đọc; mobile là viewport 390×844. Word 103/15 trang được render/QA, snapshot 444 file; xem `backend/artifacts/acceptance-current/verification.json` và manifest Word.

Vòng UAT `d15608f7d6` đạt 7/9: bộ chọn icon dùng thuộc tính chỉ có ở development và bước mobile thiếu login nhân viên sau ca đổi tài khoản. Vòng `540bf63a62` đạt 5/9: assertion mới đòi QR còn hiện sau fulfilled trái hợp đồng hiện có, kéo theo chưa gửi/duyệt hoàn và checkout vẫn được vé tháng; một bước đọc DOM quá sớm sau điều hướng. Sửa harness: dùng nút thật trong thanh công cụ, login đúng vai trò, chờ body và khẳng định QR/token bị bỏ khi đơn hoàn tất. Không đổi sản phẩm hoặc giảm yêu cầu vì các lỗi harness này. Bản cuối 9/9 đạt trên DB mới; có kiểm tra vé/chứng từ cập nhật không refresh trang và XHR tài khoản cũ thật sự trả sau login mới.

Riêng lỗi `.find(null)` là lỗi sản phẩm có RED độc lập; đã sửa và chạy lại toàn bộ frontend/build trước UAT cuối. Không sửa backend sau lượt full pytest. Không tăng skip, không bỏ assertion kiểm tra quyền/tiền hoặc bỏ bài thử để đạt.
