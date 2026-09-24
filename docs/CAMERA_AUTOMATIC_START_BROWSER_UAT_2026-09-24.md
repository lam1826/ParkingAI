# Camera automatic-start browser acceptance — 2026-09-24

Scope: the reported disabled **Bật tự động** button, role restrictions, webcam startup, actual automatic OCR/process requests, stopping, and failure handling. This is scoped acceptance, not a rerun of every ParkingAI feature. Production implementation and consolidated report are in `CAMERA_AUTOMATION_FIX_2026-09-24.md`.

## Environment and boundaries

- Shared marked synthetic demo: `http://127.0.0.1:8793`. Browser interception permitted only reads and authentication; no policy, image, process, admission, payment or AI writes.
- Isolated clone: `http://127.0.0.1:8804`, SQLite backup at `backend/artifacts/camera-auto-uat/environments/add9801fbf/camera-auto-clone.db`. Clone writes were limited to camera policy, live-frame ingestion and process endpoints. No thresholds were lowered: the fixture uses minimum confidence **0.99** and maximum frame age **12 seconds**.
- Private Chrome profiles, normal browser sandbox, loopback-only requests; profiles were removed after each run. Credentials remained in ignored sidecars and are not included in reports.
- Video was a canvas MediaStream from the existing CC0 photograph, not physical camera hardware. Actual backend detection/OCR was used except for explicitly identified injected HTTP failures and the separate mocked delayed process response.

## Results and retained failures

All run paths below are under `backend/artifacts/camera-auto-uat/`; each has `result.json` and relevant screenshots.

| Run | Scope | Result | Interpretation |
|---|---|---|---|
| `0df0465f5c` | Original disabled button baseline, ready video, Admin/Manager/Staff | 24 PASS, 3 FAIL | Admin and Manager were incorrectly blocked by disabled policy despite ready video. The Staff expected-enabled assertion was an early harness assumption superseded by the clarified authorization design; Staff blocking is correct. Original artifact retained unchanged. |
| `2292cf68b8` | First clone run | Incomplete; 7 PASS | Harness assumed the sessions endpoint returned a paginated object. It returns a list. Corrected to count all API pages; no product failure asserted. |
| `64e3ccbfac` | Full scoped regression | 116 PASS, 0 FAIL; 1 NOT_RUN | Real automatic flow and all planned startup/error checks passed. The initial error classification was case-based, so injected failures were independently rerun with exact request correlation. |
| `643f1ae414` | Controlled HTTP error paths | 60 PASS, 0 FAIL; 1 NOT_RUN | Each expected 503 is correlated to the exact CDP `networkId` deliberately fulfilled by the harness. No unrelated HTTP failure was suppressed. |
| `812fe705f5` | Shared demo read-only role check | 30 PASS, 0 FAIL | Admin/Manager start enabled with policy OFF, before and after opening a ready video; Staff correctly disabled. Shared policy unchanged for all roles. |
| `8f2c5c50c0` | Controlled delayed process after Stop, before repair | 26 PASS, 1 FAIL; 1 NOT_RUN | Reproduced real UI race: a completed process response after Stop did not trigger sessions/availability refresh. The response was mocked, and no real admission occurred. |
| `ad920cc875` | Controlled delayed process after Stop, final build `index-gS2ZkbPh.js` | 27 PASS, 0 FAIL; 1 NOT_RUN | Both sessions and availability refreshed with HTTP 200 after the late result. No fabricated session selected and no frame loop restarted. |
| `5088705c11` | Normal automatic loop on final frontend, before clone backend reload | 34 PASS, 0 FAIL; 1 NOT_RUN | Kept as intermediate evidence; clone server had not loaded the separate backend quota repair yet. |
| `f704567da2` | Normal automatic loop on final frontend **and reloaded final backend** | 34 PASS, 0 FAIL; 1 NOT_RUN | Final integration: fresh login, actual OCR/process/manual result, timestamp ordering, preserved thresholds, stop/resume/visibility, sessions unchanged. No runtime or unexpected HTTP errors. |

The scoped browser checks passed, with physical-device and high-confidence admission limits below. Counts are reported per run and **must not be added together** because checks overlap. The full and controlled-failure runs preceded the late-response UI repair; the bounded late-response and normal-loop runs verify the final frontend. The final normal-loop run additionally reloads the final backend; the browser suite does not independently claim coverage of the backend quota boundary.

