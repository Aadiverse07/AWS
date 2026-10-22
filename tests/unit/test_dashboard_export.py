import csv
import io
import json
from pathlib import Path

import pytest

from app.dashboard_data import (
    CSV_MIME_TYPE,
    csv_filename,
    load_evaluation_report,
    load_trace_events,
    records_to_csv_bytes,
)

ROOT = Path(__file__).resolve().parents[2]


def csv_rows(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="strict"))))


@pytest.mark.parametrize("report_name", ["mock_v1.json", "local_hf_v1.json"])
def test_evaluation_csv_round_trips_the_report_records(report_name):
    report = load_evaluation_report(ROOT / "eval/reports" / report_name)
    content = records_to_csv_bytes(report["records"])
    parsed = csv_rows(content)

    assert len(parsed) == report["total_tasks"] == 50
    assert list(parsed[0]) == list(report["records"][0])
    assert parsed[0]["task_id"] == report["records"][0]["task_id"]
    assert parsed[0]["expected_choice"] == report["records"][0]["expected_choice"]
    assert parsed[0]["correct"] == str(report["records"][0]["correct"]).lower()


def test_trace_csv_round_trips_all_source_trace_events():
    events, warnings = load_trace_events(ROOT / "traces/demo.jsonl")
    content = records_to_csv_bytes(events)
    parsed = csv_rows(content)

    assert warnings == []
    assert len(parsed) == len(events) == 5
    assert list(parsed[0]) == list(events[0])
    assert parsed[0]["run_id"] == events[0]["run_id"]
    assert parsed[0]["chosen"] == events[0]["chosen"]
    assert parsed[0]["status"] == events[0]["status"]


def test_csv_escapes_commas_quotes_and_multiline_unicode_text():
    source = [{"label": 'naïve, "quoted"', "notes": "first line\nदूसरी पंक्ति"}]
    result = csv_rows(records_to_csv_bytes(source))
    assert result == source


def test_csv_handles_null_missing_nested_and_typed_values():
    source = [
        {"id": 7, "active": True, "missing": None, "nested": {"tags": ["a", "β"]}},
        {"id": 8, "active": False, "nested": [1, None]},
    ]
    parsed = csv_rows(records_to_csv_bytes(source))
    assert parsed == [
        {"id": "7", "active": "true", "missing": "", "nested": '{"tags":["a","β"]}'},
        {"id": "8", "active": "false", "missing": "", "nested": "[1,null]"},
    ]


def test_empty_csv_has_no_fake_header_or_records():
    assert records_to_csv_bytes([]) == b""


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), object()])
def test_csv_rejects_non_finite_or_unsupported_values(bad_value):
    with pytest.raises(ValueError):
        records_to_csv_bytes([{"value": bad_value}])


def test_csv_rejects_non_string_columns_and_non_mapping_rows():
    with pytest.raises(ValueError, match="column names"):
        records_to_csv_bytes([{1: "value"}])
    with pytest.raises(ValueError, match="mappings"):
        records_to_csv_bytes(["not a record"])


def test_report_loader_handles_missing_malformed_and_inconsistent_files(tmp_path):
    with pytest.raises(ValueError, match="could not be read"):
        load_evaluation_report(tmp_path / "missing.json")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_evaluation_report(malformed)

    inconsistent = tmp_path / "inconsistent.json"
    inconsistent.write_text(json.dumps({"total_tasks": 2, "records": [{"id": 1}]}))
    with pytest.raises(ValueError, match="does not match"):
        load_evaluation_report(inconsistent)

    inconsistent.write_text(json.dumps({
        "total_tasks": 1,
        "successful_decisions": 1,
        "errors": 0,
        "correct": 0,
        "accuracy_over_all_tasks": 1.0,
        "records": [{"correct": False, "error": None}],
    }))
    with pytest.raises(ValueError, match="accuracy"):
        load_evaluation_report(inconsistent)


def test_trace_loader_reports_invalid_lines_and_empty_files(tmp_path):
    trace = tmp_path / "mixed.jsonl"
    trace.write_text('{"id":1}\nnot-json\n[]\n', encoding="utf-8")
    events, warnings = load_trace_events(trace)
    assert events == [{"id": 1}]
    assert warnings == ["Line 2: invalid JSON.", "Line 3: expected a JSON object."]

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert load_trace_events(empty) == ([], [])
    with pytest.raises(ValueError, match="could not be read"):
        load_trace_events(tmp_path / "missing.jsonl")


def test_download_metadata_has_csv_extension_and_utf8_mime():
    assert csv_filename("/reports/mock v1.json", suffix="evaluation") == "mock_v1_evaluation.csv"
    assert csv_filename("demo.jsonl", suffix="trace") == "demo_trace.csv"
    assert CSV_MIME_TYPE == "text/csv; charset=utf-8"
