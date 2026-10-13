import pytest
from pydantic import ValidationError

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.backends.mock import MockBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult


def make_request() -> DecisionRequest:
    return DecisionRequest(
        decision_id="D1",
        question="Which agent should handle this?",
        context="The user asks about a GitHub repository.",
        options=["developer", "research"],
        run_id="run-001",
        step=0,
    )


def test_backend_interface_cannot_be_instantiated():
    with pytest.raises(TypeError):
        DecisionBackend()


def test_mock_backend_implements_interface():
    backend = MockBackend()

    assert isinstance(backend, DecisionBackend)
    assert backend.name == "mock"


def test_mock_backend_selects_first_option_deterministically():
    backend = MockBackend()
    request = make_request()

    first = backend.decide(request)
    second = backend.decide(request)

    assert first == second
    assert first.chosen == "developer"
    assert first.scores == {"developer": 1.0, "research": 0.0}
    assert first.confidence == 1.0
    assert first.latency_ms == 0.0
    assert first.backend == "mock"


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan"), float("inf")])
def test_result_rejects_invalid_scores(score):
    with pytest.raises(ValidationError):
        DecisionResult(
            chosen="developer",
            scores={"developer": score},
            confidence=0.9,
            latency_ms=10.0,
            backend="mock",
        )


def test_result_rejects_choice_missing_from_scores():
    with pytest.raises(ValidationError):
        DecisionResult(
            chosen="research",
            scores={"developer": 1.0},
            confidence=0.9,
            latency_ms=10.0,
            backend="mock",
        )
