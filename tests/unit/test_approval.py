import pytest

from jarvis.safety.guardrails import SafetyViolation
from jarvis.tools.approval import ApprovalAuthority, ApprovalGrant


def issue(authority, run_id="run-1", title="Test"):
    return authority.issue_after_confirmation(
        run_id=run_id,
        tool_name="create_issue",
        arguments={"title": title},
    )


def test_pending_grants_are_bounded_without_evicting_existing_grants():
    authority = ApprovalAuthority(max_pending_grants=1)
    first = issue(authority)

    with pytest.raises(SafetyViolation, match="limit reached"):
        issue(authority, run_id="run-2")

    # The existing valid grant remains usable after the rejected issue.
    authority.consume(
        first,
        run_id="run-1",
        tool_name="create_issue",
        arguments={"title": "Test"},
    )


def test_consuming_grant_frees_capacity():
    authority = ApprovalAuthority(max_pending_grants=1)
    first = issue(authority)

    authority.consume(
        first,
        run_id="run-1",
        tool_name="create_issue",
        arguments={"title": "Test"},
    )

    second = issue(authority, run_id="run-2")
    assert isinstance(second, ApprovalGrant)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2", None])
def test_invalid_pending_grant_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="positive integer"):
        ApprovalAuthority(max_pending_grants=limit)
