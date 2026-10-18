# Decision Trace Schema v3

`JSONLTraceRecorder` appends one versioned JSON object per line. A Bedrock
workflow can emit a `backend_attempt` event followed by a `decision` event.
Other backends continue to emit the final decision event only.

## Fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer schema version (`3`). |
| `trace_id`, `timestamp` | Unique UUID and UTC ISO 8601 event time. |
| `event_type` | `backend_attempt` or `decision`. A Bedrock attempt event describes an individual adapter call to `converse`, including a retry. |
| `run_id`, `decision_id`, `step` | Safe, short identifiers and zero-based step. Text resembling credentials or headers is omitted. |
| `backend`, `backend_role` | Backend identifier and `primary` or `fallback` role when known. |
| `request_attempted` | For Bedrock, whether the adapter called `converse`; `false` means failure occurred while preparing the client, `true` means the SDK call was made. It does not prove AWS received the request. Other backend events use `null`. |
| `provider_attempt` | One-based attempt number for calls to `converse`; `0` means provider invocation was prevented during local validation/client setup. Other events use `null`. |
| `provider_outcome` | `success`, `invalid_request`, `invalid_response`, `timeout`, `throttling`, `authentication`, `authorization`, `configuration`, `service_unavailable`, `network_error`, `backend_error`, or `null`. |
| `chosen`, `final_choice`, `final_source` | Choice fields only on accepted decision events; sensitive-looking or unsafe text is omitted. Attempt events do not include choices. |
| `confidence`, `threshold` | Finite values from 0 to 1, or JSON `null` when unknown/unavailable. Bedrock confidence remains unknown. |
| `latency_ms` | Monotonic elapsed time for an adapter call on attempt events and for the whole engine call on decision events. |
| `fallback_invoked`, `escalated` | Whether a fallback was called and whether its result was accepted. |
| `escalation_reason` | `below_threshold`, `confidence_unavailable`, or `null`. |
| `validation_passed` | `true`, `false`, or `null` when execution failed before output validation. |
| `status` | `success`, `escalated`, `rejected`, or `error`. |
| `error_category`, `error_type` | Safe category and exception class only; no raw provider message. |

## Privacy behavior and limits

Serialization is allowlisted. It never accepts arbitrary request or response
objects, and filters supported text fields that resemble API keys, bearer
credentials, or authorization headers. Questions, contexts, score mappings,
environment variables, and complete provider responses are not serialized.
This narrow application policy cannot guarantee that sensitive data will never
appear in other logs or storage layers. The Bedrock request itself contains the
decision question and context; callers must avoid submitting confidential data
unless their data-handling requirements permit it.

If recording a successful backend attempt or decision fails, the workflow does
not return an accepted decision to the action layer. If recording a failed
backend attempt or decision fails, the original sanitized failure is preserved.
