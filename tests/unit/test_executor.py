from threading import Event, Thread
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from jarvis.safety.guardrails import SafetyPolicy, SafetyViolation
from jarvis.tools.approval import ApprovalAuthority
from jarvis.tools.executor import ToolDefinition, ToolExecutor


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str = Field(min_length=1)


class WriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)


@pytest.fixture
def setup_executor():
    calls: list[dict[str, Any]] = []

    def read_handler(args: BaseModel):
        calls.append({"tool": "read", "args": args.model_dump()})
        return {"ok": True}

    def write_handler(args: BaseModel):
        calls.append({"tool": "write", "args": args.model_dump()})
        return {"created": True}

    policy = SafetyPolicy(
        allowed_tools=frozenset({"read_repository", "create_issue"}),
        write_tools=frozenset({"create_issue"}),
        max_steps=3,
    )
    authority = ApprovalAuthority()
    executor = ToolExecutor(
        policy=policy,
        approval_authority=authority,
        tools={
            "read_repository": ToolDefinition(ReadArgs, read_handler),
            "create_issue": ToolDefinition(WriteArgs, write_handler),
        },
    )
    return executor, calls, authority


def test_valid_read_executes_once(setup_executor):
    executor, calls, authority = setup_executor

    result = executor.execute(
        run_id="run-1",
        tool_name="read_repository",
        arguments={"repository": "owner/project"},
    )

    assert result == {"ok": True}
    assert len(calls) == 1
    assert calls[0]["args"]["repository"] == "owner/project"


def test_unknown_tool_never_executes(setup_executor):
    executor, calls, authority = setup_executor

    with pytest.raises(SafetyViolation, match="not registered"):
        executor.execute(
            run_id="run-1",
            tool_name="reveal_secret",
            arguments={},
        )

    assert calls == []


def test_unapproved_write_never_executes(setup_executor):
    executor, calls, authority = setup_executor

    with pytest.raises(SafetyViolation, match="approval is required"):
        executor.execute(
            run_id="run-1",
            tool_name="create_issue",
            arguments={"title": "Test"},
        )

    assert calls == []


def test_approved_write_executes(setup_executor):
    executor, calls, authority = setup_executor

    arguments = {"title": "Approved issue"}
    grant = authority.issue_after_confirmation(
        run_id="run-1",
        tool_name="create_issue",
        arguments=WriteArgs.model_validate(arguments).model_dump(mode="json"),
    )
    result = executor.execute(
        run_id="run-1",
        tool_name="create_issue",
        arguments=arguments,
        approval=grant,
    )

    assert result == {"created": True}
    assert len(calls) == 1


def test_invalid_arguments_never_execute(setup_executor):
    executor, calls, authority = setup_executor

    with pytest.raises(SafetyViolation, match="Invalid arguments"):
        executor.execute(
            run_id="run-1",
            tool_name="read_repository",
            arguments={"repository": "", "unexpected": "value"},
        )

    assert calls == []


def test_model_cannot_bypass_step_limit(setup_executor):
    executor, calls, authority = setup_executor

    for index in range(3):
        executor.execute(
            run_id="same-run",
            tool_name="read_repository",
            arguments={"repository": f"owner/repo-{index}"},
        )

    # There is no caller-supplied step argument to reset.
    with pytest.raises(SafetyViolation, match="Step limit exceeded"):
        executor.execute(
            run_id="same-run",
            tool_name="read_repository",
            arguments={"repository": "owner/another"},
        )

    assert len(calls) == 3


def test_denied_attempts_consume_step_budget(setup_executor):
    executor, calls, authority = setup_executor

    for index in range(3):
        with pytest.raises(SafetyViolation, match="approval is required"):
            executor.execute(
                run_id="denied-run",
                tool_name="create_issue",
                arguments={"title": f"Issue {index}"},
            )

    with pytest.raises(SafetyViolation, match="Step limit exceeded"):
        executor.execute(
            run_id="denied-run",
            tool_name="read_repository",
            arguments={"repository": "owner/project"},
        )

    assert calls == []


def test_handler_error_propagates_without_retry():
    calls = 0

    def failing_handler(args: BaseModel):
        nonlocal calls
        calls += 1
        raise RuntimeError("fake tool failed")

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"read_repository"})),
        tools={
            "read_repository": ToolDefinition(ReadArgs, failing_handler),
        },
    )

    with pytest.raises(RuntimeError, match="fake tool failed"):
        executor.execute(
            run_id="error-run",
            tool_name="read_repository",
            arguments={"repository": "owner/project"},
        )

    assert calls == 1