The final source-data comparison in `environments/add9801fbf/source-invariant.json` passed: policy table remained empty, sessions **489**, observations **11**, passages **0**, identical before and after testing. After the final integration run, the clone's command line, database path, parent process and listener were verified; only its server/launcher were stopped. `cleanup.json` confirms no listener remains on 8804. The shared server 8793 remains available.

## Functional matrix

| Behavior | Status | Evidence |
|---|---|---|
| Admin/Manager policy OFF: start is clickable | PASS | `812fe705f5`; before webcam and with ready video. |
| One click opens webcam, enables policy, confirms policy, starts actual loop | PASS | `64e3ccbfac`, final `f704567da2`; real `live-frames` and `/process` requests; exact one enabling PUT. |
| Existing thresholds preserved | PASS | Policy remained **0.99 / 12 seconds** after enabling; resume emitted no new PUT. |
| Frame captured after policy enabled | PASS | Final `f704567da2`: frame `2026-09-24T10:14:51.168000+07:00`, policy `2026-09-24T10:14:51.063239+07:00`. |
| Real OCR result displayed and uncertain result stays manual | PASS | `64e3ccbfac`: `live_camera`, recognized `LD4558BI`, confidence **0.566**, result **Cần kiểm tra**. UI reason: **Biển số không nhất quán hoặc chưa đúng định dạng.** Foreign-format sample; confidence is low but this is not proof that the confidence threshold alone caused manual review. |
| Stop prevents subsequent frames; resume restarts without policy mutation | PASS | `64e3ccbfac`, frame counters observed past the 4-second loop interval. |
| Hidden tab pauses and visible tab resumes | PASS, controlled visibility simulation | `64e3ccbfac`, simulated `document.visibilityState`; physical tab switching was not tested. |
| Staff cannot enable policy; clear Admin/Manager explanation | PASS | `64e3ccbfac`, `812fe705f5`; no editable policy checkbox. |
| Staff starts already permitted policy without PUT | PASS | `64e3ccbfac`. |
| Denied webcam or stream without frames | PASS, controlled media failures | Visible error, no running claim, policy remained OFF; no empty image upload. |
| Policy PUT fails | PASS, injected 503 | `643f1ae414`; visible error, policy remained OFF, no running/no frame. |
| Initial policy GET fails | PASS, injected 503 | `643f1ae414`; visible error, disabled start, no running. |
| Confirmation GET fails after successful PUT | PASS, injected 503 | `643f1ae414`; server policy ON but UI does not run or submit images before confirmed; **Thử lại** recovers, next start does not repeat PUT. |
| Frame ingestion fails | PASS, injected 503 | `643f1ae414`; explicit failure, no fabricated recognition/admission, Stop stays enabled and prevents retries. |
| Low-confidence/foreign-format fixtures do not admit a vehicle | PASS | `64e3ccbfac`, final `f704567da2`: sessions **489 → 489**, new passage states `[manual, manual]`. |
| Late completed response after Stop refreshes shared parking data | PASS, controlled mock; RED retained | `8f2c5c50c0` before / `ad920cc875` after; mocked completed response solely tests UI race, not actual admission. |
| Physical camera, device permissions on user hardware, high-confidence vehicle admission, edge hardware, real gate movement | NOT_RUN | Simulated webcam and synthetic local data only. Backend contract verification is reported separately by the parent task. |

## Reproduction

Harness: `frontend/tests/browser/camera_auto_uat.py`; clone creation helper: `frontend/tests/browser/camera_auto_environment.py`.

Representative screenshots: `f704567da2/manager-automatic-real-manual.png`, `f704567da2/manager-automatic-real-manual-mobile.png`, `812fe705f5/manager-auto-controls.png`, `643f1ae414/policy-confirmation-error.png`, and `ad920cc875/mock-late-process-after-stop.png`.

```powershell
.\.venv\Scripts\python.exe frontend/tests/browser/camera_auto_uat.py --credentials backend/artifacts/approved-implementation/approved-demo.db.demo-credentials.json --mode baseline
.\.venv\Scripts\python.exe frontend/tests/browser/camera_auto_uat.py --credentials backend/artifacts/camera-auto-uat/environments/add9801fbf/camera-auto-clone.db.demo-credentials.json --origin http://127.0.0.1:8804 --mode regression
```

`--case-filter injected` runs the independently prepared transport-failure cases. `--case-filter "controlled mock delayed"` runs the bounded late-process race case. Credentials and database must remain marked synthetic; regression mode refuses the shared port 8793.
