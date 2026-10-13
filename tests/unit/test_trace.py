import json
import pytest
from jarvis.observability.trace import JSONLTraceRecorder, TraceValidationError

def sample():
    return dict(run_id="run-1", decision_id="D1", step=0, backend="mock", chosen="a", confidence=0.9, threshold=0.6, latency_ms=1.2, escalated=False, final_choice="a", final_source="mock")

def test_writes_valid_jsonl_event(tmp_path):
    path = tmp_path / "traces" / "events.jsonl"
    event = JSONLTraceRecorder(path).record_decision(**sample())
    stored = json.loads(path.read_text().strip())
    assert stored == event
    assert stored["schema_version"] == 1 and stored["event_type"] == "decision"
    assert stored["run_id"] == "run-1" and stored["escalated"] is False

def test_appends_events(tmp_path):
    path = tmp_path / "events.jsonl"
    recorder = JSONLTraceRecorder(path)
    recorder.record_decision(**sample())
    recorder.record_decision(**{**sample(), "step": 1})
    assert len(path.read_text().splitlines()) == 2

def test_rejects_invalid_confidence(tmp_path):
    with pytest.raises(TraceValidationError):
        JSONLTraceRecorder(tmp_path / "x.jsonl").record_decision(**{**sample(), "confidence": float("nan")})

def test_rejects_invalid_step(tmp_path):
    with pytest.raises(TraceValidationError):
        JSONLTraceRecorder(tmp_path / "x.jsonl").record_decision(**{**sample(), "step": -1})

def test_rejects_blank_identifiers(tmp_path):
    with pytest.raises(TraceValidationError):
        JSONLTraceRecorder(tmp_path / "x.jsonl").record_decision(**{**sample(), "run_id": " "})

def test_does_not_log_context_or_api_key_fields(tmp_path):
    path = tmp_path / "events.jsonl"
    JSONLTraceRecorder(path).record_decision(**sample())
    data = path.read_text()
    assert "context" not in data and "api_key" not in data and "token" not in data
