import pytest

from jarvis.safety.guardrails import (
    SafetyPolicy,
    SafetyViolation,
    authorize_tool_call,
)


@pytest.fixture
def policy():
    return SafetyPolicy(
        allowed_tools=frozenset({
            "get_repository",
            "list_issues",
            "create_issue",
        }),
        write_tools=frozenset({"create_issue"}),
        max_steps=5,
    )


def test_allows_allowlisted_read_tool(policy):
    assert authorize_tool_call(
        tool_name="list_issues", step=0, policy=policy
    ) is None


def test_rejects_non_allowlisted_tool(policy):
    with pytest.raises(SafetyViolation, match="not allowlisted"):
        authorize_tool_call(
            tool_name="reveal_secret", step=0, policy=policy
        )


def test_write_tool_requires_explicit_approval(policy):
    with pytest.raises(SafetyViolation, match="approval is required"):
        authorize_tool_call(
            tool_name="create_issue", step=0, policy=policy
        )


def test_approved_write_tool_is_allowed(policy):
    assert authorize_tool_call(
        tool_name="create_issue",
        step=0,
        policy=policy,
        approved=True,
    ) is None


def test_approval_does_not_allow_unknown_tool(policy):
    with pytest.raises(SafetyViolation, match="not allowlisted"):
        authorize_tool_call(
            tool_name="delete_everything",
            step=0,
            policy=policy,
            approved=True,
        )


def test_last_allowed_step_is_accepted(policy):
    assert authorize_tool_call(
        tool_name="list_issues", step=4, policy=policy
    ) is None


def test_step_limit_is_enforced(policy):
    with pytest.raises(SafetyViolation, match="Step limit exceeded"):
        authorize_tool_call(
            tool_name="list_issues", step=5, policy=policy
        )


@pytest.mark.parametrize("step", [-1, True, 1.5, "1"])
def test_invalid_steps_are_rejected(policy, step):
    with pytest.raises(SafetyViolation, match="non-negative integer"):
        authorize_tool_call(
            tool_name="list_issues", step=step, policy=policy
        )


@pytest.mark.parametrize("max_steps", [0, -1, True, 1.5])
def test_invalid_step_limits_are_rejected(max_steps):
    with pytest.raises(ValueError, match="positive integer"):
        SafetyPolicy(allowed_tools=frozenset({"list_issues"}),
                     max_steps=max_steps)


def test_write_tools_must_be_allowlisted():
    with pytest.raises(ValueError, match="subset"):
        SafetyPolicy(
            allowed_tools=frozenset({"list_issues"}),
            write_tools=frozenset({"create_issue"}),
        )


def test_policy_is_not_mutable_through_original_sets():
    allowed = {"list_issues"}
    policy = SafetyPolicy(allowed_tools=allowed)
    allowed.add("reveal_secret")

    assert "reveal_secret" not in policy.allowed_tools
