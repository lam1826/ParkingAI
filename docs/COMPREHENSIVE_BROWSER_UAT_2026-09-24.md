# Browser acceptance, 24 September 2026

This report records the completed browser retest of the real React/FastAPI application at `http://127.0.0.1:8793`, using only its marked synthetic database. The named core and customer transactions below have current passing evidence. This is not a claim that every extension, external provider, physical device or production environment has passed. Earlier failed runs remain intact.

## Status meanings

- **PASS:** the named behavior was exercised and its assertion succeeded.
- **FAIL:** the assertion failed; evidence is retained, including superseded baseline failures.
- **BLOCKED:** the required external capability was unavailable.
- **NOT_RUN:** this browser batch did not exercise that behavior. Unit/API tests are separate evidence.

## Baseline evidence

`backend/artifacts/comprehensive-uat/a7dc126620/` reproduced the reported invisible **Sửa hồ sơ** link. Its normal foreground and background were both `rgb(23, 103, 189)` (contrast **1.00:1**). Hover contrast was **1.626:1**. Actual matching rules identify `.prototype-ui a { color: var(--blue) }` overriding the MUI contained-button color. Screenshots and `account-contrast.json` retain this failure.

`backend/artifacts/comprehensive-uat/efc1db462d/result.json` completed the read-only baseline across 67 role/route cases: **275 PASS, 2 FAIL**. The two failures are the profile-link contrast assertions. Every inspected route rendered meaningful content or an expected permission denial and fit desktop 1440px/mobile 390px viewports. No HTTP errors, uncaught runtime exceptions or console errors were recorded. Private Chrome profiles were removed.

The route count includes repeated pages under different roles and expected denied pages; it is not a count of distinct implemented features. Opening a page does not establish that its forms complete transactions.

| Area | Current browser result | Transactional evidence and limit |
| --- | --- | --- |
| Login and account/profile/settings | PASS | Real public Customer registration, login, profile name update verified with auth API, mismatched password refusal, password change and login with new password, local chat-history clear, logout/token clear. Disposable account only. Auth group in `412beb378e`; profile-link correction in `a9734fca28`. Username rename is not a separate browser case. |
| Role boundaries | PASS | Four real roles; Customer operations/users/reports denied; Staff users/roles/config/audit/portal-admin denied. Manager can create only Staff and newly created Staff cannot open account administration. `2b3b26fb0b`, `5c4aac06fb`. Full API boundary tests are separate. |
| Zones | PASS | Create, edit, refuse deletion while a slot exists, delete after slot removal, delete independent unused zone. `5c4aac06fb`. |
| Named spaces | PASS | Create with real zone/type, edit name, delete unused slot. `5c4aac06fb`. |
| Vehicle types and rates | PASS | Type create/edit/delete on unreferenced records; hourly rate create/edit/read-back/delete; duplicate prefix create/update both give specific 409 guidance after fix. `5c4aac06fb`, `c00cb58a15`. |
| Walk-in, fee and checkout | PASS | Fresh entry without booking; private ticket proof; positive server fee; online-payment dialog; cash action disabled until explicit received confirmation; completed stay read back from server. `5b4ee470eb` plus `5c4aac06fb`. No bank transaction. |
| Capacity | PASS for displayed state and admission | All route layouts and real availability reads exercised; fresh walk-in admission uses an available type. Exhaustive capacity/concurrency constraints are covered separately by backend tests, not claimed as browser cases. |
| History | PASS | Completed stay found by exact plate and entry-day range, detail opens, reversed date range disables search. `c00cb58a15`. No exhaustive pagination/boundary-time browser claim. |
| Customers and vehicles | PASS | Create/edit both, create/delete unused customer and vehicle, link synthetic vehicle to synthetic customer. `5c4aac06fb`. |
| Monthly passes | PASS | Register for 50,000 synthetic VND, renew into a separate period preserving original ID, deactivate one period while retaining both. Registration in `5c4aac06fb`; renewal/deactivation in `c00cb58a15`. |
| Day/week reports and CSV | PASS | One-day summary, seven-day buckets, daily arrivals reconcile to weekly total, actual CSV download from UI, report layout. `5c4aac06fb`. Revenue reflects synthetic receipts; not real business revenue. |
| Staff accounts | PASS | Manager create/edit/lock, locked login refused, unlock and successful login. Referenced staff deletion correctly refused; Admin creates and deletes a fresh unassigned Customer account. `5c4aac06fb`, `c00cb58a15`. |
| Public configuration and audit | PASS for exercised actions | Unchanged-value public-profile save roundtrip, audit records visible. `5c4aac06fb`. Not every configuration field or audit filter was mutated. |
| Customer fee privacy | PASS | Fresh foreign plate alone returns generic 404; private proof grants fee access; proof removed from input/URL; vehicle ownership and owner-history unchanged; fresh stay later checked out. `5c4aac06fb`. |
| Optional bookings | PASS | Customer creates advance booking without prepayment, then cancels. `5b4ee470eb`. Reception/arrival and overlapping-capacity edge cases are backend-test scope. |
| Support | PASS | Create request, open thread, reply, close. `5b4ee470eb`. |
| AI status and saved-analysis screen | PASS for route/status only | Actual status API read. The faithful UI harness deliberately supplies an explicit test-only 503 to test chat error display; this is **not live provider acceptance**. Root agent's separate real-provider/semantic results are authoritative. |
| Camera/OCR | NOT_RUN here beyond route | Separate camera-agent test; this report makes no device accuracy claim. |
| Occupancy, insights, finance, portal administration | PASS route; NOT_RUN advanced transactions | Calibration, prediction, refunds, shift close, waitlist, fleet and portal-product transactions were not driven in this browser batch. Explicit insufficient-data notices were retained. |
| Bank payment | BLOCKED | payOS is unavailable/disabled in synthetic runner. No bank call and no simulated success presented as a bank result. |
| SDLC documents, PostgreSQL and deployment | NOT_RUN in browser | Source/test/documentation verification belongs to the root/backend agents; no production deployment or user DB migration occurred here. |

