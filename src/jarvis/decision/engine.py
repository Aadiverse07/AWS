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

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class InvalidFallbackChoiceError(DecisionEngineError):
    """The fallback backend chose something that is not a supplied option."""

    backend_role = "fallback"

    def __init__(self, message: str, *, escalation_reason: str) -> None:
        super().__init__(message)
        self.escalation_reason = escalation_reason


class InvalidPrimaryChoiceError(DecisionEngineError):
    """The primary backend chose something that is not a supplied option."""

    backend_role = "primary"


class InvalidBackendResultError(DecisionEngineError):
    """A backend returned a value outside the normalized result contract."""

    def __init__(
        self,
        message: str,
        *,
        backend_role: str,
        escalation_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.backend_role = backend_role
        self.escalation_reason = escalation_reason


class BackendInvocationError(DecisionEngineError):
    """A backend call failed; its arbitrary message is intentionally omitted."""

    def __init__(
        self,
        *,
        backend_role: str,
        error_type: str,
        escalation_reason: str | None = None,
        provider_outcome: str = "backend_error",
        request_attempted: bool | None = None,
    ) -> None:
        self.backend_role = backend_role
        self.error_type = error_type
        self.escalation_reason = escalation_reason
        self.provider_outcome = provider_outcome
        self.request_attempted = request_attempted
        super().__init__(
            f"{backend_role.capitalize()} backend failed ({provider_outcome})."
        )


def _invoke_backend(
    backend: DecisionBackend,
    request: DecisionRequest,
    role: str,
    escalation_reason: str | None = None,
) -> DecisionResult:
    try:
        result = backend.decide(request)
    except Exception as exc:
        provider_outcome = getattr(exc, "category", "backend_error")
        if not isinstance(provider_outcome, str):
            provider_outcome = "backend_error"
        request_attempted = getattr(exc, "request_attempted", None)
        if request_attempted not in (True, False, None):
            request_attempted = None
        raise BackendInvocationError(
            backend_role=role,
            error_type=getattr(exc, "error_type", type(exc).__name__),
            escalation_reason=escalation_reason,
            provider_outcome=provider_outcome,
            request_attempted=request_attempted,
        ) from None
    if not isinstance(result, DecisionResult):
        raise InvalidBackendResultError(
            f"{role.capitalize()} backend returned an invalid result structure",
            backend_role=role,
            escalation_reason=escalation_reason,
        )
    try:
        # Revalidate even an existing model instance. Backends can use
        # model_construct() or otherwise bypass normal Pydantic validation.
        return DecisionResult.model_validate(result.model_dump(mode="python"))
    except Exception:
        raise InvalidBackendResultError(
            f"{role.capitalize()} backend returned a malformed decision result",
            backend_role=role,
            escalation_reason=escalation_reason,
        ) from None


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
    fallback's own confidence is never checked. Backend exceptions are wrapped
    in a message-safe ``BackendInvocationError`` that identifies the failing
    backend role and exception type without retaining its arbitrary message.
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
            raise MissingThresholdError(
                "No confidence threshold is configured for this decision"
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

        primary_result = _invoke_backend(self.primary, request, "primary")
        if primary_result.chosen not in request.options:
            raise InvalidPrimaryChoiceError(
                "Primary backend selected an option not supplied in the request"
            )
        if not set(primary_result.scores).issubset(request.options):
            raise InvalidBackendResultError(
                "Primary backend returned scores for options not supplied in the request",
                backend_role="primary",
            )

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
                f"Decision needs escalation ({reason}), but no fallback backend is configured",
                reason=(
                    "confidence_unavailable"
                    if primary_result.confidence is None
                    else "below_threshold"
                ),
            )

        escalation_reason = (
            "confidence_unavailable"
            if primary_result.confidence is None
            else "below_threshold"
        )
        fallback_result = _invoke_backend(
            self.fallback, request, "fallback", escalation_reason
        )

        if fallback_result.chosen not in request.options:
            raise InvalidFallbackChoiceError(
                "Fallback backend selected an option not supplied in the request",
                escalation_reason=escalation_reason,
            )
        if not set(fallback_result.scores).issubset(request.options):
            raise InvalidBackendResultError(
                "Fallback backend returned scores for options not supplied in the request",
                backend_role="fallback",
                escalation_reason=escalation_reason,
            )

        return primary_result.model_copy(
            update={
                "escalated": True,
                "final_choice": fallback_result.chosen,
                "final_source": fallback_result.backend,
            },
            deep=True,
        )
