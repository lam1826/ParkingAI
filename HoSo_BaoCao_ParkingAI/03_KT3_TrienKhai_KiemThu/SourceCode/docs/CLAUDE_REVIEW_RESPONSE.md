# Đối chiếu và xử lý review Claude — 07/09/2026

**Lượt nghiệm thu độc lập mới nhất:** xem [bản review A–D và lỗi sửa bổ sung](ACCEPTANCE_REVIEW_2026-09-07.md) cùng [cổng nghiệm thu](EXPANSION_RELEASE_GATE.md). Nội dung các đợt 1–2 bên dưới được giữ làm lịch sử; số test và UAT của chúng không thay cho bằng chứng bản cuối.

Người dùng yêu cầu kiểm chứng rồi sửa các lỗi đã xác nhận. Phạm vi là bản đồ án SQLite cục bộ, dựa trên mã đang làm việc tại mốc Git `f9e80a6`; kiểm thử dùng database hoặc trình duyệt riêng. Không suy từ một nhận định trong review thành lỗi đã xác nhận nếu chưa có đường tái hiện hoặc bằng chứng mã tương ứng.

## 1. Các lỗi đã tái hiện và sửa

| Lỗi / điều kiện kích hoạt | Xử lý đã triển khai | Hồi quy |
| --- | --- | --- |
| Cấp chỗ sau giờ bắt đầu của danh sách chờ có thể trả 422 do hai lần đọc đồng hồ | Lấy một thời điểm server sau khi khóa yêu cầu, dùng cùng giá trị để chốt giờ bắt đầu và kiểm tra cửa sổ; yêu cầu hết hạn vẫn bị từ chối | `tests/test_review_waitlist_regressions.py`: đồng hồ thật, đồng hồ tiến giữa lời gọi, giờ tương lai, hết hạn, retry và cạnh tranh |
| API tạo khu cũ tạo `site_id=NULL` trong DB nhiều bãi; readiness bỏ sót, rollout sau đó dừng | Không có bãi: giữ tương thích; một bãi: tự gắn bãi; nhiều bãi tính cả bãi đóng: trả 409. SQLite readiness thường/sâu và PostgreSQL kiểm tra dữ liệu sâu cùng kiểm tra bất biến | `tests/test_review_zone_regressions.py`: 0/1/nhiều bãi, bãi đóng, API, readiness, nâng cấp bản sao và bảo toàn nguồn |
| API v1 nhận xe không chọn vị trí bỏ qua vé portal và tạo phiên không có vị trí | Khi có ít nhất một bãi, từ chối thiếu vị trí bằng 422 trước tác dụng phụ; chọn đúng bãi áp dụng vé, khác bãi không miễn phí | `tests/test_review_portal_legacy_regressions.py`: 0/1/2 bãi, đúng/sai bãi |
| Gia hạn vé portal bằng API vé tháng cũ tạo kỳ mới không có phạm vi bãi | Từ chối tạo kỳ mới bằng 409, hướng khách về portal; không tạo kỳ/phiếu thu. Retry khoản gia hạn đã ghi thu vẫn trả chứng từ lịch sử | Cùng file hồi quy portal: chặn gia hạn mới và giữ kết quả thu cũ |
| Xác nhận xe đến sát hạn có thể đã commit phiên nhưng trả lỗi vì đặt chỗ chưa được liên kết | Dùng một thời điểm sau khóa vị trí; trì hoãn commit đến khi phiên, quyền lịch sử và đúng đặt chỗ đã liên kết. Bất kỳ lỗi liên kết nào đều rollback toàn bộ | Hồi quy waitlist/arrival: trước hạn, đúng hạn, lỗi liên kết phiên, slot/session/reservation cùng rollback |
| Vị trí đổi sang bãi khác giữa kiểm tra quyền và nhận xe | Truyền bãi đã được cấp quyền xuống dịch vụ; đọc lại phạm vi, giữ khóa và thêm điều kiện bãi khi chiếm vị trí trong giao dịch | Hồi quy waitlist/arrival: đổi bãi trước khi dịch vụ đọc và ngay trước khi chiếm vị trí |
| Thao tác lưu bắt đầu ở bộ lọc A, chuyển sang B rồi thao tác A hoàn thành: trang tải mãi | Hàm tải lại ổn định và luôn dùng bộ lọc hiện tại; giữ cơ chế bỏ kết quả trả muộn | `tests/browser/remote_hook_regression.py`: React thật, hook sản phẩm, giữ dữ liệu B và kết thúc loading |

