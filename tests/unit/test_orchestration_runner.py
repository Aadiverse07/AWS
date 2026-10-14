from pydantic import BaseModel, ConfigDict

from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.orchestrator.planner import Plan, PlanStep
from jarvis.orchestrator.runner import OrchestrationRunner, RunState
from jarvis.safety.guardrails import SafetyPolicy
from jarvis.tools.executor import ToolDefinition, ToolExecutor


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FakePlanner:
    def __init__(self, plan=None, error=None):
        self.plan = plan or Plan(
            plan=[PlanStep(step=1, description="Inspect the supplied task")]
        )
        self.error = error
        self.calls = 0

    def create_plan(self, task):
        self.calls += 1
        if self.error:
            raise self.error
        return self.plan


class FakeDecisionEngine:
    def __init__(
        self, choice="inspect", confidence=0.9, error=None,
        final_choice=None,
    ):
        self.choice = choice
        self.confidence = confidence
        self.error = error
        self.final_choice = final_choice
        self.calls = 0

    def decide(self, request: DecisionRequest) -> DecisionResult:
        self.calls += 1
        if self.error:
            raise self.error
        return DecisionResult(
            chosen=self.choice,
            scores={option: (1.0 if option == self.choice else 0.0)
                    for option in request.options},
            confidence=self.confidence,
            latency_ms=1.0,
            backend="fake",
            final_choice=(
                self.final_choice
                if self.final_choice is not None
                else self.choice
            ),
            final_source="fake",
        )


def build_runner(*, plan=None, planner_error=None, decision_error=None,
                 choice="inspect", final_choice=None, max_steps=5):
    calls = []
    executor = ToolExecutor(
        policy=SafetyPolicy(
            allowed_tools=frozenset({"inspect", "summarize"}),
            max_steps=5,
        ),
        tools={
            "inspect": ToolDefinition(
                NoArgs,
                lambda args: calls.append("inspect") or {"ok": True},
            ),
            "summarize": ToolDefinition(
                NoArgs,
                lambda args: calls.append("summarize") or {"ok": True},
            ),
        },
    )
    planner = FakePlanner(plan=plan, error=planner_error)
    engine = FakeDecisionEngine(
        choice=choice,
        final_choice=final_choice,
        error=decision_error,
    )
    runner = OrchestrationRunner(
        planner=planner,
        decision_engine=engine,
        executor=executor,
        tool_catalog={
            "inspect": "no-arguments",
            "summarize": "no-arguments",
        },
        max_steps=max_steps,
    )
    return runner, planner, engine, executor, calls


def test_runs_plan_through_decision_and_executor():
    runner, planner, engine, executor, calls = build_runner()

    result = runner.run("Review a harmless task", run_id="test-run")

    assert result.state is RunState.COMPLETED
    assert result.planned_steps == 1
    assert result.completed_steps == 1
    assert result.steps[0].tool_name == "inspect"
    assert calls == ["inspect"]
    assert planner.calls == 1
    assert engine.calls == 1
    assert "test-run" not in executor._active_runs


def test_stops_after_first_tool_failure_without_retry():
    calls = 0

    def fail(args):
        nonlocal calls
        calls += 1
        raise RuntimeError("PRIVATE_TOOL_ERROR")

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"inspect", "summarize"}), max_steps=5),
        tools={
            "inspect": ToolDefinition(NoArgs, fail),
            "summarize": ToolDefinition(NoArgs, lambda args: {"ok": True}),
        },
    )
    runner = OrchestrationRunner(
        planner=FakePlanner(
            Plan(plan=[
                PlanStep(step=1, description="First"),
                PlanStep(step=2, description="Second"),
            ])
        ),
        decision_engine=FakeDecisionEngine(),
        executor=executor,
        tool_catalog={
            "inspect": "no-arguments",
            "summarize": "no-arguments",
        },
    )

    result = runner.run("Test failure handling", run_id="fail-run")

    assert result.state is RunState.FAILED
    assert result.completed_steps == 0
    assert result.error_type == "RuntimeError"
    assert calls == 1
    assert len(result.steps) == 1
    assert "PRIVATE_TOOL_ERROR" not in str(result.model_dump())


