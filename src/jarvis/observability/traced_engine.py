"""Decision-engine wrapper that emits sanitized schema-v3 traces."""

from __future__ import annotations

from time import perf_counter
from typing import Any

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


class _ObservedBedrockBackend:
    """Emit a metadata-only event for each logical Bedrock Converse call."""

    def __init__(self, backend: Any, recorder: JSONLTraceRecorder, role: str) -> None:
        self.backend = backend
        self.recorder = recorder
        self.role = role
        observer_setter = getattr(backend, "set_attempt_observer", None)
        self._native_observer = callable(observer_setter)
        if self._native_observer:
            observer_setter(self._record_native_attempt)

    @property
    def name(self) -> str:
        return self.backend.name

    def decide(self, request: DecisionRequest) -> DecisionResult:
        if self._native_observer:
            return self.backend.decide(request)
        started = perf_counter()
        try:
            result = self.backend.decide(request)
        except Exception as exc:
            outcome = getattr(exc, "category", "backend_error")
            if not isinstance(outcome, str):
                outcome = "backend_error"
            attempted = getattr(exc, "request_attempted", True)
            if attempted not in (True, False, None):
                attempted = None
            error_type = getattr(exc, "error_type", type(exc).__name__)
            status = "rejected" if outcome in {"invalid_request", "invalid_response"} else "error"
            error_category = (
                "invalid_backend_result"
                if outcome == "invalid_response"
                else f"{self.role}_backend_error"
            )
            try:
                self._record(
                    request,
                    started,
                    request_attempted=attempted,
                    provider_outcome=outcome,
                    status=status,
                    validation_passed=False if status == "rejected" else None,
                    error_category=error_category,
                    error_type=error_type,
                )
            except Exception:
                # Preserve the provider failure; a failed error trace must not
                # replace it or authorize the workflow's action.
                pass
            raise

        self._record(
            request,
            started,
            request_attempted=True,
            provider_outcome="success",
            status="success",
            validation_passed=True,
        )
        return result

    def _record(
        self,
        request: DecisionRequest,
        started: float,
        *,
        request_attempted: bool | None,
        provider_outcome: str,
        status: str,
        validation_passed: bool | None,
        error_category: str | None = None,
        error_type: str | None = None,
        provider_attempt: int | None = None,
    ) -> None:
        self.recorder.record_decision(
            run_id=request.run_id,
            decision_id=request.decision_id,
            step=request.step,
            backend=self.name,
            backend_role=self.role,
            event_type="backend_attempt",
            chosen=None,
            confidence=None,
            threshold=None,
            latency_ms=max(0.0, (perf_counter() - started) * 1000),
            escalated=False,
            fallback_invoked=self.role == "fallback",
            escalation_reason=None,
            validation_passed=validation_passed,
            final_choice=None,
            final_source=None,
            status=status,
            error_category=error_category,
            error_type=error_type,
            request_attempted=request_attempted,
            provider_outcome=provider_outcome,
            provider_attempt=provider_attempt,
        )

    def _record_native_attempt(
        self,
        request: DecisionRequest,
        provider_attempt: int,
        request_attempted: bool,
        provider_outcome: str,
        status: str,
        started: float,
        error_type: str | None,
    ) -> None:
        validation_passed = (
            True if status == "success" else False if status == "rejected" else None
        )
        error_category = None
        if status != "success":
            error_category = (
                "invalid_backend_result"
                if provider_outcome == "invalid_response"
                else f"{self.role}_backend_error"
            )
        try:
            self._record(
                request,
                started,
                request_attempted=request_attempted,
                provider_outcome=provider_outcome,
                status=status,
                validation_passed=validation_passed,
                error_category=error_category,
                error_type=error_type,
                provider_attempt=provider_attempt,
            )
        except Exception:
            if status == "success":
                raise


class TracingDecisionEngine:
    """Record schema-v3 events without prompts or exception text."""

    def __init__(self, engine: DecisionEngine, recorder: JSONLTraceRecorder) -> None:
        self.engine = engine
        self.recorder = recorder
        if self.engine.primary.name == "bedrock":
            self.engine.primary = _ObservedBedrockBackend(
                self.engine.primary, recorder, "primary"
            )
        if self.engine.fallback is not None and self.engine.fallback.name == "bedrock":
            self.engine.fallback = _ObservedBedrockBackend(
                self.engine.fallback, recorder, "fallback"
            )

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
            request_attempted=True if result.backend == "bedrock" else None,
            provider_outcome="success" if result.backend == "bedrock" else None,
        )
        return result

    def _record_failure(
        self, request: DecisionRequest, exc: Exception, started: float
    ) -> None:
        role = getattr(exc, "backend_role", None)
        fallback_invoked = role == "fallback"
        request_attempted = getattr(exc, "request_attempted", None)
        if request_attempted not in (True, False, None):
            request_attempted = None
        provider_outcome = getattr(exc, "provider_outcome", None)
        if not isinstance(provider_outcome, str):
            provider_outcome = None
        if isinstance(exc, BackendInvocationError):
            error_category = (
                "fallback_backend_error"
                if role == "fallback"
                else "primary_backend_error"
            )
            error_type = exc.error_type
            validation_passed = (
                False if exc.provider_outcome in {"invalid_request", "invalid_response"}
                else None
            )
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
                request_attempted=request_attempted,
                provider_outcome=provider_outcome,
            )
        except Exception:
            # Preserve the engine failure; a failed error trace cannot fabricate
            # success or authorize an action.
            pass
