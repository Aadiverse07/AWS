import json

from jarvis.decision.backends.mock import MockBackend
from jarvis.decision.contract import DecisionRequest
from jarvis.decision.engine import DecisionEngine
from jarvis.observability.trace import JSONLTraceRecorder
from jarvis.observability.traced_engine import TracingDecisionEngine


def make_request():
    return DecisionRequest(
        decision_id="D1",
        question="Choose a safe next step",
        context="PRIVATE_CONTEXT_SHOULD_NOT_BE_LOGGED",
        options=["inspect", "execute"],
        run_id="trace-test-run",
        step=0,
    )


def test_tracing_records_event_and_preserves_result(tmp_path):
    req = make_request()
    expected = DecisionEngine(MockBackend(), {"D1": 0.6}).decide(req)
    path = tmp_path / "events.jsonl"
    traced = TracingDecisionEngine(DecisionEngine(MockBackend(), {"D1": 0.6}), JSONLTraceRecorder(path))
    actual = traced.decide(req)
    assert actual == expected
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["run_id"] == "trace-test-run"
    assert event["decision_id"] == "D1"
    assert event["threshold"] == 0.6
    assert event["final_choice"] == expected.final_choice
    assert event["final_source"] == expected.final_source
    assert event["status"] == "success"
    contents = path.read_text(encoding="utf-8")
    assert "PRIVATE_CONTEXT_SHOULD_NOT_BE_LOGGED" not in contents
    assert "question" not in contents


def test_tracing_appends_one_event_per_decision(tmp_path):
    path = tmp_path / "events.jsonl"
    traced = TracingDecisionEngine(DecisionEngine(MockBackend(), {"D1": 0.6}), JSONLTraceRecorder(path))
    traced.decide(make_request())
    traced.decide(make_request())
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


class FixedBackend:
    def __init__(self, name, chosen, confidence):
        self._name = name
        self._chosen = chosen
        self._confidence = confidence
        self.calls = 0

    @property
    def name(self):
        return self._name

    def decide(self, request):
        from jarvis.decision.contract import DecisionResult
        self.calls += 1
        return DecisionResult(
            chosen=self._chosen,
            scores={option: (1.0 if option == self._chosen else 0.0) for option in request.options},
            confidence=self._confidence,
            latency_ms=1.0,
            backend=self._name,
        )


def test_traced_fallback_records_final_choice_and_source(tmp_path):
    primary = FixedBackend("primary", "inspect", 0.2)
    fallback = FixedBackend("fallback", "execute", 0.1)
    engine = DecisionEngine(primary, {"D1": 0.6}, fallback=fallback)
    path = tmp_path / "fallback.jsonl"
    traced = TracingDecisionEngine(engine, JSONLTraceRecorder(path))

    result = traced.decide(make_request())

    assert result.chosen == "inspect"
    assert result.backend == "primary"
    assert result.confidence == 0.2
    assert result.escalated is True
    assert result.final_choice == "execute"
    assert result.final_source == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1, "fallback confidence must not trigger another fallback call"

    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["chosen"] == "inspect"
    assert event["backend"] == "primary"
    assert event["confidence"] == 0.2
    assert event["threshold"] == 0.6
    assert event["escalated"] is True
    assert event["final_choice"] == "execute"
    assert event["final_source"] == "fallback"
    assert event["status"] == "escalated"
    assert event["fallback_invoked"] is True
    assert event["escalation_reason"] == "below_threshold"
    assert event["validation_passed"] is True


def test_traced_engine_records_sanitized_error_when_escalation_is_unavailable(tmp_path):
    import pytest
    from jarvis.decision.engine import EscalationUnavailableError

    primary = FixedBackend("primary", "inspect", 0.2)
    path = tmp_path / "unavailable.jsonl"
    traced = TracingDecisionEngine(DecisionEngine(primary, {"D1": 0.6}), JSONLTraceRecorder(path))
    request = make_request()

    with pytest.raises(EscalationUnavailableError) as caught:
        traced.decide(request)

    assert primary.calls == 1
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["status"] == "error"
    assert event["error_type"] == "EscalationUnavailableError"
    assert event["chosen"] is None
    assert event["final_choice"] is None
    assert event["fallback_invoked"] is False
    assert event["escalation_reason"] == "below_threshold"
    assert event["validation_passed"] is True
    assert "PRIVATE_CONTEXT_SHOULD_NOT_BE_LOGGED" not in path.read_text(encoding="utf-8")
    assert request.question not in path.read_text(encoding="utf-8")
    assert str(caught.value)  # Original exception is still raised.


