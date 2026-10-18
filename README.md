# Jarvis Decider

Jarvis Decider is a decision-first agent-runtime prototype. It evaluates
narrow choices with a specialized decision backend and uses confidence
thresholds to identify decisions that may need escalation.

## Current implementation

- Provider-independent decision contracts.
- Mock backend and local Strands Decider backend.
- Confidence-threshold decision engine with a bounded fallback path.
- Synthetic 50-task evaluation dataset and evaluation reports.
- Safety guardrails and argument validation/approval controls for tool execution.
- Read-only GitHub MCP integration restricted to `list_branches`.
- JSONL decision tracing.
- Free-by-default configuration guard.

The Day 1 local decision workflow is executable. It does not claim to be a
complete autonomous task runner or submission-ready system.

## Cost configuration

- `COST_MODE` defaults to `free`.
- `ALLOW_PAID` defaults to `false`.
- `COST_MODE=production` requires explicit `ALLOW_PAID=true`.
- Invalid configuration values are rejected.

The configuration module validates these settings when loaded. Do not claim
that all paid-provider startup paths are blocked unless those paths call
`load_config()` and that behavior has been tested. Do not commit API keys.

## Run locally

Activate the project's virtual environment, then install the project if
it has not already been installed:

```bash
python -m pip install -e ".[dev]"
```

Validate configuration:

```bash
jarvis-decider --check-config
```

Run the end-to-end mock decision and local routing action:

```bash
jarvis-decider --run-demo
```

Expected output identifies the `mock` backend, selected destination,
escalation status, and local `task_routing` outcome. The action only returns a
structured result; it does not execute task content, modify files, or use the
network.

Run the safe mock trace demo:

```bash
jarvis-decider --demo-trace \
  --trace-path /tmp/jarvis-decider-demo.jsonl
cat /tmp/jarvis-decider-demo.jsonl
```

The default backend is mock. `--backend local_hf --run-demo` selects the
local Strands Decider backend; inference may require a model download and
additional local compute. Bedrock requires both `COST_MODE=production` and
`ALLOW_PAID=true`; the documented default command makes no AWS request.

The engine accepts confidence at or above the configured threshold and
escalates lower or unknown confidence to its fallback once. The demo configures
a local mock fallback for non-mock providers. Backend errors and invalid
choices stop before the action.

Tests and static checks

```bash
python -m pytest -q
python -m compileall -q src tests eval
git diff --check
```

Prototype evaluation

The checked-in reports evaluate 50 synthetic, hand-labeled tasks:

Local Strands Decider: 41/50 correct (82%).

Mock backend: 18/50 correct (36%).

These results are limited to the supplied synthetic dataset and should not
be interpreted as real-world accuracy. The reported escalation rate is a
threshold-based estimate only; the evaluation report says that no fallback
was invoked. Backend completion without errors does not imply correctness.

Latency varies substantially by task and local machine. Report the
measurement method and distribution, including outliers, when presenting it.

Known limitations

The synthetic evaluation set is small and hand-labeled.

Confidence thresholds are provisional; confidence calibration has not
been established.

The evaluation measures choice-label agreement and estimated escalation,
not full end-to-end task completion.

The application configuration guard protects this backend-selection path;
AWS IAM permissions and account controls remain separate. No live Bedrock
request has been verified. Synthetic
evaluation does not establish real-world accuracy, and model-provided
confidence is not automatically calibrated. Day 1 does not claim the project
is submission-ready.

Day 2 should focus on reviewing the synthetic evaluation labels and confidence
policy, hardening observability/redaction, and planning separately authorized
live-provider validation under appropriate AWS controls.

Live GitHub branch results depend on the configured repository's actual
state and permissions.
