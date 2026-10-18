"""Allowlisted, versioned JSONL decision trace serialization."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class TraceValidationError(ValueError):
    """Trace fields contain unsupported or invalid values."""


_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SENSITIVE = re.compile(
    r"(?i)(authorization\s*:|bearer\s+|AKIA[0-9A-Z]{16}|"
    r"(?:api[_-]?key|access[_-]?key|secret|token)\s*[:=])"
)
_STATUSES = {"success", "escalated", "rejected", "error"}
_ESCALATION_REASONS = {None, "below_threshold", "confidence_unavailable"}
_ERROR_CATEGORIES = {
    None,
    "primary_backend_error",
    "fallback_backend_error",
    "invalid_primary_choice",
    "invalid_fallback_choice",
    "invalid_backend_result",
    "escalation_unavailable",
    "decision_error",
}


def _safe_text(value: Any) -> str | None:
    """Keep short identifier-like values; omit values resembling secrets."""
    if not isinstance(value, str) or not _SAFE_TEXT.fullmatch(value.strip()):
        return None
    value = value.strip()
    if _SENSITIVE.search(value):
        return None
    return value


def _required_trace_text(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        raise TraceValidationError(f"{field} must be a non-blank string")
    return _safe_text(value)


def _safe_number(value: Any, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceValidationError(f"{field} must be a finite number")
    if not math.isfinite(value):
        raise TraceValidationError(f"{field} must be a finite number")
    return float(value)


class JSONLTraceRecorder:
    """Append a small schema-v2 event containing only allowlisted fields."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record_decision(
        self,
        *,
        run_id: str,
        decision_id: str,
        step: int,
        backend: str,
        chosen: str | None,
        confidence: float | None,
        threshold: float | None,
        latency_ms: float,
        escalated: bool,
        final_choice: str | None,
        final_source: str | None,
        status: str = "success",
        error_type: str | None = None,
        backend_role: str | None = None,
        fallback_invoked: bool = False,
        escalation_reason: str | None = None,
        validation_passed: bool | None = True,
        error_category: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise TraceValidationError("step must be a non-negative integer")
        confidence = _safe_number(confidence, "confidence", optional=True)
        threshold = _safe_number(threshold, "threshold", optional=True)
        latency_ms = _safe_number(latency_ms, "latency_ms")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise TraceValidationError("confidence must be between 0 and 1")
        if threshold is not None and not 0.0 <= threshold <= 1.0:
            raise TraceValidationError("threshold must be between 0 and 1")
        if latency_ms < 0:
            raise TraceValidationError("latency_ms must be non-negative")
        for name, value in (
            ("escalated", escalated),
            ("fallback_invoked", fallback_invoked),
        ):
            if not isinstance(value, bool):
                raise TraceValidationError(f"{name} must be boolean")
        if validation_passed is not None and not isinstance(validation_passed, bool):
            raise TraceValidationError("validation_passed must be boolean or null")
        if status not in _STATUSES:
            raise TraceValidationError("unsupported trace status")
        if escalation_reason not in _ESCALATION_REASONS:
            raise TraceValidationError("unsupported escalation reason")
        if error_category not in _ERROR_CATEGORIES:
            raise TraceValidationError("unsupported error category")

        event = {
            "schema_version": 2,
            "trace_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "decision",
            "run_id": _required_trace_text(run_id, "run_id"),
            "decision_id": _required_trace_text(decision_id, "decision_id"),
            "step": step,
            "backend": _safe_text(backend),
            "backend_role": _safe_text(backend_role),
            "chosen": _safe_text(chosen),
            "confidence": confidence,
            "threshold": threshold,
            "latency_ms": latency_ms,
            "fallback_invoked": fallback_invoked,
            "escalated": escalated,
            "escalation_reason": escalation_reason,
            "validation_passed": validation_passed,
            "final_choice": _safe_text(final_choice),
            "final_source": _safe_text(final_source),
            "status": status,
            "error_category": error_category,
            "error_type": _safe_text(error_type),
        }
        line = json.dumps(
            event, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return event