## Current evidence and retained failures

All paths below are under `backend/artifacts/` and remain local ignored artifacts. Counts are assertions within a run, not distinct features, and must not be added as unique coverage.

| Artifact | Actual outcome | Interpretation |
| --- | --- | --- |
| `comprehensive-uat/a7dc126620` | 3 PASS, 2 FAIL | Original MUI profile link was blue on blue. |
| `comprehensive-uat/efc1db462d` | 275 PASS, 2 FAIL | Original all-role route baseline; same two contrast failures. |
| `comprehensive-uat/2b3b26fb0b` | 277 PASS, 0 FAIL | 67 role/route cases desktop/mobile; no HTTP/runtime/console errors. This run preceded the final camera-label/entry-time and anchor-specificity follow-ups. |
| `comprehensive-uat/ea9b58319e` | 50 PASS, 5 FAIL | Initial harness had render-timing, overly broad `[name=description]` (matched a head meta tag), and session-response field assumptions. Independent successful groups remain valid. |
| `comprehensive-uat/dc3b95c369` | 67 PASS, 3 FAIL | Meta selector and dependent fixture failures retained; account lifecycle/privacy groups passed. |
| `comprehensive-uat/a2c8b4d617` | 70 PASS, 6 FAIL | Closed-details `innerText`, MUI menu closing transitions, and reusing an already granted proof fixture were incorrect harness assumptions. No failed transaction was relabeled successful. |
| `comprehensive-uat/412beb378e` | 76 PASS, 4 FAIL | Reused prefix fixture triggered a correct uniqueness guard but exposed a **real incorrect error message** (“type name exists” for a prefix collision). Dependent CRUD groups did not finish. Root fixed the message. |
| `comprehensive-uat/5c4aac06fb` | 83 PASS, 3 FAIL, 1 BLOCKED, 4 NOT_RUN | Catalog, staff lifecycle, reports, privacy and cash/non-cash checkout groups passed. Monthly registration succeeded, then harness tried pagination before reload. Admin deletion of a site-bound staff account returned the legitimate reference-guard 409; the test had incorrectly expected deletion. Bounded follow-up covers both cases explicitly. |
| `comprehensive-uat/c00cb58a15` | **34 PASS, 0 FAIL** | Monthly renewal/deactivation, exact history filters/detail, prefix create/update message regression, referenced-account refusal and unused-account deletion. Only explicit expected 409 responses; no unexpected HTTP/runtime/console failures. |
| `comprehensive-uat/1bffc5a906` | 6 PASS, 2 FAIL | **Regression from the first CSS fix:** `a:not(.MuiButtonBase-root)` increased specificity, turning native “Vào vận hành” blue on blue (1.00 normal/1.314 hover). This was found and fixed, not omitted. |
| `comprehensive-uat/289f8e9ddb` | 15 PASS, 0 FAIL | First anchor follow-up; secondary hover was off-screen, so its normal measurement is valid but hover acceptance is superseded below. |
| `comprehensive-uat/a9734fca28` | **15 PASS, 0 FAIL** | Final MUI/native anchors measured after scrolling into view, with actual `:hover` state asserted. No unexpected HTTP/runtime/console failures. |
| `prototype-real-comparison/5b4ee470eb` | **97 PASS, 0 FAIL; 34 screenshots** | Final Customer/Manager real booking/support/walk-in/private-proof/positive-fee/explicit-cash-checkout batch after final CSS build. Zero uncaught runtime errors. Chat 503 is explicitly intercepted test-only UI behavior, not provider output. |

