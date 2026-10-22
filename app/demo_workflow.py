"""Truthful, deterministic scenarios for the interactive dashboard demo."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.application import ROUTING_DESTINATIONS, WorkflowOutcome, run_workflow
from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.backends.mock import MockBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import DecisionEngine
from jarvis.observability.trace import JSONLTraceRecorder
from jarvis.observability.traced_engine import TracingDecisionEngine

THRESHOLD = 0.60
SCENARIOS = {
    "Standard mock": "The mock backend selects the first supplied route at confidence 1.0.",
    "Low-confidence fallback fixture": "A deterministic fixture returns 0.20 confidence; the engine invokes its mock fallback once.",
    "Backend error fixture": "A deterministic fixture raises a backend error; the routing action is not called.",
}


@dataclass(frozen=True)
class DemoRun:
    """One actual workflow execution and the trace emitted by its engine."""

    request: DecisionRequest
    outcome: WorkflowOutcome | None
    error_type: str | None
    trace_events: list[dict[str, Any]]
    scenario: str


class _LowConfidenceFixture(DecisionBackend):
    name = "fixture_primary"

    def decide(self, request: DecisionRequest) -> DecisionResult:
        choice = "documentation" if "documentation" in request.options else request.options[-1]
        return DecisionResult(
            chosen=choice,
            scores={option: float(option == choice) for option in request.options},
            confidence=0.20,
            latency_ms=0.0,
            backend=self.name,
        )


class _ErrorFixture(DecisionBackend):
    name = "fixture_primary"

    def decide(self, request: DecisionRequest) -> DecisionResult:
        raise RuntimeError("Deterministic dashboard error fixture")


def run_demo_decision(
    *, scenario: str, question: str, preferred_route: str
) -> DemoRun:
    """Run a supported local engine path and capture its sanitized JSONL event."""
    if scenario not in SCENARIOS:
        raise ValueError("Choose one of the supported demo scenarios")
    if preferred_route not in ROUTING_DESTINATIONS:
        raise ValueError("Choose an allowed routing destination")
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        raise ValueError("Task description must contain 1 to 500 characters")

    options = [preferred_route, *(route for route in ROUTING_DESTINATIONS if route != preferred_route)]
    request = DecisionRequest(
        decision_id="D1",
        question=question.strip(),
        context="Dashboard demonstration. Route only; do not execute task content.",
        options=options,
        run_id=uuid4().hex,
        step=0,
    )

    if scenario == "Standard mock":
        engine = DecisionEngine(MockBackend(), {"D1": THRESHOLD})
    elif scenario == "Low-confidence fallback fixture":
        engine = DecisionEngine(
            _LowConfidenceFixture(), {"D1": THRESHOLD}, fallback=MockBackend()
        )
    else:
        engine = DecisionEngine(_ErrorFixture(), {"D1": THRESHOLD})

    with tempfile.TemporaryDirectory(prefix="jarvis-dashboard-trace-") as directory:
        trace_path = Path(directory) / "decision.jsonl"
        traced = TracingDecisionEngine(engine, JSONLTraceRecorder(trace_path))
        outcome = None
        error_type = None
        try:
            outcome = run_workflow(request, traced)
        except Exception as exc:
            # The UI shows a safe exception type; the exception message is not
            # exposed because backend messages can contain private data.
            error_type = type(exc).__name__
        trace_events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ] if trace_path.exists() else []

    return DemoRun(request, outcome, error_type, trace_events, scenario)


def threshold_explanation(event: dict[str, Any]) -> tuple[str, str]:
    """Return a plain-language branch description and its evidence category."""
    confidence = event.get("confidence")
    threshold = event.get("threshold")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return "The trace has no confidence value, so a threshold comparison is unavailable.", "Not available"
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return "The trace has no threshold value, so a threshold comparison is unavailable.", "Not available"
    if event.get("escalated") is True:
        return (
            f"Recorded confidence {confidence:.2f} is below threshold {threshold:.2f}; the engine escalated.",
            "Derived from recorded fields",
        )
    return (
        f"Recorded confidence {confidence:.2f} meets threshold {threshold:.2f}; the engine accepted the primary result.",
        "Derived from recorded fields",
    )


def workflow_tree_state(run: DemoRun) -> dict[str, Any]:
    """Map actual outcome/trace fields to the states drawn in the decision tree."""
    event = run.trace_events[-1] if run.trace_events else {}
    status = event.get("status")
    if status in {"error", "rejected"} or run.outcome is None:
        return {
            "stopped": True,
            "escalated": False,
            "primary_state": "error",
            "primary_choice": event.get("chosen"),
            "backend": event.get("backend"),
            "confidence": None,
            "threshold": None,
            "condition": "Not available in this trace",
            "primary_branch_state": "blocked",
            "fallback_branch_state": "blocked",
            "selected_route": None,
            "final_source": None,
            "action_state": "blocked",
            "trace_state": "recorded" if event else "not available",
            "error_category": event.get("error_category"),
        }

    escalated = event.get("escalated") is True
    confidence = event.get("confidence")
    threshold = event.get("threshold")
    available = (
        isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        and isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
    )
    condition = (
        f"{confidence:.2f} < {threshold:.2f}"
        if available and escalated
        else f"{confidence:.2f} ≥ {threshold:.2f}"
        if available
        else "Not available in this trace"
    )
    return {
        "stopped": False,
        "escalated": escalated,
        "primary_state": "completed",
        "primary_choice": event.get("chosen", run.outcome.primary_choice),
        "backend": event.get("backend", run.outcome.primary_backend),
        "confidence": confidence if available else None,
        "threshold": threshold if available else None,
        "condition": condition,
        "primary_branch_state": "unselected" if escalated else "selected",
        "fallback_branch_state": "selected" if escalated else "unselected",
        "selected_route": event.get("final_choice", run.outcome.selected),
        "final_source": event.get("final_source", run.outcome.final_source),
        "action_state": "completed",
        "trace_state": "recorded" if event else "not available",
        "error_category": None,
    }
