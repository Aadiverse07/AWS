"""One-time grants for write actions approved by a trusted caller.

Only the trusted UI/controller should hold ApprovalAuthority. The model-facing
agent should receive ToolExecutor, not ApprovalAuthority.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from jarvis.safety.guardrails import SafetyViolation


def _canonical_arguments(arguments: Mapping[str, Any]) -> str:
    """Create a stable representation for binding approval to exact arguments."""
    try:
        return json.dumps(
            dict(arguments),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SafetyViolation(
            "Approval arguments must contain JSON-compatible values"
        ) from exc


@dataclass(frozen=True)
class ApprovalGrant:
    """Opaque in-process reference to a grant; not a user identity credential."""

    _grant_id: str


class ApprovalAuthority:
    """Issue and consume one-time grants after trusted user confirmation.

    Architectural rule: do not expose this object or its issue method to the
    model-facing agent. Call issue_after_confirmation only from a trusted
    controller after explicit user confirmation. This is an application-level
    boundary, not a defense against arbitrary code running in the same process.
    """

    def __init__(self, *, max_pending_grants: int = 1024) -> None:
        if (
            isinstance(max_pending_grants, bool)
            or not isinstance(max_pending_grants, int)
            or max_pending_grants < 1
        ):
            raise ValueError("max_pending_grants must be a positive integer")
        self._lock = Lock()
        self._grants: dict[str, tuple[str, str, str]] = {}
        self._max_pending_grants = max_pending_grants

    def issue_after_confirmation(
        self,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> ApprovalGrant:
        """Issue a grant for one exact action after confirmation has occurred."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise SafetyViolation("run_id must be a non-blank string")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise SafetyViolation("Tool name must be a non-blank string")
        if not isinstance(arguments, Mapping):
            raise SafetyViolation("Approval arguments must be a mapping")

        fingerprint = _canonical_arguments(arguments)
        grant_id = secrets.token_urlsafe(32)

        with self._lock:
            if len(self._grants) >= self._max_pending_grants:
                raise SafetyViolation(
                    "Pending approval grant limit reached; "
                    "consume or revoke a pending grant before issuing another"
                )
            self._grants[grant_id] = (run_id, tool_name, fingerprint)

        return ApprovalGrant(grant_id)

    def consume(
        self,
        grant: ApprovalGrant,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> None:
        """Consume a grant once, and only for its exact bound action."""
        if not isinstance(grant, ApprovalGrant):
            raise SafetyViolation("A valid approval grant is required")

        fingerprint = _canonical_arguments(arguments)

        with self._lock:
            binding = self._grants.get(grant._grant_id)
            if binding is None:
                raise SafetyViolation("Approval grant is invalid or already used")

            # Consume before returning; mismatched attempts cannot reuse a grant.
            del self._grants[grant._grant_id]

        expected = (run_id, tool_name, fingerprint)
        if binding != expected:
            raise SafetyViolation(
                "Approval grant does not match this run, tool, and arguments"
            )