Không dùng khoảng dung sai để che lỗi đồng hồ. Cách sửa v1 chặt hơn gợi ý suy ra bãi duy nhất trong review: chỉ suy ra bãi cho vé vẫn để lại phiên không có vị trí và không kiểm soát được sức chứa. Client phải cung cấp vị trí khi hệ thống đã quản lý bãi; database legacy chưa có bãi giữ tương thích.

## 2. Bằng chứng trước và sau sửa

Các artifact dưới đây nằm ngoài snapshot source để tránh đưa database, ảnh và nhật ký chạy thử vào hồ sơ mã nguồn. Các bài hồi quy được giữ trong `tests/` để chạy lại.

| Nhóm | Bằng chứng |
| --- | --- |
| Khu / readiness | `backend/artifacts/review-standards/zone-red.xml`: 7 lỗi trước sửa; `zone-green.xml`: 80 test nhóm đạt sau sửa |
| Danh sách chờ / xác nhận đến / phạm vi bãi | `backend/artifacts/review-waitlist-green.xml`: 46 test nhóm đạt sau các bước tái hiện lỗi đồng hồ, liên kết phiên và đổi bãi |
| Xe vào / vé tháng | `backend/artifacts/review-core-checkin.xml`: 49 test nhóm đạt; các bài portal legacy nằm trong lượt pytest toàn bộ |
| Tải lại giao diện | Trước sửa: `backend/artifacts/review-remote/4e2733d3c5/result.json` trả `{data:null, loading:true}`; sau sửa: `review-remote/e1ba10bec9/result.json` trả `{data:"B", loading:false}` |
| Trình duyệt sau sửa | `backend/artifacts/uat/df03cc731b/summary.json`: 8/8 nhóm đạt, 0 lỗi JavaScript/console hoặc cảnh báo; 11 ảnh desktop/mobile không tràn ngang |

Các nhóm kiểm thử có phần giao nhau, không cộng các số trên thành tổng test. Bài trình duyệt `remote_hook_regression.py` chạy riêng, không nằm trong 129 bài frontend hoặc pytest. Kết quả toàn bộ backend, lint/build và bàn giao được chốt ở [Trạng thái triển khai](EXPANSION_IMPLEMENTATION_STATUS.md) và [Cổng kiểm tra bàn giao](EXPANSION_RELEASE_GATE.md).

Lượt toàn bộ đầu sau sửa đạt 1.085 bài, bỏ qua 7 và có một assertion cũ chưa liệt kê tham số `expected_site_id` mới trong lời gọi chiếm vị trí (`post-review-backend-tests.xml`). Đã bổ sung đúng tham số kỳ vọng này, giữ nguyên HTTP 409 và các assertion cũ; bài đó đạt khi chạy riêng. Mã sản phẩm không thay đổi vì lỗi assertion này. Nhật ký lượt chạy toàn bộ sau cập nhật nằm tại `backend/artifacts/post-review-final-backend-tests.log` và `.xml`.

Trên môi trường Windows dùng để phát triển, chạy hồi quy trình duyệt bằng `.venv/Scripts/python.exe tests/browser/remote_hook_regression.py` tại thư mục dự án. Cần Node trên PATH, dependencies frontend đã cài, thư viện `websockets` và Chrome tại đường dẫn mặc định. Runner dùng cổng 18970/18972 cùng hồ sơ Chrome riêng, tự dừng các tiến trình của nó; không cần database hoặc đăng nhập.

