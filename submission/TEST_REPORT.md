# Test and QA Report

## Environment and commands

Repository: `/Users/aditya/Amazon_Hackathon/jarvis-decider-copy`
Runtime: project `.venv` (the shell has no `python` command on PATH); Streamlit 1.65.0. Git state before this redesign already included the dashboard/export changes from the prior request; those user changes were preserved.

| Procedure | Result | Evidence type |
| --- | --- | --- |
| `./.venv/bin/python -m pytest -q tests/unit/test_dashboard_export.py` | **PASS** — 13 passed in 0.02s | Focused CSV/load tests |
| `./.venv/bin/python -m pytest -q` | **PASS** — 364 passed; 0 failed | Full regression suite after Arnova visual redesign |
| `./.venv/bin/python -m compileall -q app src tests eval` | **PASS** — exit 0 | Automated syntax/bytecode compilation |
| `./.venv/bin/jarvis-decider --check-config` | **PASS** — free mode, paid use false | Executed CLI |
| `./.venv/bin/jarvis-decider --run-demo` | **PASS** — mock chose `research`; action `task_routing`; destination `research`; escalated false | Executed deterministic mock workflow |
| `./.venv/bin/python -m streamlit run app/dashboard.py --server.address 127.0.0.1 --server.port 8501 --server.headless true` | **PASS** — Streamlit started on localhost | Live local process |
| `curl -fsS -o /tmp/jarvis-dashboard-response.html -w 'HTTP %{http_code}; content-type %{content_type}; downloaded %{size_download} bytes\\n' http://127.0.0.1:8501/` | **PASS** — HTTP 200, `text/html; charset=utf-8`, 6463 bytes | Local HTTP integration |
| Browser open of `http://127.0.0.1:8501/` | **PASS** — Arnova Decider landing page, hero illustration and CTAs; Guided Demo, Evaluation Lab, and Audit Trail navigation | Chrome desktop viewport, 1470 px wide |
| Browser interactive workflow | **PASS** — standard mock selected first route at 1.00 confidence; fallback fixture recorded 0.20 < 0.60 and invoked mock fallback; error fixture stopped before routing action | Manual browser interaction; actual trace/result UI |
| Browser download of mock report CSV | **PASS** — 50 rows, 11 columns; exact match with source serialization | Current browser download `/Users/aditya/Downloads/mock_v1_evaluation (3).csv` |
| Browser download of local model report CSV | **PASS** — 50 rows, 11 columns; exact match with source serialization | Current browser download `/Users/aditya/Downloads/local_hf_v1_evaluation (1).csv` |
| Browser download of historical trace CSV | **PASS** — 5 rows, 16 columns; exact match with source serialization | Current browser download `/Users/aditya/Downloads/demo_trace (3).csv` |
| Browser download of interactive run trace | **PASS** — one error event, 25 columns, status `error` | Current browser download `/Users/aditya/Downloads/interactive_demo_trace (1).csv` |
| Browser trace search | **PASS** — unmatched query showed 0 of 5; clearing it restored 5 of 5 | Manual browser interaction |
| Browser console health polling | **FAIL** — a `WebSocket onclose` warning remains from a prior browser session. Current browser interaction completed without a runtime/import error; previous direct health checks returned HTTP 200 and `ok` | Chrome console and prior direct endpoint checks |
| `git diff --check` | **PASS** — exit 0 | Git whitespace check |

The final full regression run executed 364 tests and passed all 364. The focused 13-test CSV run is a subset and is not added a second time. Compilation, CLI, HTTP, and browser checks are reported separately and are not included in the pytest count.

## Test matrix

Rows below identify test families from the executed suite. Parameterized cases count as individual pytest tests. Mocked provider outcomes are never counted as live-provider checks.

