from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class TraceValidationError(ValueError):
    """Trace fields contain unsupported or invalid values."""

def _safe_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TraceValidationError(f"{field} must be a finite number")
    return float(value)

class JSONLTraceRecorder:
    """Append small structured decision events; caller controls the file path."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record_decision(self, *, run_id: str, decision_id: str, step: int,
                        backend: str, chosen: str, confidence: float,
                        threshold: float, latency_ms: float, escalated: bool,
                        final_choice: str, final_source: str,
                        status: str = "success", error_type: str | None = None) -> dict[str, Any]:
        for name, value in (("run_id", run_id), ("decision_id", decision_id),
                            ("backend", backend), ("chosen", chosen),
                            ("final_choice", final_choice), ("final_source", final_source)):
            if not isinstance(value, str) or not value.strip():
                raise TraceValidationError(f"{name} must be a non-blank string")
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise TraceValidationError("step must be a non-negative integer")
        confidence = _safe_number(confidence, "confidence")
        threshold = _safe_number(threshold, "threshold")
        latency_ms = _safe_number(latency_ms, "latency_ms")
        if not 0 <= confidence <= 1 or not 0 <= threshold <= 1 or latency_ms < 0:
            raise TraceValidationError("confidence/threshold must be 0..1 and latency non-negative")
        if not isinstance(escalated, bool):
            raise TraceValidationError("escalated must be boolean")
        if status not in {"success", "error", "escalated"}:
            raise TraceValidationError("unsupported trace status")
        if error_type is not None and (not isinstance(error_type, str) or not error_type.strip()):
            raise TraceValidationError("error_type must be non-blank when provided")
        event = {"schema_version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
                 "event_type": "decision", "run_id": run_id, "decision_id": decision_id,
                 "step": step, "backend": backend, "chosen": chosen,
                 "confidence": confidence, "threshold": threshold, "latency_ms": latency_ms,
                 "escalated": escalated, "final_choice": final_choice,
                 "final_source": final_source, "status": status, "error_type": error_type}
        line = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return event
