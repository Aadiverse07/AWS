"""Local decision-to-action workflow and explicit backend construction."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from jarvis.config import AppConfig, ConfigurationError, load_config
from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.backends.mock import MockBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import DecisionEngine


ROUTING_DESTINATIONS = ("research", "developer", "documentation")


class WorkflowError(RuntimeError):
    """A safe, user-presentable workflow failure."""


class ActionOutcome(BaseModel):
    """Result from the local-only task-routing demonstration action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = "task_routing"
    destination: str
    status: str = "routed"


class WorkflowOutcome(BaseModel):
    """Decision and action result for one request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    selected: str
    primary_choice: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    primary_backend: str
    final_source: str
    escalated: bool
    action: ActionOutcome


class TaskRoutingAction:
    """Return a local routing outcome for one allowlisted destination."""

    allowed_destinations = frozenset(ROUTING_DESTINATIONS)

    def execute(self, destination: str) -> ActionOutcome:
        if not isinstance(destination, str) or destination not in self.allowed_destinations:
            raise ValueError("destination is not an allowed routing destination")
        return ActionOutcome(destination=destination)


def build_backend(name: str, config: AppConfig) -> DecisionBackend:
    """Resolve exactly one named backend, enforcing paid-use configuration."""
    if name not in {"mock", "local_hf", "bedrock"}:
        raise ConfigurationError(
            f"Unknown backend {name!r}; choose mock, local_hf, or bedrock."
        )
    if name == "bedrock" and not (
        config.cost_mode == "production" and config.allow_paid
    ):
        raise ConfigurationError(
            "The Bedrock backend requires COST_MODE=production and ALLOW_PAID=true."
        )
    if name == "mock":
        return MockBackend()
    if name == "local_hf":
        from jarvis.decision.backends.local_hf import LocalHFBackend

        return LocalHFBackend()
    from jarvis.decision.backends.bedrock import BedrockBackend

    return BedrockBackend()


def run_workflow(
    request: DecisionRequest,
    engine: DecisionEngine,
    *,
    action: TaskRoutingAction | None = None,
) -> WorkflowOutcome:
    """Validate, decide, and perform exactly one safe local routing action."""
    if not isinstance(request, DecisionRequest):
        raise TypeError("request must be a validated DecisionRequest")
    if not set(request.options).issubset(TaskRoutingAction.allowed_destinations):
        raise ValueError("request options must use the routing destination allowlist")
    if not callable(getattr(engine, "decide", None)):
        raise TypeError("engine must provide a callable decide() method")

    result: DecisionResult = engine.decide(request)
    if not isinstance(result, DecisionResult):
        raise WorkflowError("Decision engine returned an invalid result")
    selected = result.final_choice or result.chosen
    if selected not in request.options:
        raise WorkflowError("Decision selected an option not supplied in the request")

    action_result = (action or TaskRoutingAction()).execute(selected)
    return WorkflowOutcome(
        decision_id=request.decision_id,
        selected=selected,
        primary_choice=result.chosen,
        confidence=result.confidence,
        primary_backend=result.backend,
        final_source=result.final_source or result.backend,
        escalated=result.escalated,
        action=action_result,
    )


def run_default_demo(backend_name: str = "mock") -> WorkflowOutcome:
    """Run the documented local task-routing request using app configuration."""
    config = load_config()
    backend = build_backend(backend_name, config)
    # The mock fallback is local and deterministic. It is used for unknown
    # confidence from backends such as Bedrock, never on the default mock path.
    fallback = MockBackend() if backend_name != "mock" else None
    engine = DecisionEngine(backend, {"D1": 0.60}, fallback=fallback)
    request = DecisionRequest(
        decision_id="D1",
        question="Choose the best destination for this task.",
        context="Demonstration request; route only, do not execute task content.",
        options=list(ROUTING_DESTINATIONS),
        run_id=uuid4().hex,
        step=0,
    )
    return run_workflow(request, engine)