Private Chrome profiles were removed after every run. Expected negative HTTP responses remain in result files, with their exact path/status and explanation, instead of being silently filtered out. The faithful harness records runtime exceptions but does not independently provide a complete HTTP/console error ledger; the comprehensive harness does.

The final selector is `a:where(:not(.MuiButtonBase-root))`, which excludes MUI button roots while preserving the original anchor-rule specificity. Final measured contrast:

| Link | Normal | Actual hover |
| --- | ---: | ---: |
| MUI “Sửa hồ sơ” | 5.658:1 | 9.202:1 |
| Native “Vào vận hành” | 5.658:1 | 7.437:1 |
| Native secondary “Xe & hồ sơ” | 8.993:1 | 8.442:1 |

Sidebar inactive text is restored to `rgb(80, 96, 116)` and active text remains `rgb(23, 103, 189)`. Final primary anchors have white text; secondary anchors preserve their prototype ink color.

## Reproduction

The harness reads the ignored local credentials sidecar in memory and never saves passwords, tokens or ticket payment proofs. It starts private Chrome without disabling its sandbox, blocks external/provider/bank traffic, and validates the synthetic database marker before operating.

```powershell
.\.venv\Scripts\python.exe frontend/tests/browser/comprehensive_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode baseline
.\.venv\Scripts\python.exe frontend/tests/browser/comprehensive_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode routes
.\.venv\Scripts\python.exe frontend/tests/browser/comprehensive_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode functional
.\.venv\Scripts\python.exe frontend/tests/browser/comprehensive_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode followup --records backend/artifacts/comprehensive-uat/5c4aac06fb/synthetic-records.json
.\.venv\Scripts\python.exe frontend/tests/browser/comprehensive_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode anchors
.\.venv\Scripts\python.exe frontend/tests/browser/prototype_faithful_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --flows --roles customer manager
```

Functional mode creates uniquely named synthetic records using real UI/API behavior. It changes passwords only on a new disposable account. It preserves referenced monthly periods and their synthetic receipts rather than deleting financial history. Follow-up mode consumes nonsensitive fixture IDs from a previous functional run; it is intentionally bounded and its monthly-renewal assertion expects the previously registered single period, so blindly rerunning it after a successful renewal is not an idempotent full-suite command. Use a fresh functional fixture for another complete lifecycle.
