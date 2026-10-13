"""Deterministic policy checks before a tool is allowed to execute."""

from dataclasses import dataclass


class SafetyViolation(PermissionError):
    """Raised when a proposed tool action violates safety policy."""


@dataclass(frozen=True)
class SafetyPolicy:
    """Explicit tool allowlist, write approval requirements, and step limit."""

    allowed_tools: frozenset[str]
    write_tools: frozenset[str] = frozenset()
    max_steps: int = 5

    def __post_init__(self) -> None:
        # Normalize collections so callers cannot mutate policy through a set.
        object.__setattr__(self, "allowed_tools", frozenset(self.allowed_tools))
        object.__setattr__(self, "write_tools", frozenset(self.write_tools))

        if any(not isinstance(tool, str) or not tool.strip()
               for tool in self.allowed_tools):
            raise ValueError("allowed_tools must contain non-blank strings")

        if any(not isinstance(tool, str) or not tool.strip()
               for tool in self.write_tools):
            raise ValueError("write_tools must contain non-blank strings")

        if not self.write_tools.issubset(self.allowed_tools):
            raise ValueError("write_tools must be a subset of allowed_tools")

        if (
            isinstance(self.max_steps, bool)
            or not isinstance(self.max_steps, int)
            or self.max_steps < 1
        ):
            raise ValueError("max_steps must be a positive integer")


def authorize_tool_call(
    *,
    tool_name: str,
    step: int,
    policy: SafetyPolicy,
    approved: bool = False,
) -> None:
    """Raise SafetyViolation unless a proposed tool call is permitted.

    Steps are zero-based. With max_steps=5, steps 0 through 4 are allowed.
    This function does not execute the tool; callers must invoke it immediately
    before execution and must not bypass it.
    """
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise SafetyViolation("Tool name must be a non-blank string")

    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise SafetyViolation("Step must be a non-negative integer")

    if step >= policy.max_steps:
        raise SafetyViolation(
            f"Step limit exceeded: step {step}, maximum {policy.max_steps}"
        )

    if tool_name not in policy.allowed_tools:
        raise SafetyViolation(f"Tool is not allowlisted: {tool_name}")

    if tool_name in policy.write_tools and approved is not True:
        raise SafetyViolation(
            f"Explicit approval is required for write tool: {tool_name}"
        )
