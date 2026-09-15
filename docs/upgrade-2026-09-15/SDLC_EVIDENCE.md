# Minh chứng AI trong SDLC — đợt nâng cấp 15/09/2026

Tài liệu này ghi các quyết định/mã/test/output thực của đợt nâng cấp một bãi. Không có phản hồi Claude: người dùng đã bỏ bước tham vấn. Các câu nhắc viết lại để tái lập dưới đây không phải bản chép prompt lịch sử.

## KT1 — phân tích và thiết kế

Đầu vào là yêu cầu gốc F01–F13 và phần mở rộng E01–E08 đã được phê duyệt. Kết quả: [PROPOSAL.md](PROPOSAL.md), [EXTENSION_PLAN.md](EXTENSION_PLAN.md), [tham khảo website thật](REAL_WORLD_REFERENCES.md), ma trận quyền và [hợp đồng phí/ngoại lệ](BILLING_AND_EXCEPTIONS.md).

Các quyết định đã áp dụng: một bãi nhiều khu; giá chốt khi nhận; quá hạn vé tháng chỉ tính phần ngoài coverage; hủy giữ lịch sử; sửa biển tạo vé thay thế; snapshot cũ không đủ dữ liệu giữ NULL; vé mua, đặt chỗ, lượt gửi và tiền là các thực thể khác nhau.

Prompt tái lập: “Đối chiếu các bất biến một xe/một chỗ/một lượt, quyền manager–staff và giá lịch sử. Thiết kế migration giữ chứng từ cũ, xác định trường hợp không đủ dữ liệu để suy ra giá lúc vào.”

## KT2 — code và vòng sửa

| Vấn đề thực phát hiện | Code áp dụng | Minh chứng kiểm thử |
|---|---|---|
| Staff nhận tổng tài chính qua AI/history/fleet | Scoped analytics và kiểm quyền trước/sau provider/history/replay | 8 hồi quy quyền RED→GREEN; `test_core_analytics_permissions.py` |
| Đổi giá làm mất căn cứ lúc vào; quá hạn vé tháng tính lại phần được bao phủ | `core/billing.py`, snapshot model/guards/migration, CheckoutService dùng snapshot | `test_billing_snapshot.py`, migration/concurrency, HTTP thay giá5000→9000→12000 |
| Hủy lượt phải giữ lịch sử và không bị đếm vào lưu lượng | SessionExceptionService/event guards; analytics loại cancelled | 8 lỗi count/nhãn được tái hiện trước sửa; `test_cancelled_analytics.py` |
| Thử lại xử lý mất vé sau checkout không được mở lại thu tiền | Replay trả trạng thái hiện tại; UI nhận completed | Exception/replay tests và frontend late-response tests |
| Test import trong thư mục cô lập chưa copy module guard mới | Fixture copy cả dependency thuần của database.py | Tái hiện ModuleNotFoundError; giữ assertion không tạo thư mục/DB |

Prompt tái lập: “Tạo ca tranh chấp bằng hai kết nối cho hủy/sửa biển và trả xe; kiểm trạng thái cuối, số chỗ và chứng từ. Giữ nguyên hành vi các lượt legacy, không sửa dữ liệu lịch sử để làm test đạt.”

Các file/diff ở working tree chưa commit; Git base `3ef172e`. Manifest P0 và P1 trong `backend/artifacts` ghi hash mã ở từng mốc. Kết quả chi tiết và số test không trùng tổng tại [IMPLEMENTATION.md](IMPLEMENTATION.md).

## KT3 — prompt, số liệu và AI thật

Prompt đang chạy được dựng ở `backend/services/ai_service.py::generate_scoped_analysis` bằng `_build_grounded_qa_prompt`. Nội dung chính: chỉ dùng JSON được cấp quyền, câu hỏi là dữ liệu không tin cậy, phân biệt lượt vào/ra/tổng giao dịch, dữ liệu lịch sử với chỗ hiện tại, tổng cộng dồn tuần với tốc độ một ca, không suy định biên khi thiếu năng suất.

Luồng input: `site_analytics.summarize` → context gắn bãi/kỳ/phạm vi → provider → lưu context/content/model cùng analysis. Runner `scripts/verify_single_lot_ai.py` đọc lại chính context đã lưu cùng output, không dùng snapshot GET trước đó có thời điểm khác. Không gửi tên/biển/điện thoại/mật khẩu người dùng.

