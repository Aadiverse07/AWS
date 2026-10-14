"""A bounded execution boundary for registered tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from pydantic import BaseModel, ValidationError

from jarvis.safety.guardrails import (
    SafetyPolicy,
    SafetyViolation,
    authorize_tool_call,
)
from jarvis.tools.approval import ApprovalAuthority, ApprovalGrant


@dataclass(frozen=True)
class ToolDefinition:
    """A tool's validated argument schema and callable handler."""

    args_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]

    def __post_init__(self) -> None:
        if not isinstance(self.args_model, type) or not issubclass(
            self.args_model, BaseModel
        ):
            raise TypeError("args_model must be a Pydantic BaseModel class")
        if not callable(self.handler):
            raise TypeError("handler must be callable")


class ToolExecutor:
    """Execute registered tools only after validation and authorization.

    Step counts are maintained internally per run_id. A model cannot choose or
    reset the step number. Same-run nested/concurrent execution is rejected.
    There are no automatic retries. Only a trusted controller should hold the
    ApprovalAuthority used to issue write grants.
    """

    def __init__(
        self,
        *,
        policy: SafetyPolicy,
        tools: Mapping[str, ToolDefinition],
        approval_authority: ApprovalAuthority | None = None,
    ) -> None:
        self._policy = policy
        self._tools = dict(tools)
        self._approval_authority = approval_authority
        self._lock = Lock()
        self._steps_by_run: dict[str, int] = {}
        self._active_runs: set[str] = set()
        # Run IDs awaiting trusted confirmation cannot be reused concurrently.
        self._pending_confirmations: dict[str, int] = {}

        for name, definition in self._tools.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Tool names must be non-blank strings")
            if not isinstance(definition, ToolDefinition):
                raise TypeError(f"Invalid tool definition for {name!r}")

    @property
    def registered_tool_names(self) -> frozenset[str]:
        """Return a snapshot of registered tool names."""
        with self._lock:
            return frozenset(self._tools)

    @property
    def policy(self) -> SafetyPolicy:
        """Return the immutable safety policy used by this executor."""
        return self._policy

    def register_tool(self, name: str, definition: ToolDefinition) -> None:
        """Register a tool only when explicitly allowed by the policy."""
        if not isinstance(name, str) or not name.strip():
            raise SafetyViolation("Tool name must be a non-blank string")
        if not isinstance(definition, ToolDefinition):
            raise TypeError("definition must be a ToolDefinition")
        if name not in self._policy.allowed_tools:
            raise SafetyViolation(f"Tool is not allowlisted: {name}")
        if name in self._tools:
            raise SafetyViolation(f"Tool is already registered: {name}")

        with self._lock:
            if name in self._tools:
                raise SafetyViolation(f"Tool is already registered: {name}")
            self._tools[name] = definition

    def execute_with_confirmation(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        confirm: Callable[[str, dict[str, Any]], bool],
    ) -> Any:
        """Execute a tool, requiring trusted confirmation for write actions.

        The confirmation callback must belong to trusted application code.
        It receives the tool name and a detached copy of validated JSON
        arguments. Only the literal value True authorizes a write.
        """
        import copy

        if not callable(confirm):
            raise SafetyViolation("A trusted confirmation callback is required")
        if not isinstance(run_id, str) or not run_id.strip():
            raise SafetyViolation("run_id must be a non-blank string")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise SafetyViolation("Tool name must be a non-blank string")
        if not isinstance(arguments, Mapping):
            raise SafetyViolation("Tool arguments must be a mapping")

        definition = self._tools.get(tool_name)
        if definition is None:
            raise SafetyViolation(f"Tool is not registered: {tool_name}")

        try:
            validated = definition.args_model.model_validate(dict(arguments))
        except ValidationError as exc:
            raise SafetyViolation(
                f"Invalid arguments for tool {tool_name!r}"
            ) from exc

        normalized = validated.model_dump(mode="json")

        if tool_name not in self._policy.write_tools:
            return self.execute(
                run_id=run_id,
                tool_name=tool_name,
                arguments=normalized,
            )

        authority = self._approval_authority
        if authority is None:
            raise SafetyViolation(
                "Write execution is disabled: no trusted approval "
                "authority is configured"
            )

        # Reserve one exact step and mark confirmation as pending. Other
        # operations for this run must not consume or reset that reservation.
        with self._lock:
            if run_id in self._active_runs or run_id in self._pending_confirmations:
                raise SafetyViolation(
                    f"Recursive or concurrent execution rejected for run: {run_id}"
                )

            step = self._steps_by_run.get(run_id, 0)
            if step >= self._policy.max_steps:
                raise SafetyViolation(
                    f"Step limit exceeded for run {run_id!r}: "
                    f"maximum {self._policy.max_steps}"
                )

            self._steps_by_run[run_id] = step + 1
            self._pending_confirmations[run_id] = step

        try:
            preview = copy.deepcopy(normalized)
            try:
                confirmed = confirm(tool_name, preview)
            except Exception as exc:
                raise SafetyViolation(
                    "Confirmation failed; write action was not executed"
                ) from exc

            if confirmed is not True:
                raise SafetyViolation(
                    "Write action was not explicitly approved; nothing was executed"
                )

            grant = authority.issue_after_confirmation(
                run_id=run_id,
                tool_name=tool_name,
                arguments=normalized,
            )
            return self._execute_internal(
                run_id=run_id,
                tool_name=tool_name,
                arguments=normalized,
                approval=grant,
                reserved_step=step,
            )
        finally:
            with self._lock:
                self._pending_confirmations.pop(run_id, None)

    def finish_run(self, *, run_id: str) -> None:
        """Release run state after the trusted controller ends a run.

        Only the trusted orchestrator should call this method. Do not expose
        lifecycle controls to model-facing code.
        """
        if not isinstance(run_id, str) or not run_id.strip():
            raise SafetyViolation("run_id must be a non-blank string")

        with self._lock:
            if run_id in self._active_runs:
                raise SafetyViolation(
                    f"Cannot finish an active run: {run_id}"
                )
            if run_id in self._pending_confirmations:
                raise SafetyViolation(
                    f"Cannot finish a run awaiting confirmation: {run_id}"
                )
            self._steps_by_run.pop(run_id, None)

    def execute(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        approval: ApprovalGrant | None = None,
    ) -> Any:
        """Validate, authorize, and execute a handler at most once."""
        return self._execute_internal(
            run_id=run_id,
            tool_name=tool_name,
            arguments=arguments,
            approval=approval,
            reserved_step=None,
        )

    def _execute_internal(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        approval: ApprovalGrant | None,
        reserved_step: int | None,
    ) -> Any:
        """Internal execution path shared with trusted confirmation."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise SafetyViolation("run_id must be a non-blank string")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise SafetyViolation("Tool name must be a non-blank string")
        if not isinstance(arguments, Mapping):
            raise SafetyViolation("Tool arguments must be a mapping")

        with self._lock:
            if run_id in self._active_runs:
                raise SafetyViolation(
                    f"Recursive or concurrent execution rejected for run: {run_id}"
                )

            current_step = self._steps_by_run.get(run_id, 0)

            if reserved_step is not None:
                if self._pending_confirmations.get(run_id) != reserved_step:
                    raise SafetyViolation(
                        "The execution step reservation is missing or mismatched"
                    )
                if current_step != reserved_step + 1:
                    raise SafetyViolation(
                        "The execution step reservation is no longer current"
                    )
                step = reserved_step
            else:
                if run_id in self._pending_confirmations:
                    raise SafetyViolation(
                        f"Run is awaiting confirmation: {run_id}"
                    )
                step = current_step
                if step >= self._policy.max_steps:
                    raise SafetyViolation(
                        f"Step limit exceeded for run {run_id!r}: "
                        f"maximum {self._policy.max_steps}"
                    )

                # Denied/invalid attempts consume budget to prevent repeated probing.
                self._steps_by_run[run_id] = step + 1

            self._active_runs.add(run_id)

        try:
            definition = self._tools.get(tool_name)
            if definition is None:
                raise SafetyViolation(f"Tool is not registered: {tool_name}")

            try:
                validated_arguments = definition.args_model.model_validate(
                    dict(arguments)
                )
            except ValidationError as exc:
                raise SafetyViolation(
                    f"Invalid arguments for tool {tool_name!r}"
                ) from exc

            if tool_name in self._policy.write_tools:
                if self._approval_authority is None:
                    raise SafetyViolation(
                        "Write execution is disabled: no trusted approval "
                        "authority is configured"
                    )
                if approval is None:
                    raise SafetyViolation(
                        f"Explicit approval is required for write tool: {tool_name}"
                    )

                # Approval must match the validated representation passed
                # to the handler, including defaults and normalization.
                approved_arguments = validated_arguments.model_dump(mode="json")
                self._approval_authority.consume(
                    approval,
                    run_id=run_id,
                    tool_name=tool_name,
                    arguments=approved_arguments,
                )

            # Final policy gate immediately before calling the handler.
            authorize_tool_call(
                tool_name=tool_name,
                step=step,
                policy=self._policy,
                approved=(tool_name not in self._policy.write_tools)
                or approval is not None,
            )

            return definition.handler(validated_arguments)
        finally:
            with self._lock:
                self._active_runs.discard(run_id)
