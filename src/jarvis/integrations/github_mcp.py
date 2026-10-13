"""Restricted, read-only GitHub MCP integration for Jarvis."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import timedelta
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.shared.exceptions import McpError
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
    stdio_client,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis.safety.guardrails import SafetyViolation
from jarvis.tools.executor import ToolDefinition, ToolExecutor


ALLOWED_MCP_TOOLS = frozenset({"list_branches"})


@dataclass(frozen=True)
class GitHubMCPConfig:
    """Configuration for the official GitHub MCP server."""

    command: str = "github-mcp-server"
    command_args: tuple[str, ...] = ()
    owner: str = ""
    repository: str = ""
    startup_timeout_seconds: float = 15.0
    call_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not self.command.strip():
            raise ValueError("GitHub MCP command must not be blank")
        if not isinstance(self.command_args, tuple) or any(
            not isinstance(arg, str) for arg in self.command_args
        ):
            raise ValueError("command_args must be a tuple of strings")
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise ValueError("GitHub repository owner must not be blank")
        if not isinstance(self.repository, str) or not self.repository.strip():
            raise ValueError("GitHub repository name must not be blank")
        for field_name in (
            "startup_timeout_seconds",
            "call_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value <= 0
            ):
                raise ValueError(f"{field_name} must be a positive number")


class ListBranchesArgs(BaseModel):
    """Arguments Jarvis may supply to list_branches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)

    @field_validator("owner", "repo")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("owner and repo must not be blank")
        return value