def test_recursive_same_run_execution_is_rejected():
    holder: dict[str, ToolExecutor] = {}
    calls = 0

    def recursive_handler(args: BaseModel):
        nonlocal calls
        calls += 1
        return holder["executor"].execute(
            run_id="recursive-run",
            tool_name="read_repository",
            arguments={"repository": "owner/nested"},
        )

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"read_repository"})),
        tools={
            "read_repository": ToolDefinition(ReadArgs, recursive_handler),
        },
    )
    holder["executor"] = executor

    with pytest.raises(SafetyViolation, match="Recursive or concurrent"):
        executor.execute(
            run_id="recursive-run",
            tool_name="read_repository",
            arguments={"repository": "owner/root"},
        )

    assert calls == 1



def test_write_is_blocked_when_no_authority_is_configured():
    calls = 0

    def write_handler(args: BaseModel):
        nonlocal calls
        calls += 1
        return {"created": True}

    executor = ToolExecutor(
        policy=SafetyPolicy(
            allowed_tools=frozenset({"create_issue"}),
            write_tools=frozenset({"create_issue"}),
        ),
        tools={"create_issue": ToolDefinition(WriteArgs, write_handler)},
    )

    with pytest.raises(SafetyViolation, match="no trusted approval authority"):
        executor.execute(
            run_id="no-authority",
            tool_name="create_issue",
            arguments={"title": "Test"},
        )

    assert calls == 0


def test_grant_cannot_be_used_for_different_arguments(setup_executor):
    executor, calls, authority = setup_executor
    grant = authority.issue_after_confirmation(
        run_id="run-1",
        tool_name="create_issue",
        arguments=WriteArgs.model_validate(
            {"title": "Approved issue"}
        ).model_dump(mode="json"),
    )

    with pytest.raises(SafetyViolation, match="does not match"):
        executor.execute(
            run_id="run-1",
            tool_name="create_issue",
            arguments={"title": "Different issue"},
            approval=grant,
        )

    assert calls == []


def test_grant_cannot_be_used_for_another_run(setup_executor):
    executor, calls, authority = setup_executor
    grant = authority.issue_after_confirmation(
        run_id="run-1",
        tool_name="create_issue",
        arguments=WriteArgs.model_validate(
            {"title": "Approved issue"}
        ).model_dump(mode="json"),
    )

    with pytest.raises(SafetyViolation, match="does not match"):
        executor.execute(
            run_id="run-2",
            tool_name="create_issue",
            arguments={"title": "Approved issue"},
            approval=grant,
        )

    assert calls == []


def test_grant_cannot_be_reused(setup_executor):
    executor, calls, authority = setup_executor
    arguments = {"title": "Approved issue"}
    grant = authority.issue_after_confirmation(
        run_id="run-1",
        tool_name="create_issue",
        arguments=WriteArgs.model_validate(arguments).model_dump(mode="json"),
    )

    executor.execute(
        run_id="run-1",
        tool_name="create_issue",
        arguments=arguments,
        approval=grant,
    )

    with pytest.raises(SafetyViolation, match="invalid or already used"):
        executor.execute(
            run_id="run-1",
            tool_name="create_issue",
            arguments=arguments,
            approval=grant,
        )

    assert len(calls) == 1


def test_invalid_arguments_are_reported_as_safety_violations(setup_executor):
    executor, calls, _ = setup_executor

    with pytest.raises(SafetyViolation, match="Invalid arguments"):
        executor.execute(
            run_id="run-1",
            tool_name="read_repository",
            arguments={"repository": "", "unexpected": "value"},
        )

    assert calls == []


def test_finish_run_releases_step_budget_for_completed_run(setup_executor):
    executor, calls, _ = setup_executor

    executor.execute(
        run_id="completed-run",
        tool_name="read_repository",
        arguments={"repository": "owner/project"},
    )
    assert "completed-run" in executor._steps_by_run

    executor.finish_run(run_id="completed-run")
    assert "completed-run" not in executor._steps_by_run

    # The same ID is usable again only after trusted lifecycle completion.
    executor.execute(
        run_id="completed-run",
        tool_name="read_repository",
        arguments={"repository": "owner/project"},
    )
    assert len(calls) == 2