| Test ID | Feature | Scenario | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Contracts | Valid decision request/result and serialization | Valid schema accepted | Covered by passing contract tests | PASS | `tests/unit/test_contract.py` |
| T02 | Contracts | Missing/invalid fields, types, confidence bounds | Validation rejects malformed input | Covered by passing contract tests | PASS | `tests/unit/test_contract.py` |
| T03 | Decision engine | Confidence at/above threshold | Primary choice accepted without fallback | Covered by passing engine tests | PASS | `tests/unit/test_engine.py` |
| T04 | Decision engine | Low/unknown confidence and threshold boundaries | One fallback when configured; otherwise explicit failure | Covered by passing engine tests | PASS | `tests/unit/test_engine.py` |
| T05 | Decision engine | Invalid primary/fallback choices and backend exceptions | Reject invalid result; no unsafe action | Covered by passing engine tests | PASS | `tests/unit/test_engine.py`, `tests/unit/test_application.py` |
| T06 | Configuration | Defaults, malformed settings, cost guard | Invalid config rejected; paid provider stays opt-in | Covered by passing config tests | PASS | `tests/unit/test_config.py` |
| T07 | Application | Default deterministic routing happy path | Mock chooses an allowed destination and returns a local routing outcome | Executed `--run-demo`; `research` returned | PASS | CLI output; `tests/unit/test_application.py` |
| T08 | Application | Unsupported destination and failed action/trace | Reject; no success outcome | Covered by passing application tests | PASS | `tests/unit/test_application.py` |
| T09 | CLI | Configuration check, run demo, invalid combinations | Correct exit status and actionable message | Config and demo commands exited 0; negative CLI cases covered in suite | PASS | CLI output; `tests/unit/test_cli.py` |
| T10 | Bedrock selection | No paid opt-in, missing region, lazy client setup | Block before request/client as applicable | Covered by passing tests; no real request used | PASS | `tests/unit/test_application.py`, `tests/unit/test_bedrock.py` |
| T11 | Bedrock response | Valid, missing, oversized, malformed JSON/schema | Accept valid normalized choice; reject malformed response | Fake-client cases passed | PASS | `tests/unit/test_bedrock.py` |
| T12 | Bedrock failures | Throttling, service unavailable, timeout, auth, permission, network | Classify/sanitize; retry only bounded eligible errors | Fake-client tests passed with expected call counts | PASS | `tests/unit/test_bedrock.py` |
| T13 | Bedrock trace | Attempt, retry, fallback, invalid response and error metadata | Trace outcomes without raw provider content | Fake-client trace tests passed | PASS | `tests/unit/test_traced_engine.py`, `tests/unit/test_trace.py` |
| T14 | Live Bedrock inference | Actual AWS request and inspected provider response | Report only actual successful inference as live success | Not attempted; prior user-reported quota throttling remains unverified in current run | NOT RUN | No live-provider evidence |
| T15 | Evaluation correctness | Recompute retained counts and latency; reject inconsistent records | Totals match source; inconsistencies rejected | Passing audit tests; dashboard shows retained report values | PASS | `tests/unit/test_audit_report.py`; browser observation |
| T16 | Evaluation accuracy | Compare model decisions with reference labels | Exact matches are computed on supplied synthetic set | Historical data: local 41/50 (82%); mock 18/50 (36%); no fresh inference | PASS | `reports/evaluation/day1_results.json`, `reports/evaluation/day2_evaluation.md` |
| T17 | Trace handling | Valid JSONL and malformed/unsafe trace input | Valid entries shown; invalid data handled safely | Passing trace tests; five existing rows visible in dashboard | PASS | `tests/unit/test_trace.py`; browser observation |
| T18 | Dashboard HTTP | Local app returns a page | HTTP 200 and HTML content type | HTTP 200, `text/html; charset=utf-8` | PASS | Executed curl procedure above |
| T19 | Dashboard rendering | Guided Demo landing, secondary Evaluation Lab and Audit Trail, metrics, search, CSV control | Render checked-in data with clearly labeled sources | Guided Demo landing, three scenarios, both synthetic reports, five historical trace entries, and named exports visibly rendered | PASS | Browser observation at default viewport |
| T20 | Dashboard responsive layout | Laptop, tablet, mobile-width hero and workflow tree | Content stacks without clipped text or page-level horizontal overflow | Inspected at 1470, 768, and 390 px. At 390 px the hero and workflow stack; primary/fallback branches become full-width rows; document width remains equal to viewport | PASS | Chrome viewport checks; rendered DOM geometry and screenshots |
| T21 | API/database/security | FastAPI routes, DB persistence, auth, permissions, other-user access | Applicable API and data controls verified | No FastAPI, DB, auth, or user data model found in repository | NOT RUN | Out of current project scope; see exclusions |
| T22 | Dependency failure/recovery | Database unavailable, upstream HTTP malformed, service recovery | Correct error/recovery behavior | No database or report HTTP dependency exists; Bedrock failure handling is covered with fakes | NOT RUN | Database/UI API cases do not apply to this implementation |
| T23 | Regression/static | Full test suite, compilation, whitespace | Existing behavior remains green and sources compile | 364 passed; compileall and `git diff --check` exit 0 | PASS | Executed commands above |
| T24 | Interactive decision path | Standard mock, low-confidence fallback, backend error | Branch visualization matches actual workflow and sanitized trace | Browser showed primary accepted, one fallback, and error stop without action; each outcome matched the selected highlighted tree branch | PASS | `tests/unit/test_dashboard_workflow.py`; browser observation |
| T25 | CSV evaluation export | Both genuine 50-record report datasets; header, values, row count | UTF-8 CSV round-trips all source records | 13 focused tests passed; 50 rows and 11 columns per actual download | PASS | `tests/unit/test_dashboard_export.py`; downloaded files |
| T26 | CSV trace export | Five JSONL events; first-seen columns, values, row count | UTF-8 CSV round-trips all source events | 5 rows and 16 columns; actual file equals source serialization byte-for-byte | PASS | `tests/unit/test_dashboard_export.py`; downloaded file |
| T27 | CSV edge cases | Commas, quotes, newlines, Unicode, nulls, missing fields, nested JSON, numeric and boolean values | Standard escaping; supported data retained; unsupported/nonfinite values rejected | Round-trip and rejection cases passed | PASS | `tests/unit/test_dashboard_export.py` |
| T28 | CSV empty and metadata | Empty rows, safe filename, MIME type | Empty payload is not exposed by UI; filenames end in `.csv`; UTF-8 CSV MIME configured | Helper tests passed; each nonempty browser button has explicit filename and MIME | PASS | `tests/unit/test_dashboard_export.py`; prior browser downloads |
| T29 | Dashboard source integrity | Missing/malformed report, record-count or accuracy mismatch; malformed JSONL lines | Useful error/warning, no fabricated records or mismatched metric success | Loader tests passed; report count and accuracy cross-check source records | PASS | `tests/unit/test_dashboard_export.py` |
| T30 | Dashboard/export consistency | Displayed counts and exported records come from same report/trace loaders | Counts and CSV source agree | Prior browser downloads matched 50/50 report rows and five historical events byte-for-byte | PASS | Prior browser and byte-comparison procedure |
| T31 | CSV browser integration | Click named exports from Evaluation Lab, Audit Trail, and Guided Demo | Browser receives a `.csv` file with matching content | Current browser downloaded both 50-row reports, five historical events, and one interactive error event. The three static exports byte-match source serialization | PASS | Current download paths under `/Users/aditya/Downloads/`; parsed and byte-compared |
| T32 | Browser health-poll diagnostics | Keep dashboard open after reload | Browser health polling and WebSocket remain error-free | Prior console logged WebSocket close and health-poll errors; direct health route returned HTTP 200 and `ok`. Fresh clean browser session completed interactions and downloads; one old `WebSocket onclose` warning remains visible | FAIL | Chrome console; direct health route and curl |

