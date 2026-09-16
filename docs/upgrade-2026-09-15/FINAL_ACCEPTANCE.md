# Nghiệm thu tích hợp — một bãi đồ án

Ngày 15/09/2026. Git base `3ef172e`; mã nâng cấp nằm trong working tree, chưa commit/push/deploy. Bảng này chỉ ghi những kết quả đã đọc từ lệnh/artifact; cột "Kết quả" ghi đúng số của từng lượt chạy, kể cả lượt thất bại.

## Phạm vi và quy tắc đã áp dụng

Giữ toàn bộ F01–F13 tại [ma trận lõi](CORE_ACCEPTANCE.md): quản lý/nhân viên, khu/chỗ/xe/vé, vào–ra và giá, chỗ trống, tra cứu, khách/vé tháng, thống kê và ba chức năng AI. Hệ thống chạy một bãi, nhiều khu, SQLite, FastAPI và React; không cần microservice hoặc nhiều bãi để nộp bài.

| Mở rộng | Hành vi trong bản hiện tại | Bằng chứng và giới hạn |
|---|---|---|
| E01 Portal | Hồ sơ/xe phải được cấp quyền; khách chỉ thấy tài nguyên của mình | Test API/quyền; trình duyệt khách trong bộ 35 checks P4–P7 |
| E02 Vé giờ/ngày/tháng | Giá và khung thời gian chốt theo đơn; vé giờ/ngày một lượt; vé tháng không tự giữ ô | Test timed parking; 11 ca độc lập giờ/ngày/quá giờ/replay; HTTP mua–nhận–ra |
| E03 Đặt chỗ | Giữ tạm có hạn, cấp đặt chỗ khi thanh toán, không bán trùng; ra sớm trả sức chứa | Test tranh chấp SQLite; bug arrived sau checkout đã tái hiện và sửa |
| E04 QR | Mapping trước HTTP, chữ ký/inbox/worker, kiểm đúng nguồn/số tiền, đối soát sự kiện đến muộn | Adapter giả lập nội bộ và SQLite đồng thời; chưa có tài khoản payOS hoặc giao dịch ngân hàng |
| E05 Phí/biên nhận | F tổng phí, C đã trả online, D còn thu; hai khoản online và thu tại cổng không đếm đôi; PDF đúng quyền | Hai ca API ký giả lập độc lập giờ/ngày, hai lần trả và biên nhận tất toán 0đ |
| E06 Camera biển | Nhận ảnh từ điện thoại/upload/edge, OCR đề xuất, nhân viên xác nhận rồi gọi nghiệp vụ lõi | Capture thực trên AVI tổng hợp; không phải nghiệm thu webcam/OCR vật lý |
| E07 Quan sát ô | Khoanh vùng, so ảnh tham chiếu, hai ảnh mới xác nhận, stale/unknown và đối chiếu | 36 ca API/engine, 9 evaluator; browser quản lý/nhân viên; chưa đo accuracy bãi thật |
| E08 Ngoại lệ | Sắp hết vé/đơn, thu hồi camera token, mất vé/sửa biển/hủy có lịch sử, review tiền | Các suite exception/portal/online/camera và UI đối soát |

Thuật toán ô đỗ là `reference-diff-v1`: phát hiện thay đổi vùng ảnh, không phải mô hình chứng minh vật trong ô là xe. Quan sát không sửa chỗ, lượt hay tiền. OCR/camera/AI lỗi vẫn có luồng thao tác thủ công theo quyền.

## Kiểm chứng

