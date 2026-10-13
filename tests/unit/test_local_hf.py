from types import SimpleNamespace

import pytest

from jarvis.decision.backends.local_hf import LocalHFBackend
from jarvis.decision.contract import DecisionRequest


def make_request() -> DecisionRequest:
    return DecisionRequest(
        decision_id="D1",
        question="Which agent should handle this task?",
        context="The user asks about a GitHub repository.",
        options=["developer", "research"],
        run_id="run-001",
        step=0,
    )


class FakeEngine:
    def __init__(self, choice="developer"):
        self.choice = choice
        self.calls = []

    def ask(self, *, state, questions):
        self.calls.append((state, questions))
        return SimpleNamespace(
            answers={
                "decision": SimpleNamespace(
                    choice=self.choice,
                    probabilities={
                        "developer": 0.84,
                        "research": 0.16,
                    },
                    confidence=0.68,
                )
            }
        )


def test_local_hf_normalizes_engine_answer():
    engine = FakeEngine()
    backend = LocalHFBackend(engine=engine)

    result = backend.decide(make_request())

    assert result.chosen == "developer"
    assert result.scores == {"developer": 0.84, "research": 0.16}
    assert result.confidence == 0.68
    assert result.latency_ms >= 0
    assert result.backend == "local_hf"
    assert result.escalated is False


def test_local_hf_sends_question_and_context_to_engine():
    engine = FakeEngine()
    backend = LocalHFBackend(engine=engine)
    request = make_request()

    backend.decide(request)

    state, questions = engine.calls[0]
    assert state == request.context
    assert questions["decision"].instructions == request.question
    assert questions["decision"].criteria == {
        "developer": "developer",
        "research": "research",
    }


def test_local_hf_loads_engine_lazily_and_only_once():
    engine = FakeEngine()
    calls = []

    def factory(model_id, *, device):
        calls.append((model_id, device))
        return engine

    backend = LocalHFBackend(
        model_id="test/model",
        device="mps",
        engine_factory=factory,
    )

    assert calls == []
    backend.decide(make_request())
    backend.decide(make_request())

    assert calls == [("test/model", "mps")]


def test_local_hf_rejects_unexpected_choice():
    backend = LocalHFBackend(engine=FakeEngine(choice="unknown"))

    with pytest.raises(ValueError, match="not a supplied option"):
        backend.decide(make_request())


def test_local_hf_rejects_incomplete_probability_mapping():
    engine = FakeEngine()
    engine.ask = lambda **kwargs: SimpleNamespace(
        answers={
            "decision": SimpleNamespace(
                choice="developer",
                probabilities={"developer": 1.0},
                confidence=1.0,
            )
        }
    )
    backend = LocalHFBackend(engine=engine)

    with pytest.raises(ValueError, match="exactly the supplied options"):
        backend.decide(make_request())


def test_local_hf_rejects_blank_configuration():
    with pytest.raises(ValueError, match="model_id"):
        LocalHFBackend(model_id=" ")

    with pytest.raises(ValueError, match="device"):
        LocalHFBackend(device=" ")
