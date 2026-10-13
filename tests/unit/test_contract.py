import pytest
from pydantic import ValidationError

from jarvis.decision.contract import DecisionRequest, DecisionResult


def test_valid_decision_request():
    request = DecisionRequest(
        decision_id="D1",
        question="Which agent should handle this?",
        context="The user asks about a GitHub repository.",
        options=["developer", "research"],
        run_id="run-001",
        step=0,
    )

    assert request.options == ["developer", "research"]
    assert request.step == 0


def test_request_rejects_duplicate_options():
    with pytest.raises(ValidationError):
        DecisionRequest(
            decision_id="D1",
            question="Choose an agent",
            options=["developer", "developer"],
            run_id="run-001",
            step=0,
        )


def test_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        DecisionRequest(
            decision_id="D1",
            question="Choose an agent",
            options=["developer", "research"],
            run_id="run-001",
            step=0,
            unexpected="not allowed",
        )


def test_valid_decision_result():
    result = DecisionResult(
        chosen="developer",
        scores={"developer": 0.8412, "research": 0.1588},
        confidence=0.6825,
        latency_ms=106.07,
        backend="local_hf",
    )

    assert result.chosen == "developer"
    assert result.confidence == 0.6825
    assert result.escalated is False


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_result_rejects_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        DecisionResult(
            chosen="developer",
            scores={"developer": 1.0},
            confidence=confidence,
            latency_ms=10.0,
            backend="mock",
        )


def test_result_rejects_negative_latency():
    with pytest.raises(ValidationError):
        DecisionResult(
            chosen="developer",
            scores={"developer": 1.0},
            confidence=0.9,
            latency_ms=-1.0,
            backend="mock",
        )