def test_finish_run_rejects_active_run():
    holder = {}

    def handler(args: BaseModel):
        with pytest.raises(SafetyViolation, match="active run"):
            holder["executor"].finish_run(run_id="active-run")
        return {"ok": True}

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"read_repository"})),
        tools={"read_repository": ToolDefinition(ReadArgs, handler)},
    )
    holder["executor"] = executor

    executor.execute(
        run_id="active-run",
        tool_name="read_repository",
        arguments={"repository": "owner/project"},
    )
    assert "active-run" in executor._steps_by_run

def test_concurrent_execution_for_same_run_is_rejected():
    handler_entered = Event()
    release_handler = Event()
    handler_calls = 0
    thread_errors = []

    def blocking_handler(args: BaseModel):
        nonlocal handler_calls
        handler_calls += 1
        handler_entered.set()
        if not release_handler.wait(timeout=5):
            raise TimeoutError("Test did not release the blocked handler")
        return {"ok": True}

    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"read_repository"})),
        tools={
            "read_repository": ToolDefinition(ReadArgs, blocking_handler),
        },
    )

    def first_call():
        try:
            executor.execute(
                run_id="shared-run",
                tool_name="read_repository",
                arguments={"repository": "owner/first"},
            )
        except Exception as exc:
            thread_errors.append(exc)

    thread = Thread(target=first_call)
    thread.start()
    try:
        assert handler_entered.wait(timeout=5), "First handler did not start"
        with pytest.raises(SafetyViolation, match="Recursive or concurrent"):
            executor.execute(
                run_id="shared-run",
                tool_name="read_repository",
                arguments={"repository": "owner/second"},
            )
    finally:
        release_handler.set()
        thread.join(timeout=5)

    assert not thread.is_alive(), "Worker thread did not finish"
    assert thread_errors == []
    assert handler_calls == 1



def test_confirmation_approves_write_and_executes_once(setup_executor):
    executor, calls, authority = setup_executor
    previews = []

    def confirm(tool_name, arguments):
        previews.append((tool_name, arguments.copy()))
        return True

    result = executor.execute_with_confirmation(
        run_id="confirm-approve",
        tool_name="create_issue",
        arguments={"title": "Approved through confirmation"},
        confirm=confirm,
    )

    assert result == {"created": True}
    assert len(calls) == 1
    assert calls[0]["args"]["title"] == "Approved through confirmation"
    assert previews == [
        ("create_issue", {"title": "Approved through confirmation"})
    ]


@pytest.mark.parametrize("confirmation_result", [False, None, 1, "yes"])
def test_confirmation_requires_literal_true(
    setup_executor, confirmation_result
):
    executor, calls, authority = setup_executor

    with pytest.raises(SafetyViolation, match="not explicitly approved"):
        executor.execute_with_confirmation(
            run_id="confirm-refuse",
            tool_name="create_issue",
            arguments={"title": "Must not execute"},
            confirm=lambda tool, args: confirmation_result,
        )

    assert calls == []


def test_confirmation_callback_exception_blocks_write(setup_executor):
    executor, calls, authority = setup_executor

    def broken_confirmation(tool_name, arguments):
        raise RuntimeError("confirmation UI failed")

    with pytest.raises(SafetyViolation, match="Confirmation failed"):
        executor.execute_with_confirmation(
            run_id="confirm-error",
            tool_name="create_issue",
            arguments={"title": "Must not execute"},
            confirm=broken_confirmation,
        )

    assert calls == []


def test_confirmation_preview_mutation_does_not_change_executed_arguments(
    setup_executor,
):
    executor, calls, authority = setup_executor

    def mutate_preview(tool_name, preview):
        preview["title"] = "Tampered preview"
        preview["extra"] = "unexpected"
        return True

    result = executor.execute_with_confirmation(
        run_id="confirm-mutation",
        tool_name="create_issue",
        arguments={"title": "Original validated title"},
        confirm=mutate_preview,
    )

    assert result == {"created": True}
    assert len(calls) == 1
    assert calls[0]["args"] == {"title": "Original validated title"}


def test_confirmation_rejects_invalid_arguments_before_prompt(setup_executor):
    executor, calls, authority = setup_executor
    prompts = []

    with pytest.raises(SafetyViolation, match="Invalid arguments"):
        executor.execute_with_confirmation(
            run_id="confirm-invalid",
            tool_name="create_issue",
            arguments={"title": "", "unexpected": "value"},
            confirm=lambda tool, args: prompts.append(args) or True,
        )

    assert prompts == []
    assert calls == []


