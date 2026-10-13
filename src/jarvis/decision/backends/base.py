"""Provider-independent interface for decision backends."""

from abc import ABC, abstractmethod

from jarvis.decision.contract import DecisionRequest, DecisionResult


class DecisionBackend(ABC):
    """Interface implemented by every decision backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable identifier for this backend."""

    @abstractmethod
    def decide(self, request: DecisionRequest) -> DecisionResult:
        """Choose an option and return a normalized decision result."""
