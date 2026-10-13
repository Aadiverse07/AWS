"""Conservative orchestration primitives; no tool execution."""

from __future__ import annotations

from enum import Enum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.orchestrator.planner import Plan


class RunStatus(str, Enum):
    PLANNED = "planned"
    BLOCKED = "blocked"


class RunResult(BaseModel):
    """A plan review result, not evidence that a task was executed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    task: str = Field(min_length=1)
    status: RunStatus
    steps: tuple[str, ...]
    blocked_reason: str | None = None


class DecisionEngineProtocol(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResult:
        ...


class ActionDecision(BaseModel):
    """A validated recommendation; it does not execute the selected action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    primary_choice: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    primary_backend: str = Field(min_length=1)
    final_source: str = Field(min_length=1)
    escalated: bool
    requires_review: bool = True


_BLOCKED_PHRASES = (
    "close the issue",
    "merge the pull request",
    "delete the repository",
    "delete the branch",
    "push to the repository",
    "publish the release",
    "send the email",
    "post the comment",
    "modify the repository",
)


def review_plan(
    task: str, plan: Plan, *, run_id: str | None = None
) -> RunResult:
    """Review a plan and return it for human inspection; never execute it."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("Task must not be empty")

    if not isinstance(plan, Plan):
        raise TypeError("plan must be a validated Plan")

    if run_id is None:
        run_id = str(uuid4())
    elif not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must not be blank")

    descriptions = tuple(step.description.strip() for step in plan.plan)

    for description in descriptions:
        lowered = description.casefold()
        if any(phrase in lowered for phrase in _BLOCKED_PHRASES):
            return RunResult(
                run_id=run_id,
                task=task.strip(),
                status=RunStatus.BLOCKED,
                steps=descriptions,
                blocked_reason=(
                    "Plan contains a potentially state-changing action. "
                    "Human review is required; no actions were executed."
                ),
            )

    return RunResult(
        run_id=run_id,
        task=task.strip(),
        status=RunStatus.PLANNED,
        steps=descriptions,
    )


def choose_next_action(
    *,
    engine: DecisionEngineProtocol,
    run_id: str,
    question: str,
    context: str,
    options: list[str],
    decision_id: str = "D1",
    step: int = 0,
) -> ActionDecision:
    """Choose among supplied options without executing the recommendation."""
    if not callable(getattr(engine, "decide", None)):
        raise TypeError("engine must provide a callable decide() method")

    request = DecisionRequest(
        decision_id=decision_id,
        question=question,
        context=context,
        options=options,
        run_id=run_id,
        step=step,
    )

    result: DecisionResult = engine.decide(request)
    selected = result.final_choice or result.chosen

    if selected not in request.options:
        raise ValueError("Decision engine selected an option not supplied")

    return ActionDecision(
        run_id=run_id,
        decision_id=decision_id,
        recommended_action=selected,
        primary_choice=result.chosen,
        confidence=result.confidence,
        primary_backend=result.backend,
        final_source=result.final_source or result.backend,
        escalated=result.escalated,
        requires_review=True,
    )