| Lần kiểm | Kết quả đã xác nhận | Artifact/lệnh |
|---|---|---|
| Frontend cuối | 212 passed; lint exit 0; build riêng exit 0 | `backend/artifacts/demo/p8-frontend-test.log`, `p8-frontend-lint.log`, `p5-credit-ui-build.log` |
| Thanh toán P5 cuối | 229 passed, 54,9 s (tám file payOS/online/session/concurrency/acceptance/view-review/credit-migration, chạy lại độc lập 14:07) | Một lệnh pytest; gồm các ca thu hồi quyền trong HTTP, nguồn đóng, bằng chứng sớm nhất, lượt hủy không tích phí |
| HTTP lõi trên schema06 | 79 checks PASS (10:51) và **79/79 PASS lần 2 trên phiên 8769 (14:08)** | `backend/artifacts/demo/p8-core-http-acceptance.json`; `backend/artifacts/demo/p8-uat-8769/core-http.json` |
| Backend toàn bộ P8 | Lượt 1 (11:18): 1.920 thu thập, **1.887 pass / 13 FAILED / 20 skip**, 22 phút — 13 ca là test cũ chưa theo hợp đồng checkout mới (trả dict F/C/D, `check_out_time` có múi giờ, snapshot migration 06). Sửa 5 file test (không sửa mã sản phẩm), chạy riêng 16 pass. Lượt 2 (14:02→): xem dòng "Full backend lượt 2" | `backend/artifacts/demo/p8-full-backend.xml/.log` (lượt 1), `p8-full-backend-2.xml/.log` (lượt 2) |
| HTTP mở rộng schema06 | **41 checks PASS** (11:00) và **41/41 PASS lần 2 trên 8769 với `--session-payments`** | `backend/artifacts/demo/p8-extensions-http-acceptance/result.json`; `p8-uat-8769/extensions-http.json` (mua vé, capacity, capture AVI tổng hợp, trạng thái phí lượt khi bank tắt) |
| Browser phí lượt | **live-disabled 7/7, fixture 29/29** trên 8769 (14:10); hai lượt trước 29/29 | `backend/artifacts/session-credit-browser/{5e335e07e0,9ef479cfa6}/result.json`; backend thật chỉ GET + login, kịch bản QR dùng API fixture |
| Migration và restore 48 bảng | Recovery **PASS 48 bảng** (11:16 và 14:11); upgrade rehearsal **PASS 48 bảng, nguồn không đổi, 476 lượt legacy giữ nguyên** | `backend/artifacts/demo/p8-recovery-acceptance.json`; `p8-uat-8769/{recovery,upgrade}.json` |
| Launcher trình bày | `start_single_lot_demo.ps1` chạy dưới Windows PowerShell 5.1: build bundle hợp nhất, `/ready` sau 6 s, `SINGLE_SITE_ID` từ marker, dừng sạch (cổng thử 8770) | Script ASCII, guard BOM trong `tests/test_demo_server.py` |

Phiên 8769 (14:05–14:12) dùng DB mới `p8-uat-8769-2109fe2bdee4.db` seed bằng `single_lot_seed` trên schema06 và **bundle hợp nhất `frontend/dist`** (build 14:05, `index-4i33lGoy.js`) — không còn cần bundle riêng `backend/artifacts/p5-credit-dist`. Server chạy `--single-lot --no-vision`, AI tắt; không gọi provider, ngân hàng hay thiết bị.

Các bộ có phần giao nhau, không cộng thành một tổng test. P1 full lịch sử có 1.469 pass/20 skip/2 lỗi fixture, sau đó sửa và kiểm riêng; không đổi nhãn lịch sử thành xanh. P8 lượt 1 có 13 ca thất bại được ghi nguyên; chỉ lượt 2 sau khi sửa test mới dùng làm kết quả cuối.

| Full backend lượt 2 | Kết quả | Artifact |
| --- | --- | --- |
| `pytest -q --junitxml=backend/artifacts/demo/p8-full-backend-2.xml` (14:02–14:26) | **1.920 thu thập: 1.900 passed / 0 failed / 0 error / 20 skipped**, 1.444 s. Skip: 7 `test_postgres_integration` + 11 `test_round3_postgres` (không có `POSTGRES_TEST_URL`), 1 POSIX owner/group trên Windows, 1 `test_vision_runtime_budget` | `p8-full-backend-2.xml/.log` |

**Kết luận P8 (15/09/2026 14:30):** vòng tích hợp đạt trên SQLite cục bộ với bundle hợp nhất — full backend 0 lỗi, frontend 212/212, HTTP lõi 79/79, mở rộng 41/41, browser phí lượt 7/7 + 29/29, recovery và upgrade 48 bảng. Giới hạn giữ nguyên ở mục dưới; mã được commit/push/deploy ngay sau đó (mục kế tiếp).

## CI/CD và triển khai (15/09/2026, 14:45–15:55)