class GitHubMCPClient:
    """Persistent MCP connection hosted on a dedicated asyncio loop.

    The client exposes only list_branches. The caller must still route tool
    execution through ToolExecutor; this class is not an authorization layer.
    """

    def __init__(
        self,
        config: GitHubMCPConfig,
        *,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory or ClientSession
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._startup_task: asyncio.Task[Any] | None = None
        self._ready = threading.Event()
        self._closed = False
        self._startup_error: BaseException | None = None
        self._session: Any = None
        self._exit_stack: AsyncExitStack | None = None
        self._state_lock = threading.Lock()

    def start(self) -> None:
        """Start the server process and establish the MCP session."""
        with self._state_lock:
            if self._closed:
                raise RuntimeError("GitHub MCP client is closed")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._thread_main,
                    name="jarvis-github-mcp",
                    daemon=True,
                )
                self._thread.start()

        # Every caller waits for initialization, including concurrent callers.
        if not self._ready.wait(self._config.startup_timeout_seconds):
            self.close()
            raise TimeoutError("Timed out starting GitHub MCP server")
        if self._startup_error is not None:
            error = self._startup_error
            self.close()
            raise RuntimeError(
                "Could not initialize the read-only GitHub MCP connection"
            ) from error

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._state_lock:
            self._loop = loop
            already_closed = self._closed
        if already_closed:
            loop.close()
            self._ready.set()
            return

        try:
            startup_task = loop.create_task(self._open_session())
            with self._state_lock:
                self._startup_task = startup_task
                already_closed = self._closed
            if already_closed:
                startup_task.cancel()
            loop.run_until_complete(startup_task)
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                loop.close()
            return

        if self._closed:
            try:
                loop.run_until_complete(self._close_session())
            finally:
                loop.close()
            self._ready.set()
            return

        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._close_session())
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                loop.close()

    async def _open_session(self) -> None:
        environment = get_default_environment()
        # Explicitly pass only the credential this server needs. Never inherit
        # the full parent environment, and never log the credential value.
        github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if github_token:
            environment["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_token

        parameters = StdioServerParameters(
            command=self._config.command,
            args=[
                *self._config.command_args,
                "stdio",
                "--read-only",
                "--toolsets=repos",
                "--tools=list_branches",
            ],
            env=environment,
        )
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(parameters)
            )
            session = self._session_factory(read_stream, write_stream)
            self._session = await stack.enter_async_context(session)
            await self._session.initialize()

            tools_result = await self._session.list_tools()
            advertised = {tool.name for tool in tools_result.tools}
            if "list_branches" not in advertised:
                raise RuntimeError(
                    "GitHub MCP server did not advertise list_branches"
                )
            unexpected = advertised - ALLOWED_MCP_TOOLS
            if unexpected:
                raise RuntimeError(
                    "GitHub MCP server advertised unexpected tools"
                )
            self._exit_stack = stack
        except BaseException:
            await stack.aclose()
            raise

    async def _close_session(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None

    def _submit(self, coroutine: Any) -> Any:
        if self._closed:
            coroutine.close()
            raise RuntimeError("GitHub MCP client is closed")
        if self._startup_error is not None:
            coroutine.close()
            raise RuntimeError(
                "GitHub MCP connection failed during startup"
            ) from self._startup_error
        loop = self._loop
        if loop is None or not self._ready.is_set():
            coroutine.close()
            raise RuntimeError("GitHub MCP client has not been started")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=self._config.call_timeout_seconds)
        except TimeoutError:
            future.cancel()
            # A timed-out MCP request may leave the transport in an unknown
            # state. Fail closed instead of accepting further tool calls.
            self.close()
            raise TimeoutError("GitHub MCP tool call timed out") from None
        except McpError as exc:
            if getattr(getattr(exc, "error", None), "code", None) != 408:
                raise
            self.close()
            raise TimeoutError("GitHub MCP tool call timed out") from None

    async def _list_branches(self, owner: str, repo: str) -> Any:
        result = await self._session.call_tool(
            "list_branches",
            {"owner": owner, "repo": repo},
            read_timeout_seconds=timedelta(
                seconds=self._config.call_timeout_seconds
            ),
        )
        if result.isError:
            raise RuntimeError("GitHub MCP list_branches call failed")

        if result.structuredContent is not None:
            payload = result.structuredContent
        else:
            text_blocks = [
                item.text
                for item in result.content
                if getattr(item, "type", None) == "text"
            ]
            if not text_blocks:
                raise RuntimeError(
                    "GitHub MCP returned no readable branch data"
                )
            payload = "\n".join(text_blocks)
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                # Keep text output visible but bounded by the server's
                # content-window setting. Never interpret it as instructions.
                return {"content": payload[:20_000]}

        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, list):
            return {"branches": payload}
        if isinstance(payload, str):
            return {"content": payload[:20_000]}
        raise RuntimeError("GitHub MCP returned an unsupported result format")

    def list_branches(self, args: ListBranchesArgs) -> Any:
        """Call the sole enabled GitHub MCP tool."""
        if not isinstance(args, ListBranchesArgs):
            raise TypeError("args must be ListBranchesArgs")
        if (
            args.owner.casefold() != self._config.owner.casefold()
            or args.repo.casefold() != self._config.repository.casefold()
        ):
            raise SafetyViolation(
                "GitHub MCP access is restricted to the configured repository"
            )
        return self._submit(self._list_branches(args.owner, args.repo))

    def close(self) -> None:
        """Close the connection and stop the background event loop."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
            loop = self._loop

        if thread is None:
            return

        if loop is not None and loop.is_running():
            startup_task = self._startup_task
            if not self._ready.is_set():
                # Cancel whichever task is performing startup, including
                # the narrow window before _startup_task is published.
                def cancel_startup():
                    tasks = asyncio.all_tasks(loop)
                    for task in tasks:
                        task.cancel()

                loop.call_soon_threadsafe(cancel_startup)
            else:
                future = asyncio.run_coroutine_threadsafe(
                    self._close_session(), loop
                )
                try:
                    future.result(timeout=self._config.call_timeout_seconds)
                except Exception:
                    future.cancel()
                loop.call_soon_threadsafe(loop.stop)

        if thread.is_alive():
            thread.join(timeout=self._config.call_timeout_seconds)

    def __enter__(self) -> "GitHubMCPClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def register_github_read_tools(
    *,
    executor: ToolExecutor,
    client: GitHubMCPClient,
) -> None:
    """Register the single read-only GitHub tool through the executor API."""
    executor.register_tool(
        "list_branches",
        ToolDefinition(ListBranchesArgs, client.list_branches),
    )