## Accuracy and interpretation

The retained Day 1 benchmark is a synthetic, hand-labeled set of 50 tasks. The reported local model score is 41/50 (82%) and the mock score is 18/50 (36%). These are exact-label agreement counts on that dataset only. They do not measure semantic correctness in production, independent label quality, or calibrated confidence. The Day 2 audit recomputes historical records; it does not rerun either backend.

## Exclusions, untested paths, and residual risks

- Health route, API status codes, JSON API contracts, DB persistence, auth, authorization, rate limits, cross-user access, and frontend-to-API matching are not applicable to the inspected repository because those components do not exist.
- No real Bedrock invocation was attempted. Account credentials, model access, quotas, IAM permissions, regional access, real provider error timing, and live response quality remain **NOT RUN**.
- Fake Bedrock clients validate adapter behavior offline; their outputs are simulated test fixtures, not external-provider evidence.
- The fallback and error paths in the interactive demo use deterministic fixture backends based on behavior already covered by engine tests. They are not model inference.
- Dashboard missing/malformed input behavior is covered in loader tests, but those browser states were not exercised by replacing or removing the real files.
- Browser checks covered a 390 px mobile viewport, a 768 px tablet viewport, and a 1470 px desktop viewport. Automated visual regression snapshots are not configured.
- The browser console's transient WebSocket/health-poll errors after reload remain unexplained. Direct `/_stcore/health` checks return HTTP 200 and browser downloads work, but the diagnostic remains reported as a failure.
- The test suite has no coverage measurement, so no coverage percentage is claimed.