def test_unknown_confidence_trace_records_actual_fallback_and_null_confidence(tmp_path):
    primary = FixedBackend("primary", "inspect", None)
    fallback = FixedBackend("fallback", "execute", 0.8)
    path = tmp_path / "unknown-confidence.jsonl"
    traced = TracingDecisionEngine(
        DecisionEngine(primary, {"D1": 0.6}, fallback), JSONLTraceRecorder(path)
    )
    result = traced.decide(make_request())
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert result.final_choice == "execute"
    assert event["confidence"] is None
    assert event["fallback_invoked"] is True
    assert event["escalation_reason"] == "confidence_unavailable"
    assert event["final_choice"] == "execute"


def test_fallback_exception_trace_identifies_stage_without_message(tmp_path):
    import pytest
    from jarvis.decision.engine import BackendInvocationError

    primary = FixedBackend("primary", "inspect", 0.2)

    class FailingFallback(FixedBackend):
        def decide(self, request):
            self.calls += 1
            raise RuntimeError("AWS_ACCESS_KEY_ID=secret-value")

    fallback = FailingFallback("fallback", "execute", 0.9)
    path = tmp_path / "fallback-error.jsonl"
    traced = TracingDecisionEngine(
        DecisionEngine(primary, {"D1": 0.6}, fallback), JSONLTraceRecorder(path)
    )
    with pytest.raises(BackendInvocationError) as caught:
        traced.decide(make_request())
    text = path.read_text(encoding="utf-8")
    event = json.loads(text.splitlines()[0])
    assert "secret-value" not in text and "AWS_ACCESS_KEY_ID" not in text
    assert "secret-value" not in str(caught.value)
    assert event["status"] == "error"
    assert event["error_category"] == "fallback_backend_error"
    assert event["backend_role"] == "fallback"
    assert event["fallback_invoked"] is True
    assert event["escalation_reason"] == "below_threshold"


def test_invalid_primary_choice_is_traced_as_rejected(tmp_path):
    import pytest
    from jarvis.decision.contract import DecisionResult
    from jarvis.decision.engine import InvalidPrimaryChoiceError

    class InvalidBackend:
        name = "primary"

        def decide(self, request):
            return DecisionResult(
                chosen="authorization: Bearer secret-value",
                scores={},
                confidence=0.9,
                latency_ms=1.0,
                backend="primary",
            )

    path = tmp_path / "rejected.jsonl"
    traced = TracingDecisionEngine(
        DecisionEngine(InvalidBackend(), {"D1": 0.6}), JSONLTraceRecorder(path)
    )
    with pytest.raises(InvalidPrimaryChoiceError):
        traced.decide(make_request())
    text = path.read_text(encoding="utf-8")
    event = json.loads(text.splitlines()[0])
    assert "secret-value" not in text
    assert event["status"] == "rejected"
    assert event["error_category"] == "invalid_primary_choice"
    assert event["validation_passed"] is False
    assert event["fallback_invoked"] is False


def test_error_trace_failure_does_not_mask_engine_exception(tmp_path):
    import pytest

    class BrokenRecorder:
        def record_decision(self, **kwargs):
            raise OSError("TRACE_STORAGE_SECRET_FAILURE")

    class BrokenBackend:
        name = "broken"

        def decide(self, request):
            raise RuntimeError("PRIVATE_EXCEPTION_MESSAGE")

    engine = DecisionEngine(BrokenBackend(), {"D1": 0.6})
    traced = TracingDecisionEngine(engine, BrokenRecorder())

    from jarvis.decision.engine import BackendInvocationError

    with pytest.raises(BackendInvocationError) as caught:
        traced.decide(make_request())
    assert "PRIVATE_EXCEPTION_MESSAGE" not in str(caught.value)