## 3. Những nhận định cần giữ đúng mức bằng chứng

- Lỗi đồng hồ waitlist có thật, nhưng từ “luôn” trả 422 quá tuyệt đối: độ phân giải đồng hồ có thể khiến hai lần đọc trùng nhau. Hồi quy dùng cả đồng hồ thật và đồng hồ tiến để kiểm tra nguyên nhân ổn định.
- Camera/OCR và viewport điện thoại chưa được Claude thử trong lượt review của họ. Đợt kiểm chứng lại đã chạy upload qua model thật và giao diện 390×844; OCR vẫn đọc sai, cần người duyệt. Đây không phải nghiệm thu điện thoại vật lý hoặc đo độ chính xác biển Việt Nam.
- Worker portal tự chạy mỗi 30 giây trong `demo_server.py`. Cấu hình triển khai ngoài bộ demo chưa có lịch chạy tương đương; phải bổ sung trước vận hành thật.
- Nghi vấn `_notify` làm hỏng giao dịch chưa có đường tái hiện qua API hiện tại: các caller cùng mã sự kiện khóa thực thể nghiệp vụ trước ghi, router và worker rollback khi lỗi. Chưa thay bằng upsert chỉ dựa trên giả thuyết này; PostgreSQL thực vẫn cần kiểm tra đồng thời riêng.
- Sáu bài PostgreSQL thực chưa chạy. SQL offline và thử truy vấn dùng chung trên SQLite không chứng minh khóa/trigger/migration đúng trên PostgreSQL thật. Giới hạn này được đặt cạnh phạm vi bàn giao và ghi riêng trong bảng kiểm chứng.
- Dự báo lấp các giờ không có lượt bằng 0 là giả định hiện tại. Hệ thống chưa phân biệt giờ không có xe với giờ mất dữ liệu; chất lượng dự báo trên bãi thật và cảnh báo độ phủ theo giờ là phần phát triển tiếp.
- Tải lại nhiều danh sách cùng lúc, trang lịch sử giới hạn 100 mục, form hết hiệu lực nếu để quá giờ và thu hẹp trường trả về của báo cáo đội xe là các điểm cần cải thiện. Không đánh đồng chúng với lỗi giao dịch hoặc quyền chéo khách đã tái hiện ở mục 1.
- Báo cáo đội xe có trả thừa cột nội bộ (mã nhân viên, mã vé, hash báo giá); cần thu hẹp trường trả về khi hoàn thiện API. Kiểm tra hiện tại có giới hạn thành viên, bãi và thời điểm xe tham gia nhóm; chưa tìm thấy đường đọc xe ngoài quyền hoặc dùng hash thay token báo giá đã ký.

## 4. Đợt 2 ngày 07/09/2026: kiểm chứng bản sửa, review giao điểm và bốn nâng cấp

### 4.1. Kiểm chứng bảy nhóm sửa

Ba file hồi quy `tests/test_review_waitlist_regressions.py`, `test_review_zone_regressions.py`, `test_review_portal_legacy_regressions.py` chạy lại: 28 đạt. Ba reproduction độc lập của lượt review đầu (đồng hồ thật khi cấp chỗ, khu legacy trong DB nhiều bãi, v1 nhận xe không vị trí) được chạy lại trên mã đã sửa: bài đồng hồ thật nay đạt; hai bài còn lại chuyển sang hợp đồng mới đúng như tài liệu (409 khi tạo khu qua API cũ có từ hai bãi, 422 khi v1 nhận xe không chọn vị trí). Không hoàn tác bản sửa nào.

### 4.2. Lỗi xác nhận thêm và đã sửa

