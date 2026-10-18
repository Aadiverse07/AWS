"""Decision-engine wrapper that emits sanitized schema-v2 traces."""

from __future__ import annotations

from time import perf_counter

from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import (
    BackendInvocationError,
    DecisionEngine,
    EscalationUnavailableError,
    InvalidBackendResultError,
    InvalidFallbackChoiceError,
    InvalidPrimaryChoiceError,
)
from jarvis.observability.trace import JSONLTraceRecorder


class TracingDecisionEngine:
    """Record allowlisted fields; never serialize prompts or exception text."""

    def __init__(self, engine: DecisionEngine, recorder: JSONLTraceRecorder) -> None:
        self.engine = engine
        self.recorder = recorder

    def decide(self, request: DecisionRequest) -> DecisionResult:
        started = perf_counter()
        try:
            result = self.engine.decide(request)
        except Exception as exc:
            self._record_failure(request, exc, started)
            raise

        reason = None
        if result.escalated:
            reason = (
                "confidence_unavailable"
                if result.confidence is None
                else "below_threshold"
            )
        self.recorder.record_decision(
            run_id=request.run_id,
            decision_id=request.decision_id,
            step=request.step,
            backend=result.backend,
            backend_role="primary",
            chosen=result.chosen,
            confidence=result.confidence,
            threshold=self.engine.threshold_for(request.decision_id),
            latency_ms=max(0.0, (perf_counter() - started) * 1000),
            escalated=result.escalated,
            fallback_invoked=result.escalated,
            escalation_reason=reason,
            validation_passed=True,
            final_choice=result.final_choice or result.chosen,
            final_source=result.final_source or result.backend,
            status="escalated" if result.escalated else "success",
        )
        return result

    def _record_failure(
        self, request: DecisionRequest, exc: Exception, started: float
    ) -> None:
        role = getattr(exc, "backend_role", None)
        fallback_invoked = role == "fallback"
        if isinstance(exc, BackendInvocationError):
            error_category = (
                "fallback_backend_error"
                if role == "fallback"
                else "primary_backend_error"
            )
            error_type = exc.error_type
            validation_passed = None
        elif isinstance(exc, InvalidPrimaryChoiceError):
            error_category = "invalid_primary_choice"
            error_type = type(exc).__name__
            validation_passed = False
        elif isinstance(exc, InvalidFallbackChoiceError):
            error_category = "invalid_fallback_choice"
            error_type = type(exc).__name__
            validation_passed = False
        elif isinstance(exc, InvalidBackendResultError):
            error_category = "invalid_backend_result"
            error_type = type(exc).__name__
            validation_passed = False
        elif isinstance(exc, EscalationUnavailableError):
            error_category = "escalation_unavailable"
            error_type = type(exc).__name__
            validation_passed = True
        else:
            error_category = "decision_error"
            error_type = type(exc).__name__
            validation_passed = None

        threshold = None
        try:
            threshold = self.engine.threshold_for(request.decision_id)
        except Exception:
            pass

        backend = self.engine.primary.name
        if fallback_invoked and self.engine.fallback is not None:
            backend = self.engine.fallback.name
        escalation_reason = getattr(exc, "escalation_reason", None)
        if isinstance(exc, EscalationUnavailableError):
            escalation_reason = exc.reason
        status = "rejected" if validation_passed is False else "error"
        try:
            self.recorder.record_decision(
                run_id=request.run_id,
                decision_id=request.decision_id,
                step=request.step,
                backend=backend,
                backend_role=role,
                chosen=None,
                confidence=None,
                threshold=threshold,
                latency_ms=max(0.0, (perf_counter() - started) * 1000),
                escalated=False,
                fallback_invoked=fallback_invoked,
                escalation_reason=escalation_reason,
                validation_passed=validation_passed,
                final_choice=None,
                final_source=None,
                status=status,
                error_category=error_category,
                error_type=error_type,
            )
        except Exception:
            # Preserve the engine failure; a failed error trace cannot fabricate
            # success or authorize an action.
            pass
