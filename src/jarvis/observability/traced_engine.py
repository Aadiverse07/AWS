from __future__ import annotations

from time import perf_counter

from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import DecisionEngine
from jarvis.observability.trace import JSONLTraceRecorder


class TracingDecisionEngine:
    """Record sanitized outcomes without logging prompts or exception messages."""

    def __init__(self, engine: DecisionEngine, recorder: JSONLTraceRecorder) -> None:
        self.engine = engine
        self.recorder = recorder

    def decide(self, request: DecisionRequest) -> DecisionResult:
        started = perf_counter()
        try:
            result = self.engine.decide(request)
        except Exception as exc:
            # Never include the prompt, context, or exception message in the trace.
            try:
                try:
                    threshold = self.engine.threshold_for(request.decision_id)
                except Exception:
                    # Sentinel used only when threshold lookup also fails.
                    threshold = 0.0
                self.recorder.record_decision(
                    run_id=request.run_id,
                    decision_id=request.decision_id,
                    step=request.step,
                    backend=self.engine.primary.name,
                    chosen="unavailable",
                    confidence=0.0,
                    threshold=threshold,
                    latency_ms=max(0.0, (perf_counter() - started) * 1000),
                    escalated=False,
                    final_choice="unavailable",
                    final_source=self.engine.primary.name,
                    status="error",
                    error_type=type(exc).__name__,
                )
            except Exception:
                # Preserve the original engine exception if trace storage fails.
                pass
            raise

        self.recorder.record_decision(
            run_id=request.run_id,
            decision_id=request.decision_id,
            step=request.step,
            backend=result.backend,
            chosen=result.chosen,
            confidence=result.confidence,
            threshold=self.engine.threshold_for(request.decision_id),
            latency_ms=result.latency_ms,
            escalated=result.escalated,
            final_choice=result.final_choice or result.chosen,
            final_source=result.final_source or result.backend,
            status="escalated" if result.escalated else "success",
        )
        return result