def test_planner_failure_is_sanitized():
    runner, planner, engine, executor, calls = build_runner(
        planner_error=RuntimeError("PRIVATE_TASK_AND_TOKEN")
    )

    result = runner.run("Test planner failure")

    assert result.state is RunState.FAILED
    assert result.error_type == "RuntimeError"
    assert result.steps == ()
    assert "PRIVATE_TASK_AND_TOKEN" not in str(result.model_dump())
    assert engine.calls == 0
    assert calls == []


def test_decision_failure_stops_before_tool_execution():
    runner, planner, engine, executor, calls = build_runner(
        decision_error=RuntimeError("PRIVATE_CONTEXT")
    )

    result = runner.run("Test decision failure")

    assert result.state is RunState.FAILED
    assert result.error_type == "RuntimeError"
    assert result.completed_steps == 0
    assert calls == []
    assert "PRIVATE_CONTEXT" not in str(result.model_dump())


def test_unknown_selected_tool_is_blocked():
    runner, planner, engine, executor, calls = build_runner(
        choice="inspect",
        final_choice="not-registered",
    )

    result = runner.run("Test allowlist enforcement")

    assert result.state is RunState.BLOCKED
    assert result.completed_steps == 0
    assert calls == []


def test_plan_above_runner_limit_is_blocked_before_decision():
    plan = Plan(plan=[
        PlanStep(step=1, description="One"),
        PlanStep(step=2, description="Two"),
    ])
    runner, planner, engine, executor, calls = build_runner(plan=plan, max_steps=1)

    result = runner.run("Test step bound")

    assert result.state is RunState.BLOCKED
    assert result.error_type == "StepLimitExceeded"
    assert result.planned_steps == 2
    assert result.completed_steps == 0
    assert engine.calls == 0
    assert calls == []


def test_task_is_required_and_bounded():
    runner, planner, engine, executor, calls = build_runner()

    try:
        runner.run(" ")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "non-blank" in str(exc)

    try:
        runner.run("x" * 4001)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "4000" in str(exc)

    assert planner.calls == 0


def test_catalog_rejects_tool_not_registered_with_executor():
    from pytest import raises

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"inspect"})),
        tools={"inspect": ToolDefinition(NoArgs, lambda args: {"ok": True})},
    )

    with raises(ValueError, match="not registered"):
        OrchestrationRunner(
            planner=FakePlanner(),
            decision_engine=FakeDecisionEngine(),
            executor=executor,
            tool_catalog={
                "inspect": "no-arguments",
                "missing": "no-arguments",
            },
        )


def test_catalog_rejects_tool_outside_executor_allowlist():
    from pytest import raises

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"inspect"})),
        tools={
            "inspect": ToolDefinition(NoArgs, lambda args: {"ok": True}),
            "extra": ToolDefinition(NoArgs, lambda args: {"ok": True}),
        },
    )

    with raises(ValueError, match="outside the executor allowlist"):
        OrchestrationRunner(
            planner=FakePlanner(),
            decision_engine=FakeDecisionEngine(),
            executor=executor,
            tool_catalog={
                "inspect": "no-arguments",
                "extra": "no-arguments",
            },
        )


def test_write_tools_are_rejected_until_confirmation_is_supported():
    from pytest import raises

    executor = ToolExecutor(
        policy=SafetyPolicy(
            allowed_tools=frozenset({"inspect", "create_issue"}),
            write_tools=frozenset({"create_issue"}),
        ),
        tools={
            "inspect": ToolDefinition(NoArgs, lambda args: {"ok": True}),
            "create_issue": ToolDefinition(
                NoArgs, lambda args: {"created": True}
            ),
        },
    )

    with raises(ValueError, match="write tools are disabled"):
        OrchestrationRunner(
            planner=FakePlanner(),
            decision_engine=FakeDecisionEngine(),
            executor=executor,
            tool_catalog={
                "inspect": "no-arguments",
                "create_issue": "no-arguments",
            },
        )


def test_confirm_write_argument_is_not_silently_ignored():
    from pytest import raises

    runner, planner, engine, executor, calls = build_runner()

    with raises(ValueError, match="not supported yet"):
        OrchestrationRunner(
            planner=planner,
            decision_engine=engine,
            executor=executor,
            tool_catalog={
                "inspect": "no-arguments",
                "summarize": "no-arguments",
            },
            confirm_write=lambda tool, args: True,
        )


