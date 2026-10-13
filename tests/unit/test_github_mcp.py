import pytest
from pydantic import ValidationError

from jarvis.integrations.github_mcp import (
    GitHubMCPConfig,
    ListBranchesArgs,
    register_github_read_tools,
)
from jarvis.safety.guardrails import SafetyPolicy, SafetyViolation
from jarvis.tools.executor import ToolExecutor


def _wait_for_process_exit(pid_file, timeout=3.0):
    """Wait until a fixture process is no longer running."""
    import os
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pid = int(pid_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            time.sleep(0.02)
            continue

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass

        time.sleep(0.02)

    return False


def test_config_rejects_blank_required_values():
    with pytest.raises(ValueError, match="command"):
        GitHubMCPConfig(command=" ", owner="owner", repository="repo")
    with pytest.raises(ValueError, match="owner"):
        GitHubMCPConfig(owner=" ", repository="repo")
    with pytest.raises(ValueError, match="repository"):
        GitHubMCPConfig(owner="owner", repository=" ")


def test_config_rejects_invalid_timeouts():
    with pytest.raises(ValueError, match="startup_timeout_seconds"):
        GitHubMCPConfig(
            owner="owner",
            repository="repo",
            startup_timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="call_timeout_seconds"):
        GitHubMCPConfig(
            owner="owner",
            repository="repo",
            call_timeout_seconds=True,
        )


def test_branch_arguments_are_validated_and_reject_extras():
    args = ListBranchesArgs(owner="octocat", repo="hello-world")
    assert args.owner == "octocat"
    assert args.repo == "hello-world"

    with pytest.raises(ValidationError):
        ListBranchesArgs(owner="", repo="hello-world")

    with pytest.raises(ValidationError):
        ListBranchesArgs(
            owner="octocat",
            repo="hello-world",
            token="not-allowed",
        )


def test_register_github_tool_only_when_allowlisted():
    client = type("FakeClient", (), {"list_branches": lambda self, args: []})()
    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"list_branches"})),
        tools={},
    )

    register_github_read_tools(executor=executor, client=client)

    result = executor.execute(
        run_id="github-test",
        tool_name="list_branches",
        arguments={"owner": "octocat", "repo": "hello-world"},
    )
    assert result == []


def test_registration_rejects_tool_not_in_policy():
    client = type("FakeClient", (), {"list_branches": lambda self, args: []})()
    executor = ToolExecutor(policy=SafetyPolicy(frozenset()), tools={})

    with pytest.raises(SafetyViolation, match="not allowlisted"):
        register_github_read_tools(executor=executor, client=client)


def test_registration_rejects_duplicate_tool():
    client = type("FakeClient", (), {"list_branches": lambda self, args: []})()
    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"list_branches"})),
        tools={},
    )
    register_github_read_tools(executor=executor, client=client)

    with pytest.raises(SafetyViolation, match="already registered"):
        register_github_read_tools(executor=executor, client=client)


def test_client_rejects_repository_outside_configured_scope():
    from jarvis.integrations.github_mcp import GitHubMCPClient

    client = GitHubMCPClient(
        GitHubMCPConfig(owner="octocat", repository="hello-world")
    )

    with pytest.raises(SafetyViolation, match="restricted"):
        client.list_branches(
            ListBranchesArgs(owner="another-owner", repo="another-repo")
        )


def test_client_rejects_wrong_repo_even_when_owner_matches():
    from jarvis.integrations.github_mcp import GitHubMCPClient

    client = GitHubMCPClient(
        GitHubMCPConfig(owner="octocat", repository="hello-world")
    )

    with pytest.raises(SafetyViolation, match="restricted"):
        client.list_branches(
            ListBranchesArgs(owner="octocat", repo="different-repo")
        )


