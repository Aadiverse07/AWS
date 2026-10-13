import pytest

from jarvis.orchestrator.controller import RunStatus, review_plan
from jarvis.orchestrator.planner import Plan, PlanStep


def make_plan(*descriptions: str) -> Plan:
    return Plan(
        plan=[
            PlanStep(step=index, description=description)
            for index, description in enumerate(descriptions, start=1)
        ]
    )


def test_review_returns_plan_without_claiming_execution():
    result = review_plan(
        "Review a public issue",
        make_plan("Read the issue", "Summarize the issue"),
        run_id="test-run",
    )

    assert result.status is RunStatus.PLANNED
    assert result.run_id == "test-run"
    assert result.steps == ("Read the issue", "Summarize the issue")
    assert result.blocked_reason is None


def test_review_blocks_obvious_state_changing_step():
    result = review_plan(
        "Review a public issue",
        make_plan("Read the issue", "Close the issue"),
    )

    assert result.status is RunStatus.BLOCKED
    assert result.blocked_reason is not None


def test_review_rejects_empty_task():
    with pytest.raises(ValueError, match="Task must not be empty"):
        review_plan(" ", make_plan("Read the issue"))


def test_review_rejects_unvalidated_plan_type():
    with pytest.raises(TypeError, match="validated Plan"):
        review_plan("Review an issue", {"plan": []})  # type: ignore[arg-type]


def test_review_rejects_blank_run_id():
    with pytest.raises(ValueError, match="run_id"):
        review_plan("Review an issue", make_plan("Read the issue"), run_id=" ")
