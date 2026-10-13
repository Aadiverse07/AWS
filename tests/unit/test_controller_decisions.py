import pytest

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import DecisionEngine, EscalationUnavailableError
from jarvis.orchestrator.controller import choose_next_action


class FixedBackend(DecisionBackend):
    def __init__(self, name, choice, confidence):
        self._name = name
        self.choice = choice
        self.confidence = confidence
        self.calls = 0

    @property
    def name(self):
        return self._name

    def decide(self, request: DecisionRequest) -> DecisionResult:
        self.calls += 1
        return DecisionResult(
            chosen=self.choice,
            scores={
                option: 1.0 if option == self.choice else 0.0
                for option in request.options
            },
            confidence=self.confidence,
            latency_ms=1.0,
            backend=self.name,
        )


def test_high_confidence_returns_recommendation_without_execution():
    primary = FixedBackend("primary", "inspect", 0.9)
    engine = DecisionEngine(primary, {"D1": 0.6})

    result = choose_next_action(
        engine=engine,
        run_id="run-1",
        question="What should happen next?",
        context="Read-only review",
        options=["inspect", "summarize"],
    )

    assert result.recommended_action == "inspect"
    assert result.primary_choice == "inspect"
    assert result.requires_review is True
    assert result.escalated is False
    assert primary.calls == 1


def test_low_confidence_uses_configured_fallback_choice():
    primary = FixedBackend("primary", "inspect", 0.2)
    fallback = FixedBackend("fallback", "summarize", 0.9)
    engine = DecisionEngine(primary, {"D1": 0.6}, fallback=fallback)

    result = choose_next_action(
        engine=engine,
        run_id="run-2",
        question="What should happen next?",
        context="Read-only review",
        options=["inspect", "summarize"],
    )

    assert result.primary_choice == "inspect"
    assert result.recommended_action == "summarize"
    assert result.final_source == "fallback"
    assert result.escalated is True
    assert result.requires_review is True
    assert primary.calls == 1
    assert fallback.calls == 1


def test_invalid_options_are_rejected_before_backend_call():
    primary = FixedBackend("primary", "inspect", 0.9)
    engine = DecisionEngine(primary, {"D1": 0.6})

    with pytest.raises(ValueError):
        choose_next_action(
            engine=engine,
            run_id="run-3",
            question="Choose an action",
            context="",
            options=["inspect", "inspect"],
        )

    assert primary.calls == 0


def test_low_confidence_without_fallback_fails_safely():
    primary = FixedBackend("primary", "inspect", 0.2)
    engine = DecisionEngine(primary, {"D1": 0.6})

    with pytest.raises(EscalationUnavailableError, match='no fallback'):
        choose_next_action(
            engine=engine,
            run_id="run-4",
            question="Choose an action",
            context="",
            options=["inspect", "summarize"],
        )

    assert primary.calls == 1


def test_tracing_wrapper_can_be_used_by_controller(tmp_path):
    from jarvis.observability.trace import JSONLTraceRecorder
    from jarvis.observability.traced_engine import TracingDecisionEngine

    primary = FixedBackend("primary", "inspect", 0.9)
    engine = DecisionEngine(primary, {"D1": 0.6})
    traced = TracingDecisionEngine(
        engine,
        JSONLTraceRecorder(tmp_path / "controller-events.jsonl"),
    )

    result = choose_next_action(
        engine=traced,
        run_id="traced-run",
        question="What should happen next?",
        context="Read-only review",
        options=["inspect", "summarize"],
    )

    assert result.recommended_action == "inspect"
    assert result.final_source == "primary"
    assert result.requires_review is True
    assert len((tmp_path / "controller-events.jsonl").read_text().splitlines()) == 1
