# Đánh giá 14 PR dependency

Ngày đánh giá: **2026-08-29**. Fixed point: `origin/main` tại
`9057037de871bf0fd15bba485667a746508b0184`. Phạm vi gồm PR #8, #9, #10,
#12, #14–#23. Không PR nào được checkout vào working tree, merge hoặc push.

Hai trục dưới đây độc lập: “Standards” trả lời PR có vượt quy chuẩn của repo
hay không; “Spec/compatibility” trả lời dependency có phù hợp và cần kiểm thử
gì. Không dùng một trục để xóa hoặc hạ mức phát hiện của trục còn lại.

## 1. Standards review

Nguồn chuẩn trong repo là `README.md`, `.github/workflows/ci.yml` và
`scripts/sync_source_snapshot.py`. Repo không có `AGENTS.md`,
`CONTRIBUTING.md`, `CODING_STANDARDS.md` hoặc `docs/agents/issue-tracker.md`;
vì vậy không thể truy xuất issue/spec gốc theo issue tracker.

### Phát hiện chung — mức chặn

Cả 14 PR sửa source nhưng không đồng bộ file tương ứng dưới
`HoSo_BaoCao_ParkingAI/03_KT3_TrienKhai_KiemThu/SourceCode`. So sánh blob cho
thấy 1–2 mismatch mỗi PR. Public Checks đều có `verify: failed` ở bước
`Verify source snapshot parity`; backend tests, PostgreSQL integration,
frontend tests, ESLint và build sau đó bị skip. Vì vậy **chưa PR nào vượt gate
được README quy định**, bất kể mức rủi ro dependency.

Các merge ref đều tồn tại và `git merge-tree` không phát hiện conflict marker
tại thời điểm đánh giá. Điều này không thay thế CI xanh sau khi rebase.

