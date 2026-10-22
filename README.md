# Arnova Decider

**An explainable decision engine for controlled AI workflows.** Arnova accepts a bounded decision request, validates its allowed choices, asks a backend to propose a route, applies a confidence threshold, and records the result. A low-confidence result can invoke one configured fallback; backend errors stop before the routing action.

**Repository:** [Aadiverse07/AWS](https://github.com/Aadiverse07/AWS)

**Live demo:** [arnova-decider.streamlit.app](https://arnova-decider.streamlit.app/) — deployed on Streamlit Community Cloud and verified from an unauthenticated browser session.

## Judge summary

The live dashboard is designed to be usable without cloud credentials. Its interactive workflow uses deterministic mock and fixture backends, and labels that mode clearly. Judges can explore the normal path, a low-confidence fallback, and a safe backend-error path; inspect trace evidence; review the historical synthetic benchmarks and audit trail; and download CSV exports. It records a routing result only; it does not execute task content. Bedrock is an opt-in adapter in the codebase, but this public demo does not call AWS and live behavior has not been verified.

## Problem and proposed solution

AI workflows often make routing or delegation choices without showing the policy or evidence behind them. Arnova puts a small, inspectable control layer around those decisions: validate inputs and allowed destinations, evaluate a backend response against explicit confidence policy, bound fallback to one attempt, stop safely on errors, and preserve a sanitized audit event.

The core design principle is **evidence travels with the outcome**. The dashboard's decision tree is derived from the actual workflow result and trace fields rather than a decorative, hard-coded success path.

## What is implemented

- A provider-independent decision request/result contract and decision engine.
- Deterministic mock and local Strands Decider backend paths.
- Threshold-based acceptance and a bounded, one-time fallback path.
- Safe task-routing action with an allowlist; it returns a structured route and does not execute task instructions.
- Versioned, allowlisted JSONL decision tracing and a historical audit view.
- Streamlit dashboard with Guided Demo, Evaluation Lab, and Audit Trail pages.
- Three deterministic scenarios: standard mock, low-confidence fallback fixture, and backend-error fixture.
- Synthetic benchmark reports and CSV downloads for evaluation records and historical or interactive traces.
- Cost-safety configuration and an opt-in, lazy AWS Bedrock adapter.
- Read-only GitHub MCP functionality limited to listing repository branches.

The dashboard currently runs the local deterministic demo path. It does not connect to Figma or Claude, and does not expose an authenticated live-model service.

## Workflow and architecture

```text
Dashboard / CLI
      │
      ▼
DecisionRequest validation ── destination allowlist
      │
      ▼
Primary backend proposes a choice + confidence
      │
      ▼
DecisionEngine compares confidence with configured threshold
   ┌──┴───────────────────────────────┐
   │ confidence meets threshold       │ low / unavailable confidence
   ▼                                  ▼
accept primary choice            invoke fallback once
   └────────────────┬─────────────────┘
                    ▼
       TaskRoutingAction returns route
                    │
                    ▼
       Sanitized JSONL trace / audit

Backend error or invalid choice ──► stop safely; no routing action
```

The runtime separates contracts, backend adapters, policy, actions, and observability. See [`src/jarvis`](src/jarvis), [`app/dashboard.py`](app/dashboard.py), [`app/demo_workflow.py`](app/demo_workflow.py), and the [trace schema](docs/decision-trace-schema.md). The interactive dashboard writes its run trace to a temporary local file and displays the resulting event; the checked-in historical trace is a separate audit dataset.

## Evaluation and how to read it

The checked-in reports cover **50 synthetic, hand-labeled tasks per backend**. They measure exact-choice label agreement on that dataset:

| Report | Exact-label matches | Interpretation |
|---|---:|---|
| Mock | 18/50 (36%) | Baseline behavior on the supplied synthetic tasks |
| Local Strands Decider | 41/50 (82%) | Recorded local-model benchmark result |

These are historical results, not a live model evaluation or evidence of real-world accuracy. The estimated escalation rate is computed from confidence and threshold; the report does not claim that a fallback was actually invoked during those benchmark runs. Latency is also historical and machine-dependent. The Evaluation Lab labels the data and exports accordingly. Source reports are in [`eval/reports`](eval/reports), and the audit methodology is documented in [`reports/evaluation/day2_evaluation.md`](reports/evaluation/day2_evaluation.md).

## Technology and repository map

- Python 3.11 or newer; Pydantic; PyYAML; boto3.
- Streamlit for the dashboard; pytest for the test suite.
- Optional local Strands Decider path; opt-in AWS Bedrock adapter.

```text
app/                  Streamlit dashboard and deterministic demo workflow
src/jarvis/           Decision contracts, engine, backends, actions, tracing, CLI
eval/                 Synthetic datasets, reports, evaluation and audit scripts
docs/                 Trace schema and Bedrock smoke-test guidance
reports/               Evaluation audit documentation
submission/            Delivery notes, demo script, and verification evidence
tests/                 Unit and integration tests
traces/                Checked-in historical demo trace
```

## Install and run

### macOS, Linux, and Windows

Install Python 3.11+ and Git. From the repository root:

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,dashboard]"
```

Start the dashboard:

```bash
streamlit run app/dashboard.py
```

Run the CLI mock workflow and configuration check:

```bash
jarvis-decider --check-config
jarvis-decider --run-demo
```

The default backend is mock. A safe trace demo writes only to the chosen local path:

```bash
jarvis-decider --demo-trace --trace-path /tmp/arnova-demo.jsonl
```

The dashboard's three guided scenarios are selected in the Guided Demo page. Choose a scenario, optionally edit the task and preferred route, select **Run Guided Demo**, and inspect the highlighted branch and trace. The standard run accepts the primary mock result; the fixture run falls back once; the error fixture stops without a routing action. Evaluation Lab and Audit Trail provide record inspection and CSV downloads.

### Checks

```bash
python -m pytest -q
python -m compileall -q src app tests eval
git diff --check
```

## Configuration and cost safety

The application defaults to free/mock operation. Safe example values are in [`.env.example`](.env.example); copy and adjust only values needed for a local run. Never commit real credentials.

| Variable | Default / purpose |
|---|---|
| `COST_MODE` | `free`; paid mode requires explicit production configuration |
| `ALLOW_PAID` | `false`; explicit opt-in required for paid provider selection |
| `BEDROCK_REGION` | No default; required to select Bedrock (or use standard AWS region variables) |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0`; configurable model ID or supported inference profile |

Do not put AWS keys in `.env`, Streamlit secrets, source, or screenshots. If a separate, authorized Bedrock evaluation is ever performed, use the standard AWS credential provider chain or an approved role, a dedicated region, and least-privilege IAM access. Apply account-level budgets and monitoring. The application guard does not replace IAM policy or billing controls. This delivery and the hosted mock demo make no AWS request.

## AWS Bedrock status and verification plan

An opt-in backend adapter is present. Provider selection is guarded by paid-mode opt-in and region configuration, and the client is lazy until inference. **No live Bedrock request was made or verified for this delivery.** The hosted judge demo remains functional with no AWS credentials.

For a separately approved smoke test, first review [`docs/bedrock-smoke-test.md`](docs/bedrock-smoke-test.md), choose an allowed model and region, provide credentials through the standard AWS provider chain, confirm least-privilege `bedrock:InvokeModel` access for only the intended model/profile, and explicitly enable paid mode. Monitor cost and remove temporary access afterward. Never create or distribute reusable AWS keys for judges. A future judge-facing live inference service would require separate authentication, quotas, monitoring, and budget safeguards.

## Integrations and roadmap

The current GitHub MCP client is read-only and supports `list_branches`; it does not create branches, commits, or pull requests. AWS Bedrock is adapter-present but live-unverified. Figma and Claude integrations are future possibilities, not current capabilities. Any future tool integration should use explicit permissions, narrow actions, approval gates where appropriate, and auditable traces.

Planned work includes a larger independently reviewed evaluation set, confidence calibration, stronger end-to-end workflow measures, deployment monitoring, and governed integrations. Current limitations include a small synthetic benchmark, provisional confidence thresholds, no demonstrated calibration, no live Bedrock verification, and no autonomous execution of task content.

## Security and privacy

- Demo inputs are processed in the Streamlit session; the workflow records routing decisions, not task execution.
- Trace fields follow an allowlisted schema; inspect [`docs/decision-trace-schema.md`](docs/decision-trace-schema.md) for field and privacy limits.
- Mock and fixture scenarios require no credentials and perform no paid inference.
- `.gitignore` excludes local environments, secret files, caches, and generated runtime traces.
- Do not enter sensitive personal, customer, or credential data into the public demo.

## Changelog — delivery

- Added a judge-facing project explanation, architecture and workflow, setup and demo instructions, evaluation caveats, security and cost guidance, integration status, and roadmap.
- Added a pinned Streamlit Community Cloud dependency manifest and safe environment example.
- Updated ignore rules for local AWS and Streamlit credentials and private key files.
- Deployed the dashboard publicly on Streamlit Community Cloud; included the sanitized five-event historical trace required by the hosted Audit Trail.
- Fixed Cloud entrypoint import resolution so the dashboard works from Streamlit's script-path execution context.
- The dashboard, trace-backed decision visualization, guided scenarios, evaluation/audit pages, and CSV exports are included as project functionality; their test results are reported only after the final checks are run.