def test_end_to_end_read_only_mcp_call_with_local_fake_server():
    import sys
    from pathlib import Path

    from jarvis.integrations.github_mcp import GitHubMCPClient

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "fake_github_mcp_server.py"
    )
    assert fixture.is_file()

    config = GitHubMCPConfig(
        command=sys.executable,
        command_args=(str(fixture),),
        owner="octocat",
        repository="hello-world",
        startup_timeout_seconds=10,
        call_timeout_seconds=10,
    )
    client = GitHubMCPClient(config)
    executor = ToolExecutor(
        policy=SafetyPolicy(frozenset({"list_branches"})),
        tools={},
    )
    register_github_read_tools(executor=executor, client=client)

    try:
        client.start()
        result = executor.execute(
            run_id="fake-mcp-e2e",
            tool_name="list_branches",
            arguments={"owner": "octocat", "repo": "hello-world"},
        )
        assert result == {
            "branches": [
                {
                    "name": "main",
                    "sha": "abc123",
                    "protected": True,
                }
            ]
        }
    finally:
        client.close()

    with pytest.raises(RuntimeError, match="closed"):
        client.list_branches(
            ListBranchesArgs(owner="octocat", repo="hello-world")
        )


def test_startup_timeout_does_not_leave_client_thread_running(tmp_path):
    import sys
    import time
    from pathlib import Path

    from jarvis.integrations.github_mcp import GitHubMCPClient

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "fake_github_mcp_server.py"
    )
    pid_file = tmp_path / "startup-server.pid"
    client = GitHubMCPClient(
        GitHubMCPConfig(
            command=sys.executable,
            command_args=(
                str(fixture),
                "--test-mode=hang-init",
                f"--pid-file={pid_file}",
            ),
            owner="octocat",
            repository="hello-world",
            startup_timeout_seconds=0.3,
            call_timeout_seconds=0.5,
        )
    )

    with pytest.raises(TimeoutError, match="starting"):
        client.start()

    thread = client._thread
    deadline = time.monotonic() + 2
    while thread is not None and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert thread is None or not thread.is_alive()
    assert pid_file.exists(), "fake server did not report its PID"
    assert _wait_for_process_exit(pid_file), (
        "fake MCP server process remained alive after startup timeout"
    )


def test_tool_call_timeout_closes_stuck_client(tmp_path):
    import sys
    import time
    from pathlib import Path

    from jarvis.integrations.github_mcp import GitHubMCPClient

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "fake_github_mcp_server.py"
    )
    pid_file = tmp_path / "call-server.pid"
    client = GitHubMCPClient(
        GitHubMCPConfig(
            command=sys.executable,
            command_args=(
                str(fixture),
                "--test-mode=hang-call",
                f"--pid-file={pid_file}",
            ),
            owner="octocat",
            repository="hello-world",
            startup_timeout_seconds=2,
            call_timeout_seconds=0.3,
        )
    )

    client.start()
    with pytest.raises(TimeoutError, match="timed out"):
        client.list_branches(
            ListBranchesArgs(owner="octocat", repo="hello-world")
        )

    # A timed-out client should reject later calls without manual cleanup.
    with pytest.raises(RuntimeError, match="closed"):
        client.list_branches(
            ListBranchesArgs(owner="octocat", repo="hello-world")
        )

    thread = client._thread
    deadline = time.monotonic() + 2
    while thread is not None and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert thread is None or not thread.is_alive()
    assert pid_file.exists(), "fake server did not report its PID"
    assert _wait_for_process_exit(pid_file), (
        "fake MCP server process remained alive after tool-call timeout"
    )
    client.close()


def test_close_during_startup_stops_client_thread():
    import sys
    import threading
    import time
    from pathlib import Path

    from jarvis.integrations.github_mcp import GitHubMCPClient

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "fake_github_mcp_server.py"
    )
    client = GitHubMCPClient(
        GitHubMCPConfig(
            command=sys.executable,
            command_args=(str(fixture), "--test-mode=hang-init"),
            owner="octocat",
            repository="hello-world",
            startup_timeout_seconds=5,
            call_timeout_seconds=0.5,
        )
    )

    start_errors = []

    def start_client():
        try:
            client.start()
        except (RuntimeError, TimeoutError) as exc:
            start_errors.append(exc)

    starter = threading.Thread(target=start_client, daemon=True)
    starter.start()

    deadline = time.monotonic() + 2
    while client._thread is None and time.monotonic() < deadline:
        time.sleep(0.01)

    assert client._thread is not None, "client startup thread was not created"
    client.close()

    starter.join(timeout=2)
    thread = client._thread
    assert thread is None or not thread.is_alive(), (
        "client thread remained alive after close during startup"
    )
    assert not starter.is_alive(), "start() did not return after close"
