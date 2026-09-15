# Verification — 2026-09-15 proposal baseline

Source HEAD: `3ef172e` (initial working tree clean). This task edits planning documents/memory only.

Command executed in `D:\Ứng_dụng_TTNT\ParkingAI`:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_check_in.py tests/test_check_out.py tests/test_fee.py tests/test_slots.py tests/test_core_site_analytics.py tests/test_monthly_coverage_snapshot.py tests/test_checkout_quote_contract.py tests/test_report_period_consistency.py
```

Observed result: **115 passed in 37.49s**, exit code **0**.

`tests/conftest.py` forces SQLite in-memory, replaces AI keys with test values and installs an autouse guard against real Gemini client construction. This run did not validate a live provider or production database.

Test presence and the passing selected baseline are not a full acceptance result. No frontend build/tests, browser UAT, hosted-environment checks, new Gemini generation, PostgreSQL integration run or implementation of proposed behavior was performed in this planning task.

Claude collaboration status: attempted real Claude Code CLI invocation, version 2.1.263. Authentication failed before model work: `Failed to authenticate: OAuth session expired and could not be refreshed`. Result records zero API duration/cost and no generated model answer. The sanitized no-tools attempt failed with the same authentication message. No Claude review is represented as completed.

## Follow-up research and scope update

The user subsequently cancelled the Claude requirement and requested research of real parking websites, preserving F01–F13 before adding QR payments, OCR/CV and a customer portal. OAuth is no longer a blocker; no further Claude calls were made.

Added REAL_WORLD_REFERENCES.md (five first-party parking product/operator websites) and EXTENSION_PLAN.md (E01–E08, existing code mapping, payment-provider primary references). Updated PROPOSAL.md, intent.md, plan.md and project memory. The research task did not change application source or tests; the 115-pass baseline above belongs to the preceding planning run and was not rerun for document edits. No paid transaction, provider account setup, camera test or hosted deployment was performed.
