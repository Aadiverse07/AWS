import json

import pytest

from eval.audit_day1 import (
    AuditError,
    DEFAULT_INPUT,
    build_audit,
    render_markdown,
    write_outputs,
)


def retained_day1():
    return json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))


def test_audit_recomputes_historical_case_counts_and_latency():
    audit = build_audit(retained_day1())
    local = audit["backends"]["local_hf"]
    assert local["total_cases"] == 50
    assert local["correct_choices"] == 41
    assert local["incorrect_choices"] == 9
    assert local["runner_errors"] == 0
    assert local["accuracy"] == 0.82
    assert local["actual_fallback_invocations"] == 0
    assert local["threshold_derived_would_escalate_count"] == 27
    assert local["latency_audit"]["matches_stored_summary"] is True
    assert local["latency_audit"]["mean_ms"] == 295.691
    assert local["latency_audit"]["p50_ms"] == 108.882
    assert local["latency_audit"]["p95_ms"] == 126.547
    assert local["latency_audit"]["max_case_id"] == "T001"
    assert local["latency_audit"]["max_ms"] == 9374.305


def test_markdown_summary_is_rendered_from_machine_report():
    audit = build_audit(retained_day1())
    rendered = render_markdown(audit)
    assert "| mock | 50 | 18 | 32 | 0 | 36.0% | 0 | 0 (0.0%) |" in rendered
    assert "| local_hf | 50 | 41 | 9 | 0 | 82.0% | 0 | 27 (54.0%) |" in rendered
    assert "9,374.305 ms T001 outlier" in rendered
    assert "synthetic, hand-labeled" in rendered
    assert "do not establish real-world accuracy" in rendered


def test_audit_rejects_mismatched_case_accounting():
    data = retained_day1()
    data["backends"]["mock"]["correct"] += 1
    with pytest.raises(AuditError, match="correct count does not match"):
        build_audit(data)


def test_audit_outputs_preserve_existing_and_protected_inputs(tmp_path):
    audit = build_audit(retained_day1())
    source = tmp_path / "day1.json"
    source.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite an input"):
        write_outputs(audit, source, tmp_path / "report.md", (source,))
    assert source.read_text(encoding="utf-8") == "preserve"

    output_json = tmp_path / "out.json"
    output_md = tmp_path / "out.md"
    write_outputs(audit, output_json, output_md, ())
    assert json.loads(output_json.read_text(encoding="utf-8")) == audit
    assert output_md.read_text(encoding="utf-8") == render_markdown(audit)
    with pytest.raises(FileExistsError):
        write_outputs(audit, output_json, tmp_path / "other.md", ())
