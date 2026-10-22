"""Data loading and CSV serialization shared by the local dashboard."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

CSV_MIME_TYPE = "text/csv; charset=utf-8"


def load_evaluation_report(path: str | Path) -> dict[str, Any]:
    """Load one evaluation JSON report and verify its record count."""
    report_path = Path(path)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Report could not be read as valid UTF-8 JSON: {report_path.name}"
        ) from exc
    if not isinstance(report, dict):
        raise ValueError(f"Report must contain a JSON object: {report_path.name}")
    records = report.get("records")
    total = report.get("total_tasks")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f"Report records must be a list of objects: {report_path.name}")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError(
            f"Report total_tasks must be a non-negative integer: {report_path.name}"
        )
    if total != len(records):
        raise ValueError(
            f"Report total_tasks ({total}) does not match its {len(records)} records: "
            f"{report_path.name}"
        )
    counts = (report.get("successful_decisions"), report.get("errors"), report.get("correct"))
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError(f"Report decision counts are invalid: {report_path.name}")
    successful, errors, correct = counts
    if any(not isinstance(row.get("correct"), bool) for row in records):
        raise ValueError(f"Report record correctness values are invalid: {report_path.name}")
    record_errors = sum(row.get("error") is not None for row in records)
    record_correct = sum(row.get("correct") is True for row in records)
    if successful + errors != total or errors != record_errors or correct != record_correct:
        raise ValueError(f"Report decision totals do not match its records: {report_path.name}")
    accuracy = report.get("accuracy_over_all_tasks")
    expected_accuracy = correct / total if total else 0.0
    if (
        isinstance(accuracy, bool)
        or not isinstance(accuracy, (int, float))
        or not math.isfinite(accuracy)
        or not math.isclose(accuracy, expected_accuracy, abs_tol=0.00005)
    ):
        raise ValueError(f"Report accuracy does not match its records: {report_path.name}")
    policy = report.get("escalation_policy")
    if not isinstance(policy, dict):
        raise ValueError(f"Report escalation policy is invalid: {report_path.name}")
    would_escalate = policy.get("would_escalate")
    escalation_rate = policy.get("rate_over_all_tasks")
    record_escalations = sum(row.get("would_escalate") is True for row in records)
    expected_escalation_rate = would_escalate / total if total else 0.0
    if (
        isinstance(would_escalate, bool)
        or not isinstance(would_escalate, int)
        or would_escalate != record_escalations
        or isinstance(escalation_rate, bool)
        or not isinstance(escalation_rate, (int, float))
        or not math.isfinite(escalation_rate)
        or not math.isclose(escalation_rate, expected_escalation_rate, abs_tol=0.00005)
    ):
        raise ValueError(f"Report escalation totals do not match its records: {report_path.name}")
    latency = report.get("latency_ms")
    if not isinstance(latency, dict):
        raise ValueError(f"Report latency summary is invalid: {report_path.name}")
    for key in ("mean", "p50", "p95"):
        value = latency.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Report latency value {key} is invalid: {report_path.name}")
    return report


def load_trace_events(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Load JSONL trace objects and return per-line parse/shape warnings."""
    trace_path = Path(path)
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Trace could not be read as UTF-8: {trace_path.name}") from exc

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"Line {line_number}: invalid JSON.")
            continue
        if not isinstance(event, dict):
            errors.append(f"Line {line_number}: expected a JSON object.")
            continue
        events.append(event)
    return events, errors


def csv_filename(name: str, *, suffix: str = "records") -> str:
    """Return a safe, predictable CSV filename for a report or trace."""
    stem = Path(name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "data"
    safe_suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", suffix).strip("_- ") or "records"
    return f"{safe_stem}_{safe_suffix}.csv"


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("CSV nested values must contain valid JSON data") from exc
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("CSV numeric values must be finite")
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ValueError(f"Unsupported CSV value type: {type(value).__name__}")


def records_to_csv_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    """Serialize mappings as escaped UTF-8 CSV with a first-seen header.

    Nested JSON values remain present in a cell as compact JSON. Missing keys
    and explicit null values are empty cells. Empty input returns empty bytes;
    callers should omit its download control.
    """
    rows = list(records)
    if not rows:
        return b""
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("CSV records must all be mappings")

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if not isinstance(key, str):
                raise ValueError("CSV column names must be strings")
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=fieldnames, extrasaction="raise", lineterminator="\r\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
    # The BOM keeps Unicode CSV readable in common spreadsheet applications.
    return output.getvalue().encode("utf-8-sig")
