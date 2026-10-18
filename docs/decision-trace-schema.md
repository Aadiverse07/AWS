# Decision Trace Schema v2

`JSONLTraceRecorder` writes one versioned JSON object per line. The schema is
used by `TracingDecisionEngine`; it does not store prompts, contexts, full
backend responses, or exception messages.

## Fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer schema version (`2`). |
| `trace_id` | Unique UUID for this event. |
| `timestamp` | UTC ISO 8601 timestamp. |
| `event_type` | Currently `decision`. |
| `run_id`, `decision_id`, `step` | Safe, short identifiers and zero-based step. Text resembling credentials or headers is omitted. |
| `backend`, `backend_role` | Backend identifier and `primary`/`fallback` role when known. |
| `chosen`, `final_choice`, `final_source` | Allowed result values only on accepted paths; sensitive-looking or unsafe text is omitted. |
| `confidence`, `threshold` | Finite values from 0 to 1, or JSON `null` when unknown/unavailable. |
| `latency_ms` | Monotonic elapsed time through the decision engine call. |
| `fallback_invoked`, `escalated` | Whether the fallback was actually called, and whether its result was accepted. For a failed fallback call, `fallback_invoked=true` and `escalated=false`. |
| `escalation_reason` | `below_threshold`, `confidence_unavailable`, or `null`. |
| `validation_passed` | `true`, `false`, or `null` when backend execution failed before output validation. |
| `status` | `success`, `escalated`, `rejected`, or `error`. |
| `error_category`, `error_type` | Safe category and exception class only; no raw exception message. |

## Privacy behavior and limits

Serialization is allowlisted. It never accepts arbitrary request or response
objects, and filters supported text fields that resemble API keys, bearer
credentials, or authorization headers. Unsafe text fields become `null`.
Questions, contexts, score mappings, environment variables, and exception
messages are not serialized. This is a narrow application trace policy, not a
guarantee that all possible sensitive data can never appear in every log or
storage layer.

If writing a successful decision trace fails, `TracingDecisionEngine` raises
the storage error and does not return a decision to the application action
layer. If recording an engine failure also fails, the original sanitized
engine error remains the visible failure. Tracing does not change a valid
decision's selected choice.