| Lỗi / điều kiện | Xử lý | Hồi quy |
| --- | --- | --- |
| Đặt chỗ của chủ xe cũ chặn chủ xe mới đã xác minh đặt chỗ cùng khung giờ (`reserve` kiểm tra trùng theo `vehicle_id` mà không xét `customer_id`); chủ mới không hủy được, chủ cũ không đến được | Kiểm tra trùng khung giờ chỉ với đặt chỗ của chính chủ hiện tại; hàng của chủ cũ vẫn giữ vị trí của nó ở kiểm tra mức vị trí | `tests/test_review2_regressions.py::test_previous_owner_booking_no_longer_blocks_verified_new_owner` |
| Nhân viên bãi A gọi ảnh của bãi B nhận 403, id ngẫu nhiên nhận 404: lộ việc tồn tại id ảnh | `_observation` trả 404 đồng nhất cho ảnh ngoài phạm vi | `test_foreign_site_observation_id_is_indistinguishable_from_missing` |
| Đơn tạo trước 0h, mô phỏng thành công sau 0h nhưng còn trong hạn đơn → `start_date_passed`, vào xét duyệt và quản lý không thể duyệt (409), chỉ có thể từ chối | `_fulfillment_problem` nhận thời điểm nhận kết quả; ngày bắt đầu chỉ bị coi là đã qua khi kết quả đến sau hạn đơn. Kết quả muộn vẫn vào xét duyệt `late_payment` | `test_demo_result_inside_validity_window_survives_midnight`, `test_demo_result_after_expiry_still_goes_to_review_and_manager_can_reject`, `test_review_for_on_time_result_can_be_approved_even_days_later` |

Các điểm cùng lượt review chưa sửa vì là chính sách đã thống nhất hoặc cần quyết định sản phẩm: xe đã đến rồi ra sớm không vào lại chính vị trí bằng cùng mã (đã ghi trong giới hạn); bảo đảm chỗ bọc ngoài một đặt chỗ cùng xe tạo trước bị 409 (bất đối xứng, không mất dữ liệu); đơn thu tại bãi cũng hết hạn sau 15 phút; đơn xét duyệt do kết quả muộn chỉ quản lý mới gỡ được; retry sự kiện không có trần số lần. Các mục này nằm trong backlog ở tài liệu trạng thái.

### 4.3. Bốn nâng cấp