def test_confirmation_requires_authority_before_prompt():
    prompts = []
    calls = 0

    def write_handler(args: BaseModel):
        nonlocal calls
        calls += 1
        return {"created": True}

    executor = ToolExecutor(
        policy=SafetyPolicy(
            allowed_tools=frozenset({"create_issue"}),
            write_tools=frozenset({"create_issue"}),
        ),
        tools={"create_issue": ToolDefinition(WriteArgs, write_handler)},
    )

    with pytest.raises(SafetyViolation, match="no trusted approval authority"):
        executor.execute_with_confirmation(
            run_id="confirm-no-authority",
            tool_name="create_issue",
            arguments={"title": "Must not execute"},
            confirm=lambda tool, args: prompts.append(args) or True,
        )

    assert prompts == []
    assert calls == 0


def test_confirmation_for_read_tool_does_not_require_approval(setup_executor):
    executor, calls, authority = setup_executor
    prompts = []

    result = executor.execute_with_confirmation(
        run_id="confirm-read",
        tool_name="read_repository",
        arguments={"repository": "owner/project"},
        confirm=lambda tool, args: prompts.append((tool, args)) or True,
    )

    assert result == {"ok": True}
    assert calls == [
        {"tool": "read", "args": {"repository": "owner/project"}}
    ]
    assert prompts == []


def test_repeated_confirmation_refusals_consume_step_budget(setup_executor):
    executor, calls, authority = setup_executor
    prompts = 0

    def refuse(tool_name, arguments):
        nonlocal prompts
        prompts += 1
        return False

    for _ in range(3):
        with pytest.raises(SafetyViolation, match="not explicitly approved"):
            executor.execute_with_confirmation(
                run_id="confirmation-budget",
                tool_name="create_issue",
                arguments={"title": "Not approved"},
                confirm=refuse,
            )

    # The configured limit is three attempts for this run.
    with pytest.raises(SafetyViolation, match="Step limit exceeded"):
        executor.execute_with_confirmation(
            run_id="confirmation-budget",
            tool_name="create_issue",
            arguments={"title": "Fourth attempt"},
            confirm=refuse,
        )

    assert prompts == 3
    assert calls == []


def test_confirmed_write_consumes_exactly_one_step(setup_executor):
    executor, calls, authority = setup_executor

    for index in range(3):
        result = executor.execute_with_confirmation(
            run_id="confirmed-write-budget",
            tool_name="create_issue",
            arguments={"title": f"Approved issue {index}"},
            confirm=lambda tool, args: True,
        )
        assert result == {"created": True}

    assert len(calls) == 3

    with pytest.raises(SafetyViolation, match="Step limit exceeded"):
        executor.execute_with_confirmation(
            run_id="confirmed-write-budget",
            tool_name="create_issue",
            arguments={"title": "Fourth issue"},
            confirm=lambda tool, args: True,
        )

    assert len(calls) == 3


def test_pending_confirmation_blocks_same_run_and_finish_run(setup_executor):
    executor, calls, authority = setup_executor
    confirmation_entered = Event()
    release_confirmation = Event()
    thread_errors = []

    def blocking_confirmation(tool_name, arguments):
        confirmation_entered.set()
        if not release_confirmation.wait(timeout=5):
            raise TimeoutError("Test did not release confirmation")
        return True

    def confirmed_write():
        try:
            executor.execute_with_confirmation(
                run_id="pending-run",
                tool_name="create_issue",
                arguments={"title": "Approved issue"},
                confirm=blocking_confirmation,
            )
        except Exception as exc:
            thread_errors.append(exc)

    thread = Thread(target=confirmed_write)
    thread.start()

    try:
        assert confirmation_entered.wait(timeout=5), (
            "Confirmation callback did not start"
        )

        with pytest.raises(SafetyViolation, match="awaiting confirmation"):
            executor.execute(
                run_id="pending-run",
                tool_name="read_repository",
                arguments={"repository": "owner/project"},
            )

        with pytest.raises(SafetyViolation, match="awaiting confirmation"):
            executor.finish_run(run_id="pending-run")

        assert calls == []
    finally:
        release_confirmation.set()
        thread.join(timeout=5)

    assert not thread.is_alive(), "Confirmation worker did not finish"
    assert thread_errors == []
    assert len(calls) == 1
    assert calls[0]["tool"] == "write"