| Bước | Kết quả | Bằng chứng |
| --- | --- | --- |
| Commit/push `4f6116b` (285 file P4–P8 + docs) | CI `verify` (ubuntu: 1.920 test backend + migration/integration PostgreSQL 16 + frontend test/lint/build) **xanh 12m29**; `vision-memory` xanh; `release-safety-windows` **bị hủy ở 30m12**: log dừng ở một ca `F` (~24%, nhóm readiness tham số hóa) rồi không có tiến triển 28 phút. Continuous Delivery bị bỏ qua vì CI không success. | GitHub Actions run của `4f6116b`; log chỉ có chữ `F`, không có traceback vì pytest in phần FAILURES ở cuối phiên bị cắt |
| Commit/push `e523ebc` (nâng `timeout-minutes` job Windows 30→60 theo trần của guard test) | `verify` xanh 12m34, `vision-memory` xanh 0m54, `release-safety-windows` **xanh 39m32** (291 ca). CD chạy: `alembic upgrade head` + `production_release_gate.py` trong release_command Fly. | Job API công khai: `release-safety-windows` completed/success 08:07:52Z→08:47:24Z; CD run 34948898918 |
| Production sau CD | `GET /` trả `release_id = e523ebcdf477fc95e4de1e3285c918275b73a068`; `GET /ready` = `{"status":"ready"}`; OpenAPI 175 path gồm `/api/v2/me/timed-passes`, `/api/v2/sites/{site_id}/online-payments/review*`, `/api/v2/sites/{site_id}/occupancy*`; preflight CORS từ `https://parkingai.am` → 200, `access-control-allow-origin: https://parkingai.am`; Cloudflare Pages phục vụ bundle mới `index-DrCCYjSK.js` (Pages đã build từ lúc push `4f6116b`, tức khoảng 1 giờ UI mới chạy trên API cũ `0b8c54c` cho đến khi backend lên). | curl từ máy phát triển 15:55 +07; không đọc dữ liệu khách |
| Gate Windows: nguyên nhân và xử lý | Ca `F` và ca treo **không tái hiện** cục bộ (Python 3.12.14/SQLite 3.53.1, 2 ca 6 s; cả file 290 pass/1 skip trong 11m17) lẫn trong bản clone sạch. Bằng chứng đo được: `0b8c54c` thu thập 192 ca → job 16m24; `e523ebc` 291 ca → 39m32; phần tăng là ~150 ca `test_readiness_rejects_wrong_definition_for_every_required_schema_object` mỗi ca chạy trọn bộ rollout (migration, backfill, readiness sâu) trên runner Windows lạnh. Sửa: một DB mẫu cấp module rồi copy cho từng ca (cục bộ 235 ca 57 s thay vì ~2 s/ca), thêm `faulthandler_timeout = 600` trong `pytest.ini` để lần treo sau in stack mọi thread, sửa chú thích sai trong `ci.yml` (0b8c54c có 192 ca, không phải 291). Không sửa mã sản phẩm. | `tests/test_release_safety.py` (fixture `rollout_template_database`), `pytest.ini`, `.github/workflows/ci.yml`. Kết quả CI của `2155d01` (16:08–16:18): `verify` **8m34** (bước backend 6m53, trước 12m34), `vision-memory` 0m52, `release-safety-windows` **9m12** (bước test 8m20, trước 39m32); CD success, production `release_id = 2155d01…`, `/ready` ready (16:33) |

## Bổ sung 16/09/2026 — trang giới thiệu công khai, hỗ trợ và hoàn tiền

Hai khoảng trống còn lại của EXTENSION_PLAN §2 được triển khai với migration additive `20260916_07` (8 cột `parking_sites`, bảng `customer_support_requests`, `customer_support_messages`, `payment_refund_requests`). Bằng chứng: 10 test backend mới, gate readiness 328 pass/1 skip, frontend 221 test/lint/build, HTTP UAT 60 checks, browser UAT 73/73 (desktop + mobile, lỗi API/rỗng/retry), migration bản sao schema06 PASS (48 bảng gốc giữ nguyên, 51 bảng sau nâng cấp), backup–restore PASS 51 bảng. Số hồi quy toàn bộ và CI/CD ghi trong [PUBLIC_SITE_AND_SUPPORT.md](../upgrade-2026-09-16/PUBLIC_SITE_AND_SUPPORT.md) và HANDOFF. Hoàn tiền với ngân hàng thật vẫn chưa nghiệm thu (chưa có tài khoản payOS); quản lý ghi nhận khoản hoàn ngoài hệ thống kèm tham chiếu.

## Bằng chứng AI và giao diện đã lưu

Năm kết quả Gemini thật sau sửa prompt ở `backend/artifacts/demo/p2-live-ai-acceptance.json`: 30 checks HTTP/persistence và review nội dung đạt trong bộ ca ngày/tuần/hỏi đáp/nhân sự/kỳ rỗng. Đầu vào là dữ liệu tổng hợp có nhãn, không đưa bí mật hoặc danh tính khách vào model. Output trước sửa được giữ riêng với kết luận CHANGES_REQUIRED.

Giao diện mở rộng P4–P7: 35 checks tại `backend/artifacts/extensions-browser/5b73d9f9d9/result.json`. Giao diện Markdown đọc lại đúng năm output đã lưu: 23 checks tại `backend/artifacts/saved-ai-browser/da61bf2748/result.json`, không gọi thêm model. Đây là kiểm trình bày, không thay review nội dung.

## Vận hành và bàn giao

[Hướng dẫn demo](../SINGLE_LOT_DEMO.md) tạo DB mới riêng với tài khoản ngẫu nhiên, không ghi đè DB cũ. [SDLC_EVIDENCE.md](SDLC_EVIDENCE.md) nối yêu cầu/prompt/code/test; [nghiên cứu website](REAL_WORLD_REFERENCES.md) ghi nguồn tham khảo và quyết định phạm vi.

Chưa nghiệm thu ngân hàng, thiết bị webcam/điện thoại vật lý, độ chính xác CV ngoài bãi hoặc PostgreSQL đang chạy. CI/CD đã chạy cho `4f6116b`/`e523ebc` (mục CI/CD ở trên); Word/slide lịch sử chưa được xuất lại cho working tree này. Các giới hạn này được giữ trong bộ nhớ chung để người tiếp tục không hiểu nhầm bằng chứng mô phỏng thành triển khai thật.
