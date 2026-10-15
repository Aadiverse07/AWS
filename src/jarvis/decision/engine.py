"""Confidence-based decision engine with a single, bounded escalation step.

The engine is provider-independent. It depends only on the ``DecisionBackend``
interface and the ``DecisionResult`` contract, so any backend (local model,
hosted LLM, mock) can be plugged in as the primary or the fallback.
"""

import math
from collections.abc import Mapping

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult


class DecisionEngineError(RuntimeError):
    """Base class for errors raised while the engine makes a decision."""


class MissingThresholdError(DecisionEngineError):
    """No confidence threshold is configured for a decision ID."""


class EscalationUnavailableError(DecisionEngineError):
    """Escalation is required but no fallback backend is configured."""


class InvalidFallbackChoiceError(DecisionEngineError):
    """The fallback backend chose something that is not a supplied option."""


def _validate_threshold(decision_id: str, value: object) -> float:
    """Return ``value`` as a float, or raise ``ValueError`` if it is invalid."""
    # bool is a subclass of int, so it must be rejected explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"threshold for {decision_id!r} must be a number, "
            f"got {type(value).__name__}"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"threshold for {decision_id!r} must be finite, got {value!r}"
        )
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"threshold for {decision_id!r} must be between 0.0 and 1.0 "
            f"inclusive, got {value!r}"
        )
    return float(value)


def _validate_thresholds(thresholds: Mapping[str, float]) -> dict[str, float]:
    """Validate the mapping and return a private, normalized copy.

    Decision IDs are stripped of surrounding whitespace, because
    ``DecisionRequest`` strips ``decision_id`` and lookups must match it.
    """
    if not isinstance(thresholds, Mapping):
        raise TypeError(
            "thresholds must be a mapping of decision IDs to thresholds"
        )
    if not thresholds:
        raise ValueError("thresholds must not be empty")

    validated: dict[str, float] = {}
    for decision_id, value in thresholds.items():
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError(
                f"decision IDs must be non-blank strings, got {decision_id!r}"
            )
        key = decision_id.strip()
        if key in validated:
            raise ValueError(
                f"duplicate decision ID after trimming whitespace: {key!r}"
            )
        validated[key] = _validate_threshold(key, value)

    return validated


class DecisionEngine:
    """Call a primary backend and escalate to a fallback when unsure.

    Each ``decide`` call makes exactly one primary call and at most one
    fallback call. There are no retries, no loops, and no recursion: the
    fallback's own confidence is never checked, and backend exceptions
    propagate unchanged.
    """

    def __init__(
        self,
        primary: DecisionBackend,
        thresholds: Mapping[str, float],
        fallback: DecisionBackend | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._thresholds = _validate_thresholds(thresholds)

    def _threshold_for(self, decision_id: str) -> float:
        try:
            return self._thresholds[decision_id]
        except KeyError:
            configured = ", ".join(repr(key) for key in sorted(self._thresholds))
            raise MissingThresholdError(
                f"No confidence threshold configured for decision ID "
                f"{decision_id!r}. Configured decision IDs: {configured}"
            ) from None

    def threshold_for(self, decision_id: str) -> float:
        """Return the configured confidence threshold for a decision."""
        return self._threshold_for(decision_id)

    def decide(self, request: DecisionRequest) -> DecisionResult:
        """Return the primary result annotated with the final choice.

        The primary result's ``chosen``, ``scores``, ``confidence``,
        ``latency_ms`` and ``backend`` are always preserved. ``final_choice``
        and ``final_source`` describe who supplied the final answer.
        """
        # Fail on a missing threshold before spending any backend call.
        threshold = self._threshold_for(request.decision_id)

        primary_result = self.primary.decide(request)

        if (
            primary_result.confidence is not None
            and primary_result.confidence >= threshold
        ):
            return primary_result.model_copy(
                update={
                    "escalated": False,
                    "final_choice": primary_result.chosen,
                    "final_source": primary_result.backend,
                },
                deep=True,
            )

        if self.fallback is None:
            reason = (
                "confidence is unknown"
                if primary_result.confidence is None
                else f"confidence {primary_result.confidence} is below "
                f"threshold {threshold}"
            )
            raise EscalationUnavailableError(
                f"Decision {request.decision_id!r} needs escalation "
                f"({reason}), but no fallback backend is configured"
            )

        fallback_result = self.fallback.decide(request)

        if fallback_result.chosen not in request.options:
            raise InvalidFallbackChoiceError(
                f"Fallback backend {fallback_result.backend!r} selected "
                f"{fallback_result.chosen!r}, which is not a supplied option"
            )

        return primary_result.model_copy(
            update={
                "escalated": True,
                "final_choice": fallback_result.chosen,
                "final_source": fallback_result.backend,
            },
            deep=True,
        )