| PR | Standards finding | Khuyến nghị Standards |
| --- | --- | --- |
| [#23](https://github.com/lam1826/ParkingAI/pull/23) MUI icons | Snapshot fail; lockfile nâng cả Material 9.3.1 nhưng manifest còn `^9.2.0`, có version-family drift và cần visual UAT. | Defer |
| [#22](https://github.com/lam1826/ParkingAI/pull/22) types/react | Snapshot fail; không thấy smell khác. | Defer |
| [#21](https://github.com/lam1826/ParkingAI/pull/21) Uvicorn | Snapshot fail; đồng thời bỏ UTF-8 BOM ngoài phạm vi. | Defer |
| [#20](https://github.com/lam1826/ParkingAI/pull/20) types/react-dom | Snapshot fail; không thấy smell khác. | Defer |
| [#19](https://github.com/lam1826/ParkingAI/pull/19) Starlette | Snapshot fail; app dùng Starlette trực tiếp nhưng test bị skip. | Defer |
| [#18](https://github.com/lam1826/ParkingAI/pull/18) Data Grid | Snapshot fail; root manifest vẫn giữ 9.10.1, tạo version drift. | Defer |
| [#17](https://github.com/lam1826/ParkingAI/pull/17) charset-normalizer | Snapshot fail; bỏ BOM ngoài phạm vi. | Defer |
| [#16](https://github.com/lam1826/ParkingAI/pull/16) Day.js | Snapshot fail; không thấy smell khác. | Defer |
| [#15](https://github.com/lam1826/ParkingAI/pull/15) Pygments | Snapshot fail; bỏ BOM ngoài phạm vi. | Defer |
| [#14](https://github.com/lam1826/ParkingAI/pull/14) SQLAlchemy | Snapshot fail; bỏ BOM; DB/concurrency/Postgres suite chưa chạy. | Defer |
| [#12](https://github.com/lam1826/ParkingAI/pull/12) setup-python | Snapshot fail; không thấy smell khác. | Defer |
| [#10](https://github.com/lam1826/ParkingAI/pull/10) Python 3.14 image | Snapshot fail; production thành 3.14 trong khi cả hai CI job vẫn 3.12. | **Reject as-is** |
| [#9](https://github.com/lam1826/ParkingAI/pull/9) upload-artifact | Snapshot fail; không thấy smell khác. | Defer |
| [#8](https://github.com/lam1826/ParkingAI/pull/8) checkout | Snapshot fail; không thấy smell khác. | Defer |

## 2. Spec/compatibility review

Không có issue tracker nội bộ, nên trục này dùng title/body PR, diff thực tế và
release note chính thức làm spec thay thế. Tất cả ref khớp file dependency dự
kiến và `git diff --check` đạt. “APPROVE” bên dưới chỉ có nghĩa rủi ro thấp sau
CI bình thường; finding Standards vẫn chặn merge hiện tại.

| PR | Kết luận compatibility | Kiểm tra bắt buộc trước merge |
| --- | --- | --- |
| [#23](https://github.com/lam1826/ParkingAI/pull/23) | **TEST** — scope lockfile lớn hơn title; Icons kéo Material 9.3.1 và System/Utils/Types 9.3.0, gồm bản vá prototype pollution của MUI System. | Rebase/consolidate với #18; `npm ci`, `npm ls` họ MUI, test/lint/build và UAT icon/dialog/select/menu bằng chuột + bàn phím. |
| [#22](https://github.com/lam1826/ParkingAI/pull/22) | **APPROVE** — type dev-only, frontend JS/JSX không có TypeScript build. | CI frontend bình thường. |
| [#21](https://github.com/lam1826/ParkingAI/pull/21) | **TEST** — patch Uvicorn sửa WebSocket/header/parser, không công bố breaking API. | Clean install, `pip check`, full backend/Postgres, Docker boot, `/ready`, CORS và HTTP smoke. |
| [#20](https://github.com/lam1826/ParkingAI/pull/20) | **APPROVE** — type dev-only, không tác động runtime. | CI frontend bình thường. |
| [#19](https://github.com/lam1826/ParkingAI/pull/19) | **TEST** — 1.4–1.6 đổi GZip/body-size/debug/FileResponse; FastAPI hiện chấp nhận version này. | Full API/auth/audit/error + Postgres, Docker readiness và CORS smoke. |
| [#18](https://github.com/lam1826/ParkingAI/pull/18) | **TEST** — peer-compatible nhưng cập nhật nhiều gói MUI X; DataGrid được dùng rộng và có server paging. | `npm ls`, test/lint/build; UAT mọi grid: row/filter/sort/page/toolbar/loading/empty/edit/delete/keyboard. |
| [#17](https://github.com/lam1826/ParkingAI/pull/17) | **TEST** — không import trực tiếp; 3.5 đổi accelerator và detection cho nội dung lớn/khó đoán. | Linux container clean install, `pip check`, full tests, HTTP smoke response lớn/non-ASCII. |
| [#16](https://github.com/lam1826/ParkingAI/pull/16) | **APPROVE** — timezone patch; source không import Day.js. | CI frontend bình thường. |
| [#15](https://github.com/lam1826/ParkingAI/pull/15) | **APPROVE** — không import trong app, chủ yếu lexer mới. | Clean install và backend tests. |
| [#14](https://github.com/lam1826/ParkingAI/pull/14) | **TEST** — SQLAlchemy là lõi, patch liên quan concurrent UPDATE/bulk session state. | Full suite, check-in/out concurrency, Postgres/release safety, Alembic và rollback/transaction. |
| [#12](https://github.com/lam1826/ParkingAI/pull/12) | **TEST** — v6 dùng Node 24/runner ≥2.327.1; v7 chuyển ESM. | Cả Ubuntu/Windows jobs xanh, Python 3.12 và pip cache hoạt động. |
| [#10](https://github.com/lam1826/ParkingAI/pull/10) | **DEFER** — runtime production nhảy 3.12→3.14 nhưng CI không đổi; wheel có vẻ khả dụng nhưng chưa chứng minh tương thích. | Thêm CI 3.14 Linux/Windows; build exact image, `pip check`, native imports, full SQLite/Postgres/Alembic/concurrency, staging readiness/CORS/load và đo resource. Pin patch/digest. |
| [#9](https://github.com/lam1826/ParkingAI/pull/9) | **TEST** — v6/v7 đổi Node runtime/ESM; PR CI không chạy bước delivery này. | Dry-run không production; tải artifact theo SHA, kiểm tra `frontend/dist` và retention 14 ngày. |
| [#8](https://github.com/lam1826/ParkingAI/pull/8) | **TEST** — v7 thêm bảo vệ fork cho `workflow_run`; điều kiện delivery hiện chỉ nhận push main nên về lý thuyết không bị chặn. | CI Ubuntu/Windows và delivery dry-run xác nhận exact-SHA checkout + main-ancestor gate. |

### Rủi ro cắt ngang

- Các PR backend #14/#15/#17/#19/#21 cùng bỏ BOM, dễ conflict; gom normalization
  thành một commit riêng hoặc rebase từng PR.
- `@mui/x-data-grid` bị khai báo ở root và frontend; chọn manifest có thẩm quyền
  trước khi xử lý #18/#23.
- #18 và #23 ghi đè cùng vùng lockfile; nên gom thành một nhánh có peer tree sạch.
- Các Actions PR vẫn dùng mutable major tag. Với delivery production, pin full
  commit SHA đã review rồi để Dependabot cập nhật SHA.

## 3. Quyết định

Không auto-merge. Trước hết sửa snapshot trong từng PR để toàn bộ gate thực sự
chạy. Sau đó có thể xử lý nhóm thấp rủi ro #22/#20/#16/#15 riêng; các PR còn lại
phải qua targeted test ở bảng trên. #10 phải sửa as-is trước khi review lại.

## 4. Nguồn upstream chính thức

- [MUI Material 9.3.0](https://github.com/mui/material-ui/releases/tag/v9.3.0),
  [MUI X 9.11.0](https://github.com/mui/mui-x/releases/tag/v9.11.0) và
  [9.12.0](https://github.com/mui/mui-x/releases/tag/v9.12.0)
- [Uvicorn release notes](https://uvicorn.dev/release-notes/) và
  [Starlette release notes](https://starlette.dev/release-notes/)
- [charset-normalizer 3.5.1](https://github.com/jawah/charset_normalizer/releases/tag/3.5.1),
  [Day.js 1.11.23](https://github.com/iamkun/dayjs/releases/tag/v1.11.23),
  [Pygments changelog](https://pygments.org/docs/changelog/)
- [SQLAlchemy 2.0.52 changelog](https://docs.sqlalchemy.org/en/20/changelog/changelog_20.html#change-2.0.52)
- [setup-python v7](https://github.com/actions/setup-python/releases/tag/v7.0.0),
  [upload-artifact v7](https://github.com/actions/upload-artifact/releases/tag/v7.0.0),
  [checkout v7](https://github.com/actions/checkout/releases/tag/v7.0.0)
- [Python 3.14 porting notes](https://docs.python.org/3.14/whatsnew/3.14.html)
  và [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