| Nâng cấp | Thực hiện | Nghiệm thu |
| --- | --- | --- |
| A. Lọc và phân trang đặt chỗ tại server | `GET /me/reservations`, `/me/waitlist`, `/sites/{id}/reservations`, `/allocations`, `/waitlist` nhận `site_id`/`status`/`vehicle_id`/`from_at`/`to_at`/`limit`/`offset`; quyền và phạm vi bãi lọc trước trang; thứ tự `start_at`(hoặc `created_at`) rồi `id`; giữ dạng mảng trả về. Trang khách và trang bãi đọc trang 25 mục, đổi bộ lọc về trang đầu | `tests/test_expansion_booking_pagination.py` (9 bài): 130 đặt chỗ + 15 phân bổ + 120 chờ xen kẽ hai bãi, hai khách; hợp các trang bằng đúng tập lọc, không trùng, không lộ khách khác, bãi không có quyền 403, tham số sai 422. UAT trình duyệt: trang 2 lượt gửi khác trang 1; đổi bộ lọc về trang 1; đặt chỗ mới hiện sau POST 201 với `site_id` lọc tại server |
| B. Thu hẹp báo cáo đội xe | `fleet_summary` trả DTO 8 trường cho từng lượt (không mã nhân viên, vé, hash báo giá); tổng lượt/đang đỗ/hoàn tất/tổng phí bằng SQL trên toàn phạm vi được cấp quyền; phân trang `limit`/`offset`; `fee_note` nói rõ tổng phí lượt gửi chưa trừ hoàn và không gồm thanh toán vé tháng (chứng từ DEMO là chứng từ vé tháng) | `tests/test_expansion_fleet_report.py` (8 bài): tập khóa chính xác, khóa cấm không xuất hiện, tổng trên 7 lượt khi trang 3, loại lượt trước khi vào đội và lượt ở bãi khác, khách ngoài nhóm/nhân viên bãi khác 403. Không tuyên bố vá IDOR |
| C. Tải và thử lại riêng từng phần | `useRemote` giữ nguyên; thêm `usePage`, `refreshAll`, `RemoteSection`, `combineRemotes`. Trang bãi tách danh mục, chỗ trống, lượt gửi, đặt chỗ, phân bổ, chờ; cổng khách tách hồ sơ, xe, vé, đơn, lịch sử, chứng từ, thông báo, hoàn; trang đặt chỗ tách nền/đặt chỗ/chờ. Mutation làm mới đúng phần phụ thuộc | `tests/browser/remote_hook_regression.py` 2 kịch bản đạt (reload muộn sau đổi bộ lọc; một phần lỗi, phần khác giữ dữ liệu, thử lại riêng, `refreshAll` tải lại đúng một lần mỗi phần). UAT trình duyệt: chặn riêng API danh sách chờ → phần đó báo lỗi có Thử lại, đặt chỗ vẫn hiện; gỡ chặn → Thử lại hồi phục; nhận xe cập nhật lượt và chỗ trống; đổi bãi A→B→A nhanh không lẫn dữ liệu; thanh toán mô phỏng cập nhật vé/chứng từ không cần làm mới; đăng xuất/đăng nhập tài khoản khác không giữ dữ liệu cũ |
| D. Minh bạch chất lượng dữ liệu dự báo | `coverage` thêm `hours_in_window`, `hours_with_arrivals`, `hours_with_departures`, `hours_zero_filled`, `observation_completeness="unknown"`, `completeness_note`, `sparse_history`; mỗi dự báo có `samples_observed`/`samples_zero_filled`; giao diện có khối Độ phủ dữ liệu | `tests/test_expansion_forecast.py` thêm 5 bài (rỗng, thưa, dày, nhiễu, mốc múi giờ), `test_expansion_insights_api.py` thêm 1; UAT: 392/1354 giờ có bản ghi, mức đầy đủ "Chưa xác định" trên dữ liệu tổng hợp |

### 4.4. Review lại ngày 08/09/2026 trên bản đã commit (`026e692`)

Chạy lại trên bản commit: toàn bộ pytest, frontend test/lint/build, hai runner hook trình duyệt và kiểm tra snapshot (kết quả ở tài liệu trạng thái). Lỗi mới có tái hiện: `scripts/start_demo.ps1` không có BOM UTF-8 trong khi chứa chuỗi tiếng Việt, nên Windows PowerShell 5.1 (bản mặc định của Windows; máy demo không có PowerShell 7) báo `The string is missing the terminator` và không khởi động được — đúng nội dung `backend/artifacts/demo/production-deploy.err.log` lúc 07:36 ngày 08/09. Đã thêm BOM (parser 5.1 trả 0 lỗi, script chạy được) và bài `tests/test_demo_server.py::test_powershell_scripts_with_vietnamese_text_carry_a_utf8_bom` bắt buộc mọi `.ps1` có ký tự ngoài ASCII phải giữ BOM. Hai script còn lại (`database_guard.ps1`, `verify.ps1`) đã có BOM.

### 5. Hướng phát triển sau bản sửa

Bốn nâng cấp phân trang/lọc đặt chỗ tại server, DTO đội xe, tải từng phần và độ phủ dữ liệu dự báo đã được triển khai, sau đó kiểm tra bổ sung trong lượt nghiệm thu độc lập. Khi chuyển sang vận hành thật, cần PostgreSQL integration, lịch worker có giám sát, diễn tập migration/backup/restore, thử thiết bị điện thoại và làm rõ giấy phép model. Thanh toán ngân hàng và camera video liên tục vẫn ngoài phạm vi đồ án đã thống nhất.

Các thay đổi hiện ở workspace và bản source bàn giao; việc sửa lỗi này không đồng nghĩa đã đẩy Git hoặc thay website triển khai bên ngoài.
