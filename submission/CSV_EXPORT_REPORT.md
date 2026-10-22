# CSV Export Fix Report

## Root cause

Before the fix, the decision trace was rendered with `st.dataframe`. Its only
CSV action was Streamlit's implicit table-toolbar export; the app did not
construct a download payload, set a filename or MIME type, or expose exports
for the evaluation records. In the open dashboard, clicking the toolbar
control produced no browser download event. The table changed sort state, so
there was no verified file to inspect. This reproduction is evidence of the
observed failure; it does not identify an internal Streamlit defect.

## Data flow after the fix

- Evaluation summary metrics and each report CSV are loaded from the same
  `eval/reports/{mock_v1,local_hf_v1}.json` file. The dashboard now checks that
  the declared task count, success/error counts, correct count, and accuracy
  agree with the underlying records before displaying the summary or export.
- The trace table, summary counts, and trace CSV all use events parsed from
  `traces/demo.jsonl`. Invalid JSONL lines are shown as warnings and are not
  included as records.
- Repository paths are derived from `app/dashboard.py`, so running the
  documented Streamlit command from the project root uses the intended files.
- The UI labels each export's scope. Report buttons export all records from
  that named report; the trace button exports all valid trace events even
  when the user filters which events appear in the table.

## Export format and browser verification

CSV uses Python's `csv.DictWriter`, first-seen column order, correct quote and
newline escaping, and UTF-8 with BOM for spreadsheet compatibility. Null or
missing fields become empty cells; booleans use lowercase `true`/`false`;
nested JSON values remain compact JSON in a cell. Invalid non-finite numbers
and unsupported Python value types show an export error instead of silently
losing data. Empty datasets do not show a download button.

Actual downloads were initiated through Chrome at `http://localhost:8501/`:

| File | Rows | Columns | Result |
| --- | ---: | ---: | --- |
| `/Users/aditya/Downloads/mock_v1_evaluation.csv` | 50 | 11 | Exact byte match to serialized source report records |
| `/Users/aditya/Downloads/local_hf_v1_evaluation.csv` | 50 | 11 | Exact byte match to serialized source report records |
| `/Users/aditya/Downloads/demo_trace.csv` | 5 | 16 | Exact byte match to serialized source trace events |

Each downloaded file was parsed back with `csv.DictReader`; its header and
record count were checked and its bytes were compared against serialization
of the actual source data. The downloads used only local checked-in reports
and traces. No Bedrock request or external service call was made.

## Verification commands

```bash
./.venv/bin/python -m pytest -q tests/unit/test_dashboard_export.py
./.venv/bin/python -m pytest -q
./.venv/bin/python -m compileall -q src tests eval app
git diff --check
./.venv/bin/python -m streamlit run app/dashboard.py
```

The original CSV export verification run passed **13 focused tests and 354
total tests**. After the Guided Demo redesign, the current full suite passes
**364 tests**, including those CSV tests; compilation and diff checks exit 0.
Browser verification confirmed all three named controls generated `.csv`
downloads. The current session also downloaded a 50-row, 11-column report and
the interactive error trace (one event, status `error`). The trace search
showed zero rows for an unmatched query and restored all five when cleared.

After a browser reload, Chrome's console also logged a WebSocket close and
health-poll requests that received no response. Direct browser navigation to
`/_stcore/health` displayed `ok`, and terminal requests to both the app and
health endpoint returned HTTP 200. The CSV controls and search still worked.
This console behavior remains unresolved and is recorded as a failed
diagnostic in the QA matrix.

## Changed files

- `app/dashboard.py` — Guided Demo decision workflow and tree, explicit
  report/trace downloads, record views, search, source error messages, and
  empty states.
- `app/demo_workflow.py` — local deterministic fixtures and branch state
  derived from actual decision traces.
- `tests/unit/test_dashboard_workflow.py` — workflow and tree-state checks.
- `app/dashboard_data.py` — shared report and JSONL loaders, consistency
  checks, safe filename generation, and CSV serialization.
- `tests/unit/test_dashboard_export.py` — 13 tests for report/trace round trips,
  headers and values, escaping, Unicode, nulls, nested fields, invalid input,
  empty data, and download metadata.
- `submission/TEST_REPORT.md` and `submission/FINAL_STATUS.md` — updated
  regression and release results.
- `submission/evidence/csv_export_verification.txt` — sanitized browser and
  downloaded-file verification record.

## Remaining limits

The dashboard remains a local Streamlit app reading repository files. It does
not connect to a FastAPI service or database because neither exists in this
project. Browser checks used the default viewport; narrow-screen layout was
not measured. The post-reload browser-console health-poll diagnostic is still
unresolved. The downloads are verified against the current checked-in
synthetic evaluation records and demo trace.