Artifact đầu `backend/artifacts/demo/p1-live-ai-final-acceptance.json` chứa5ca thật: ngày, tuần, hỏi đáp, nhân sự và kỳ rỗng;30 kiểm tra HTTP/history/replay/quyền đạt. Review nội dung phát hiện lỗi cộng hai bucket giờ nhưng ghi khoảng một giờ, và mô tả thiếu dữ liệu ngày chưa chính xác. Output này là bằng chứng phát hiện lỗi, chưa là nghiệm thu semantic; bản sửa và kết quả gọi lại được ghi dưới đây.

Test provider giả xác minh prompt, dữ liệu rỗng/sai, timeout/quota, injection và quyền, không có request ra mạng. Bằng chứng live phải ghi riêng; không lấy số test mock làm số lần Gemini thật.

## Cuối kỳ — cách truy xuất và tái lập

- [CORE_ACCEPTANCE.md](CORE_ACCEPTANCE.md): đối chiếu từng F01–F13 và phần còn chốt.
- [SINGLE_LOT_DEMO.md](../SINGLE_LOT_DEMO.md): tạo DB mới, cấu hình AI bằng biến môi trường cục bộ, chạy ba vai trò.
- Các runner `verify_single_lot_core.py`, `verify_single_lot_upgrade.py`, `verify_single_lot_recovery.py`, `verify_single_lot_ai.py`: lưu JSON kết quả trong thư mục artifacts ignored; không ghi đè dữ liệu nguồn.
- Ảnh giao diện/PDF được kiểm thật; tên thư mục bằng chứng ở IMPLEMENTATION.md. Token/mật khẩu chỉ ở file local ignored riêng, không đưa vào hồ sơ.
- Phần mở rộng có ma trận E01–E08 riêng; bank/device live phải có bằng chứng tương ứng. Chưa xuất lại Word/slide của các mốc cũ trong đợt này.

## Kết quả vòng sửa KT3

Hai kiểm tra prompt RED→GREEN và122testAI/analytics đạt. Năm output thật mới trong `backend/artifacts/demo/p2-live-ai-acceptance.json` qua30checksHTTP/persistence và review độc lập: số liệu/kỳ/quyền đúng,17+18giờ được ghi17đếntrước19, daily totals không bị báo thiếu. Giữ hai ghi chú diễn đạt nhỏ và phạm vi của review, không cam kết loại bỏ mọi lỗi AI tương lai.

26 kiểm tra trình duyệt đọc đúng năm output, lịch sử và đổi kỳ đạt tại `backend/artifacts/p2-ai-browser/010b2dc7bd/result.json`; hai audit đăng nhập, không phát sinh lần gọi AI khác. Ảnh desktop/mobile đã xem. Đây là bằng chứng mới sau sửa, khác với artifact trước đó có CHANGES_REQUIRED.

## P8 — nghiệm thu tích hợp và cách tái lập

- Hồi quy toàn bộ backend hai lượt: lượt 1 ghi nguyên 13 ca thất bại (test cũ theo hợp đồng checkout/migration mới) rồi sửa test, lượt 2 sau sửa; số thật tại [FINAL_ACCEPTANCE.md](FINAL_ACCEPTANCE.md). Frontend 212 test/lint/build.
- Runner UAT trên DB mới schema06: `verify_single_lot_core.py`, `verify_single_lot_extensions.py --session-payments`, `frontend/tests/browser/session_credit_uat.py --mode live-disabled|fixture`, `verify_single_lot_recovery.py`, `verify_single_lot_upgrade.py`; JSON tại `backend/artifacts/demo/p8-uat-8769/` và `backend/artifacts/session-credit-browser/`.
- Bốn phát hiện provider của reviewer trước có test hồi quy trong `tests/test_session_online_payments.py` và `tests/test_session_payment_concurrency.py` (SQLite hai kết nối); không có bằng chứng ngân hàng thật.
- Launcher trình bày `scripts/start_single_lot_demo.ps1` được chạy thử thật dưới Windows PowerShell 5.1; mật khẩu chỉ ở sidecar cục bộ ignored.
