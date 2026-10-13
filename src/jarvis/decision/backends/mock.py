"""Deterministic backend for development and testing."""

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult


class MockBackend(DecisionBackend):
    """Always select the first option without calling an AI model."""

    @property
    def name(self) -> str:
        return "mock"

    def decide(self, request: DecisionRequest) -> DecisionResult:
        chosen = request.options[0]

        scores = {
            option: 1.0 if option == chosen else 0.0
            for option in request.options
        }

        return DecisionResult(
            chosen=chosen,
            scores=scores,
            confidence=1.0,
            latency_ms=0.0,
            backend=self.name,
        )