def test_explicit_blank_run_id_is_rejected():
    from pytest import raises

    runner, planner, engine, executor, calls = build_runner()
    with raises(ValueError, match="run_id must be a non-blank string"):
        runner.run("inspect this task", run_id="")

    assert planner.calls == 0
    assert calls == []


def test_omitted_run_id_is_generated():
    runner, planner, engine, executor, calls = build_runner()

    result = runner.run("inspect this task")

    assert result.run_id
    assert result.state.value == "completed"


def test_runner_with_tracing_engine_records_exactly_one_event_per_decision(tmp_path):
    import json

    from jarvis.decision.backends.mock import MockBackend
    from jarvis.decision.engine import DecisionEngine
    from jarvis.observability.trace import JSONLTraceRecorder
    from jarvis.observability.traced_engine import TracingDecisionEngine

    calls = []
    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"inspect", "summarize"})),
        tools={
            "inspect": ToolDefinition(
                NoArgs, lambda args: calls.append("inspect") or {"secret": "hidden"}
            ),
            "summarize": ToolDefinition(
                NoArgs, lambda args: calls.append("summarize") or {"ok": True}
            ),
        },
    )
    trace_path = tmp_path / "runner.jsonl"
    traced_engine = TracingDecisionEngine(
        DecisionEngine(MockBackend(), {"STEP_1": 0.0}),
        JSONLTraceRecorder(trace_path),
    )
    runner = OrchestrationRunner(
        planner=FakePlanner(),
        decision_engine=traced_engine,
        executor=executor,
        tool_catalog={
            "inspect": "no-arguments",
            "summarize": "no-arguments",
        },
    )

    result = runner.run(
        "PRIVATE_TASK_TEXT_DO_NOT_TRACE",
        run_id="trace-run",
    )

    assert result.state is RunState.COMPLETED
    assert len(calls) == 1
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 1
    assert events[0]["run_id"] == "trace-run"
    assert events[0]["decision_id"] == "STEP_1"
    trace_text = trace_path.read_text(encoding="utf-8")
    assert "PRIVATE_TASK_TEXT_DO_NOT_TRACE" not in trace_text
    assert "hidden" not in trace_text
    assert "context" not in trace_text


def test_cleanup_failure_is_reported_when_run_otherwise_succeeds():
    from pytest import raises

    runner, planner, engine, executor, calls = build_runner()

    def fail_cleanup(*, run_id):
        raise OSError("PRIVATE_CLEANUP_DETAIL")

    executor.finish_run = fail_cleanup

    with raises(RuntimeError, match="Run cleanup failed: OSError") as caught:
        runner.run("cleanup test", run_id="cleanup-run")

    assert "PRIVATE_CLEANUP_DETAIL" not in str(caught.value)


def test_cleanup_failure_does_not_mask_original_step_failure():
    runner, planner, engine, executor, calls = build_runner(
        decision_error=RuntimeError("PRIVATE_DECISION_FAILURE")
    )

    def fail_cleanup(*, run_id):
        raise OSError("PRIVATE_CLEANUP_DETAIL")

    executor.finish_run = fail_cleanup

    result = runner.run("cleanup error precedence", run_id="cleanup-error-run")

    assert result.state is RunState.FAILED
    assert result.error_type == "RuntimeError"
    assert "PRIVATE_DECISION_FAILURE" not in str(result.model_dump())
    assert "PRIVATE_CLEANUP_DETAIL" not in str(result.model_dump())


def test_cleanup_failure_does_not_mask_original_planner_failure():
    runner, planner, engine, executor, calls = build_runner(
        planner_error=RuntimeError("PRIVATE_PLANNER_FAILURE")
    )

    def fail_cleanup(*, run_id):
        raise OSError("PRIVATE_CLEANUP_DETAIL")

    executor.finish_run = fail_cleanup

    result = runner.run("planner and cleanup failure", run_id="planner-cleanup-run")

    assert result.state is RunState.FAILED
    assert result.error_type == "RuntimeError"
    assert "PRIVATE_PLANNER_FAILURE" not in str(result.model_dump())
    assert "PRIVATE_CLEANUP_DETAIL" not in str(result.model_dump())
