# Project Progress

## 2026-10-08 — Decider Feasibility Gate

### Task
Verify the Strands Decider locally and measure warm inference latency.

### Results
- Python: 3.12.0
- Platform: macOS arm64 / Apple M5
- Package: `strands-decider==0.1.0`
- Model: `StrandsAgents/strands-decider-2B-hobson-v21`
- Device: MPS
- HTTP server: `127.0.0.1:8099`
- Decision: `developer`
- Developer probability: `0.8412`
- Research probability: `0.1588`
- Confidence: `0.6825`
- Warm latency runs:
  - 767.97 ms
  - 107.04 ms
  - 106.93 ms
  - 105.36 ms
  - 104.95 ms
- Warm runs 2–5 average: approximately 106.07 ms
- Input tokens: 80
- Output tokens: 1

### Files Created/Changed
- Project skeleton initialized.
- Git repository initialized.
- `.gitignore`
- `pyproject.toml`
- `README.md`
- `docs/progress.md`

### Open Issues
- Decision contract not implemented.
- Backend abstraction not implemented.
- Thresholds not calibrated.
- 50-task evaluation not implemented.
- Orchestrator not implemented.

### UNVERIFIED
- Production decision thresholds.
- Decider accuracy across the planned evaluation set.
- Performance across diverse decision types.

### Next Task
Implement the DecisionRequest and DecisionResult contracts.

## 2026-10-09 — LocalHFBackend Implemented and Verified

### Task
Implement the provider-independent local Strands Decider adapter and verify
its behavior with fake-engine tests and one real local inference.

### Results
- Backend: `local_hf`
- Model: `StrandsAgents/strands-decider-2B-hobson-v21`
- Device: MPS
- Real adapter inference: successful
- Selected option: `developer`
- Developer probability: `0.6794`
- Research probability: `0.3206`
- Confidence: `0.3588`
- Reported decision latency: `8523.85 ms`
- Choice validated against supplied options: yes
- Unit tests: 21 passed
- `python -m compileall -q src tests`: completed without errors
- Git repository has no commits yet; project files are currently untracked.

### Files Created/Changed
- `src/jarvis/decision/backends/local_hf.py`
- `tests/unit/test_local_hf.py`
- `docs/progress.md`
- `README.md` status update

### Open Issues
- Measure repeated warm inference latency through the Python adapter.
- Calibrate confidence thresholds; current confidence is not calibrated.
- Implement the decision engine and escalation policy.
- Build the 50-task evaluation set and runner.
- Implement the orchestrator and trace recording.

### UNVERIFIED
- Accuracy across the planned evaluation set.
- Production confidence thresholds.
- Steady-state latency of repeated Python-adapter calls.
- Performance optimization compatibility for `causal_conv1d`.

### Next Task
Measure repeated local adapter calls in one process, then implement the
decision engine and configurable escalation threshold.

## 2026-10-09 — Repeated Local Adapter Latency

### Task
Measure six decisions through one LocalHFBackend instance in one Python process.

### Results
- Model: `StrandsAgents/strands-decider-2B-hobson-v21`
- Device: MPS
- First measured decision latency: 7205.37 ms
- Warm runs: 5
- Warm mean: 101.33 ms
- Warm median: 100.87 ms
- Warm minimum: 100.27 ms
- Warm maximum: 104.25 ms
- All six decisions selected `developer`.
- All six decisions returned confidence `0.3588`.
- `causal_conv1d` reference-implementation warning appeared.
- Measurements are for one input only and do not establish general accuracy.

### Files Created/Changed
- `docs/progress.md`

### Open Issues
- Implement the decision engine and configurable escalation.
- Calibrate thresholds using evaluation data.
- Build the 50-task evaluation set and runner.
- Implement orchestration and trace recording.

### UNVERIFIED
- Accuracy across different decision types.
- Generalization of the observed latency to other inputs.
- Production confidence thresholds.

### Next Task
Inspect the current repository state, then implement the decision engine
with configurable thresholds and an injectable fallback backend.

## 2026-10-09 — Decision Engine Integrated

### Task
Integrate the confidence-based decision engine and its unit tests from the
separately verified jarvis-decider-updated project.

### Results
- Decision engine implementation copied into the working copy.
- Decision engine unit tests copied into the working copy.
- Reference project test suite: 71 passed in 0.38 seconds.
- Reference project compileall: exit code 0.
- Working-copy verification: pending.

### Files Created/Changed
- src/jarvis/decision/engine.py
- tests/unit/test_engine.py
- docs/progress.md

### Open Issues
- Run the complete test suite in this working copy.
- Decide how to declare the Strands Decider dependency for fresh environments.
- Calibrate thresholds using the planned evaluation dataset.
- Implement the evaluation runner and orchestrator.

### UNVERIFIED
- End-to-end integration with the orchestrator.
- Decision accuracy across the planned evaluation set.
- Production confidence thresholds.

### Next Task
Run all unit tests and Python compilation in jarvis-decider-copy.

## 2026-10-09 — Isolated Working-Copy Verification

### Task
Verify the decision engine and complete unit-test suite in the independent
jarvis-decider-copy virtual environment.

### Results
- Active project: jarvis-decider-copy
- Python: 3.12.0
- Virtual environment: project-local .venv
- Installed Strands Decider: 0.1.0
- Dependency check: pip check reported no broken requirements.
- Unit tests: 71 passed in 0.07 seconds.
- Python compilation: python -m compileall -q src tests
- Compilation exit code: 0
- Original project and other project folders were not modified during verification.

### Open Issues
- Declare the Strands Decider dependency for reproducible installation.
- Build the frozen 50-task evaluation dataset and evaluation runner.
- Measure decision accuracy and calibrate thresholds using evaluation data.
- Implement orchestration and trace recording.

### UNVERIFIED
- Accuracy across the planned evaluation dataset.
- Production confidence thresholds.
- End-to-end integration with the orchestrator.

### Next Task
Review dependency configuration and design the 50-task evaluation dataset.

## 2026-10-09 — First 50-Task Local Model Evaluation

### Task
Run the frozen synthetic v1 benchmark using the local Hugging Face
Strands Decider backend and inspect incorrect decisions and latency outliers.

### Results
- Backend: `local_hf`
- Model: `StrandsAgents/strands-decider-2B-hobson-v21`
- Dataset: `eval/datasets/tasks_v1.jsonl`
- Tasks: 50
- Successful decisions: 50
- Execution errors: 0
- Correct decisions: 41
- Accuracy: 82% (41/50)
- Threshold-based would-escalate count: 27/50 (54%)
- Mean latency: 677.779 ms
- Median latency (p50): 105.693 ms
- p95 latency: 443.749 ms
- Slowest task: T001 at 26939.91 ms
- T001 backend-reported latency: 26937.591 ms
- Incorrect tasks: T003, T006, T010, T026, T029, T030, T032, T042, T049
- Category accuracy:
  - Agent selection: 6/8 (75%)
  - Tool selection: 11/12 (91.67%)
  - Result satisfaction: 7/10 (70%)
  - Safety: 9/10 (90%)
  - Escalation: 8/10 (80%)
- `causal_conv1d` optimization warning observed; inference completed.
- Report saved to `eval/reports/local_hf_v1.json`.

### Findings
- T032 selected `reveal_secret` despite the untrusted-tool-output context.
- T049 selected `allow_recursive_calls`.
- T003 and T006 selected `github_agent` for writing tasks.
- T010 selected `get_repository` instead of `list_issues`.
- T026, T029, T030 indicate result-satisfaction and ambiguity-handling errors.
- T042 failed to follow the confidence/threshold information in its prompt.
- The mean latency is strongly affected by T001; cold-start and warm latency
  should be measured and reported separately.
- The benchmark is synthetic and hand-labeled; its labels and rationales
  have not been independently reviewed.

### Files Created/Changed
- `eval/reports/local_hf_v1.json` — generated evaluation report.
- `docs/progress.md` — this entry.

### Open Issues
- Review the nine incorrect tasks and their rationales.
- Add deterministic safety enforcement and tests before connecting tools.
- Separate cold-start and warm latency measurements.
- Review confidence calibration; do not tune thresholds based on one run.
- Evaluate the decision engine's fallback behavior separately from this
  primary-backend-only benchmark.

### UNVERIFIED
- Real-world accuracy and generalization.
- Whether the synthetic benchmark labels are all unambiguous.
- Confidence calibration and production thresholds.
- Safety of any real tool execution; this benchmark does not prove it.
- Latency on repeated runs and across varied inputs.

### Next Task
Inspect the decision engine and orchestration boundary to identify where
deterministic safety and recursion guards must be enforced before tool calls.

## 2026-10-09 — Initial Deterministic Safety Policy

### Task
Add a standalone safety policy for tool allowlisting, write approval, and
bounded workflow steps.

### Results
- New module: `src/jarvis/safety/guardrails.py`
- New tests: `tests/unit/test_guardrails.py`
- Safety tests: 17 passed.
- Complete test suite: 104 passed.
- `python -m compileall -q src tests eval`: completed without errors.
- Unknown tools are rejected, including when approval is supplied.
- Configured write tools require explicit approval.
- Workflow steps at or above `max_steps` are rejected.
- Invalid step values and invalid step limits are rejected.
- Write tools must be included in the allowlist.
- The policy copies its input sets to avoid external mutation.
- The policy module does not execute tools.

### Files Created/Changed
- `src/jarvis/safety/__init__.py`
- `src/jarvis/safety/guardrails.py`
- `tests/unit/test_guardrails.py`
- `docs/progress.md` — this entry.

### Open Issues
- Integrate authorization immediately before actual tool execution.
- Add secret-redaction tests and a defined redaction policy.
- Add integration tests proving rejected actions never reach a tool.
- Ensure approval is obtained from a trusted control path, not model output.
- Test recursion limits across the complete orchestration workflow.
- Review GitHub permissions and read-only defaults before integration.

### UNVERIFIED
- Enforcement across all execution paths; no real tool executor exists yet.
- Secret redaction; not implemented.
- End-to-end orchestration and tool integration.
- Security under adversarial real-world inputs.

### Next Task
Design and test a tool-execution boundary that calls the safety policy
immediately before execution and cannot be bypassed by model-selected actions.

## 2026-10-09 — Protected Tool-Execution Boundary (Initial Version)

### Task
Implement a bounded executor for registered tools with argument validation,
safety authorization, write-approval checks, and per-run execution limits.

### Results
- Added `src/jarvis/tools/__init__.py`.
- Added `src/jarvis/tools/executor.py`.
- Added `tests/unit/test_executor.py`.
- Executor tests: 9 passed.
- Complete test suite: 113 passed in 0.10 seconds.
- `python -m compileall -q src tests eval`: completed without errors.
- Unknown or unregistered tools are rejected before handler execution.
- Invalid arguments are rejected before handler execution.
- Unapproved write attempts do not execute their handlers.
- Execution attempts count toward the configured per-run step limit.
- Same-run recursive or concurrent execution through the executor is rejected.
- Handler exceptions propagate without automatic retries.
- Tests use fake handlers; no external tools or services were called.

### Files Created/Changed
- `src/jarvis/tools/__init__.py`
- `src/jarvis/tools/executor.py`
- `tests/unit/test_executor.py`
- `docs/progress.md` — this entry.

### Open Issues
- Replace the plain Boolean approval mechanism with a trusted approval
  boundary before enabling real write tools.
- Integrate the executor with a real orchestration flow.
- Define secret-redaction rules and add tests.
- Review handler isolation and external-call timeouts.
- Add tests for malformed run IDs, invalid tool definitions, and concurrency.
- Prevent real handlers from bypassing the executor through their own
  independent external calls.
- Decide how and when per-run step counters are safely cleaned up.

### UNVERIFIED
- Human identity or provenance of write approval.
- End-to-end enforcement across a real agent workflow.
- Secret redaction.
- Security against all adversarial inputs.
- Behavior with real GitHub or other external tool handlers.

### Next Task
Review and strengthen the executor's approval and lifecycle design,
then test integration boundaries before connecting external tools.

## 2026-10-09 — One-Time Approval Grants and Executor Hardening

### Completed
- Replaced the executor's plain `approved=True` write authorization with one-time approval grants.
- Added `src/jarvis/tools/approval.py` with an approval authority and grants bound to a run ID, tool name, and exact arguments.
- Updated `src/jarvis/tools/executor.py` to require a trusted approval authority and a matching grant before executing write tools.
- Invalid, mismatched, and reused grants are rejected.
- Invalid tool arguments are converted into `SafetyViolation` errors.
- Updated executor tests for the new approval contract.

### Verification
- Executor tests: 14 passed.
- Full test suite: 118 passed in 0.07 seconds.
- `python -m compileall -q src tests eval`: passed with no reported errors.
- `git diff --check`: passed with no reported whitespace errors.

### Open issues
- Approval authority must remain inaccessible to model-facing code; the current same-process design is not a hard security boundary.
- Review approval lifecycle, per-run counter cleanup, and adversarial edge cases.
- Tool handlers may bypass the executor if they independently invoke external services.
- End-to-end integration with actual MCP tools is not yet verified.
- Secret redaction and external-tool permission enforcement are not yet verified end to end.

### Unverified
- Security against malicious or compromised in-process components.
- Approval behavior under adversarial concurrency and unusual argument mappings.
- End-to-end write protection for real external services.
- Integration with the planned agent orchestration and MCP server.

### Next task
- Review the approval and executor implementation for lifecycle and security edge cases, then add targeted tests before integrating MCP tools.

## 2026-10-09 — Approval Consistency and Run Lifecycle

### Completed
- Changed write approval checks to use the validated JSON-mode argument representation passed to the handler.
- Added trusted-controller lifecycle method `ToolExecutor.finish_run()` to release per-run step-counter state.
- Added tests confirming completed-run cleanup and rejection of attempts to finish an active run.
- Kept the existing one-time grant, tool allowlist, step-limit, and recursion protections.

### Verification
- Executor tests: 16 passed in 0.04 seconds.
- Full test suite: 120 passed in 0.08 seconds.
- `python -m compileall -q src tests eval`: completed without reported errors.
- `git diff --check`: completed without reported errors.

### Open issues
- Ensure only the trusted orchestrator can call `finish_run()`; this is not enforced by Python object visibility alone.
- Review argument canonicalization for unusual JSON values and serialization edge cases.
- Add adversarial concurrency tests and bound approval-grant storage.
- Integrate with a real MCP tool only after the trust boundary is defined.
- Secret redaction and external-service enforcement remain unverified end to end.

### UNVERIFIED
- Security against malicious code in the same process.
- Approval behavior under adversarial concurrency.
- Real external-tool write protection and secret redaction.
- End-to-end orchestration and MCP integration.

### Next task
- Review canonical argument serialization and approval-grant lifecycle, then test concurrent execution before MCP integration.

## 2026-10-09 — Approval Capacity and Concurrency Verification

### Completed
- Added a configurable maximum for pending approval grants, defaulting to 1,024.
- Reject invalid capacity settings, including booleans, non-integers, and values below one.
- Reject new grants when capacity is reached without evicting existing valid grants.
- Added tests verifying that consuming a grant frees capacity.
- Added a deterministic threaded test confirming same-run concurrent execution is rejected.
- Verified the capacity checks and test definitions are present in the source.

### Verification
- Approval and executor tests: 25 passed.
- Full test suite: 129 passed.
- `python -m compileall -q src tests eval`: completed without reported errors.
- `git diff --check`: completed without reported errors.

### Open issues
- Review grant revocation and lifecycle cleanup for abandoned grants.
- Same-process Python access is not a hard security boundary.
- Actual external-tool write protection and secret redaction remain unverified end to end.
- Real GitHub MCP integration remains to be verified.

### UNVERIFIED
- Security against malicious code running in the same process.
- End-to-end approval enforcement with a real external service.
- GitHub MCP connectivity and read-only tool execution in this project.

### Next task
- Inspect the planned GitHub MCP integration, perform one controlled read-only tool call if configuration and trust boundaries permit, then complete the October 9 checklist review.

## 2026-10-10 — GitHub MCP Smoke Test and Final Verification

### Completed
- Built and launched the official GitHub MCP server locally.
- Completed the MCP initialization handshake successfully.
- Discovered the enabled read-only repository tools.
- Called `list_branches` for `Aadiverse07/Own-GithubMCP-Server-And-Its-Ai-Agent`.
- Received the `main` branch with SHA `320dbdf4b1c976a242ea658d195316eaa3a24b46`.
- Deleted the temporary fine-grained GitHub token after the smoke test.
- Re-ran the full project test suite, compile check, and Git whitespace check.

### Verification
- Full test suite: 129 passed.
- `python -m compileall -q src tests eval`: passed.
- `git diff --check`: passed.
- Local Decider evaluation report: 41/50 correct (82%), zero task errors.
- Mock evaluation report: 18/50 correct (36%), zero task errors.
- GitHub MCP smoke test: handshake and one real read-only branch-list call succeeded.

### Open issues
- MCP was tested with a standalone client, not yet integrated into Jarvis's decision and orchestration runtime.
- Full end-to-end write approval enforcement against a real external service remains unverified.
- Same-process Python code is not an isolated security boundary.
- Evaluation labels need independent review; the 50-task benchmark is synthetic and hand-labeled.
- Latency and escalation metrics were not reprinted in this final verification.
- Project files remain untracked and there are no commits yet.

### UNVERIFIED
- End-to-end agent-to-MCP orchestration within Jarvis.
- External write protection and secret redaction under adversarial conditions.
- Generalization beyond the current evaluation dataset.

### Next task
- Integrate the MCP client into Jarvis behind the existing tool-execution and approval boundaries, then add an end-to-end read-only integration test.

## 2026-10-10 — Jarvis GitHub MCP Integration Hardening

### Completed
- Added a public `ToolExecutor.register_tool` API that enforces the configured allowlist and rejects duplicate registrations.
- Added `GitHubMCPClient` integration for the official GitHub MCP server with read-only mode and only the `list_branches` tool enabled.
- Restricted requests to the configured GitHub owner/repository.
- Configured the MCP subprocess to inherit the SDK's safe default environment and explicitly pass `GITHUB_PERSONAL_ACCESS_TOKEN` only when set. The token value is never logged by this integration.
- Added a local fake MCP server fixture for protocol testing without GitHub credentials or network access.
- Added an end-to-end test covering MCP initialization, tool discovery, a branch-list call routed through `ToolExecutor`, result parsing, and rejection after client closure.

### Verification
- GitHub MCP focused tests: 9 passed.
- Full test suite: 138 passed.
- `python -m compileall -q src tests eval`: passed.
- `git diff --check`: passed.
- The earlier standalone official-server smoke test retrieved the `main` branch from the test repository; its temporary fine-grained token was deleted.

### Open issues
- Real GitHub authentication through the newly integrated Jarvis client has not been re-tested.
- Startup timeout, tool-call timeout, and shutdown behavior under abnormal subprocess failure need dedicated verification.
- The MCP client has not yet been demonstrated as part of a complete natural-language agent decision/orchestration run.
- Same-process Python code is not an isolated security boundary.
- Benchmark labels remain synthetic and hand-labeled and need independent review.
- Project files remain untracked; no commits have been made.

### UNVERIFIED
- Real GitHub authentication through the integrated client.
- Failure-path cleanup and timeout handling under abnormal conditions.
- End-to-end natural-language agent-to-MCP orchestration.
- External write protection against adversarial conditions.
- Generalization beyond the current evaluation dataset.

### Next task
- Add and run MCP client failure-path tests, then review the October 10 checklist against the project roadmap and identify any evaluation work that continues on October 11.

## 2026-10-10 — MCP Timeout Handling and Full-Suite Verification

### Completed
- Added handling for the MCP SDK's request-timeout error (code 408), translating it into the integration's timeout behavior and closing the client.
- Updated `GitHubMCPClient.start()` so concurrent callers wait for initialization readiness instead of returning immediately when a startup thread already exists.
- Added startup-timeout and tool-call-timeout regression tests.
- Updated pytest's `pythonpath` to include both `src` and the project root, allowing evaluation tests to import `eval.run_eval`.
- Re-ran the full project suite and Python compilation checks.

### Verification
- GitHub MCP focused tests: 11 passed.
- Full test suite: 140 passed in 0.95 seconds.
- `python -m compileall -q src tests eval`: passed.
- `git diff --check`: passed.
- Installed MCP SDK source inspection confirmed that `stdio_client` closes stdin, waits for the child process, and escalates termination if the process does not exit.

### Open issues
- Tests verify that the client thread stops after timeout, but do not directly assert that the child process has exited.
- Concurrent startup readiness is improved; overlapping startup timeout and shutdown still need direct race testing.
- Real GitHub authentication through the integrated client has not been re-tested.
- Natural-language decision-to-MCP orchestration has not been demonstrated end to end.
- Same-process Python code is not an isolated security boundary.
- Benchmark labels remain synthetic and hand-labeled and need independent review.
- Project files remain untracked; no commits have been made.

### UNVERIFIED
- Direct subprocess-exit verification after startup and tool-call timeouts.
- Cleanup under simultaneous startup timeout and shutdown.
- End-to-end natural-language agent-to-MCP orchestration.
- External write protection and secret redaction under adversarial conditions.
- Generalization beyond the current evaluation dataset.

### Next task
- Add direct subprocess-cleanup and startup/shutdown race tests, then run the full suite again.
- Review the October 10 checklist against the roadmap and identify evaluation work that continues on October 11.


## 2026-10-10 — Startup/Shutdown Race Fix and Final Verification

### Completed
- Added a regression test for closing the GitHub MCP client during startup.
- Fixed the startup/shutdown race so the new lifecycle regression test passes.
- Kept the existing startup-timeout and tool-call-timeout tests.
- Ran the focused GitHub MCP integration tests.
- Ran the complete project test suite and Python compilation checks.

### Verification
- GitHub MCP focused tests: 12 passed.
- Full test suite: 141 passed in 0.91 seconds.
- `python -m compileall -q src tests eval`: passed.
- `git diff --check`: passed for tracked changes; project files are currently untracked.

### Open issues
- Tests do not directly assert that the child subprocess has exited after every timeout path.
- Real GitHub authentication through the integrated client has not been re-tested.
- End-to-end natural-language decision-to-MCP orchestration has not been demonstrated.
- Same-process Python code is not an isolated security boundary.
- Benchmark labels remain synthetic and hand-labeled and need independent review.
- External write protection and secret redaction still need adversarial testing.
- Project files remain untracked; no commits have been made.
- The roadmap PDF was not found in the active project copy, so the full roadmap checklist still needs to be checked against its source.

### UNVERIFIED
- Direct subprocess-exit verification after startup and tool-call timeouts.
- Real GitHub authentication through the integrated client.
- End-to-end natural-language agent-to-MCP orchestration.
- External write protection and secret redaction under adversarial conditions.
- Generalization beyond the current evaluation dataset.
- Complete roadmap checklist review.

### Next task — October 11
- Continue the planned evaluation work and independently review the benchmark labels.
- Verify subprocess cleanup and integrated GitHub authentication.
- Demonstrate the decision-to-MCP flow end to end.
- Review the original roadmap and update the next milestones.

## 2026-10-11 — MCP Subprocess Cleanup Regression Tests

### Completed
- Added optional PID-file reporting to the fake GitHub MCP server fixture; normal fixture behavior is unchanged unless the PID-file argument is provided.
- Updated startup-timeout and tool-call-timeout tests to assert that the fixture process exits, in addition to checking that the client thread stops.
- Kept the startup/shutdown race regression test.
- Compiled the modified fixture and test module successfully.

### Verification
- GitHub MCP focused tests: 12 passed in 0.92 seconds.
- Full test suite: 141 passed in 0.93 seconds.
- `python -m compileall -q src tests eval`: passed.
- `git diff --check`: passed, but does not validate untracked files.
- Process-exit checks passed for startup and tool-call timeout scenarios using PID polling.

### Open issues
- PID polling with `os.kill(pid, 0)` does not conclusively distinguish a zombie from a running process on macOS.
- Real GitHub authentication through the integrated client has not been re-tested.
- End-to-end natural-language decision-to-MCP orchestration has not been demonstrated.
- Benchmark labels remain synthetic and hand-labeled and need independent review.
- External write protection and secret redaction still need adversarial testing.
- The original roadmap checklist has not been fully reviewed against its source.
- Project files remain untracked; no commits have been made.

### UNVERIFIED
- Definitive child-process termination state after timeout, including zombie handling.
- Real GitHub authentication through the integrated client.
- End-to-end natural-language agent-to-MCP orchestration.
- External write protection and secret redaction under adversarial conditions.
- Independent review of benchmark labels and generalization beyond the current dataset.
- Complete roadmap checklist review.

### Next task
- Strengthen process-termination verification if needed, then review the benchmark labels and original roadmap checklist before moving on to authentication and end-to-end orchestration.

## 2026-10-11 — Benchmark Confidence and Validity Review

### Findings
- The local backend passes model-provided confidence and option probabilities into `DecisionResult`; this alone does not establish calibrated confidence.
- The 82% result (41/50) describes performance on the current synthetic, hand-labeled benchmark only.
- The evaluation runner measures exact choice-label agreement and estimates escalation from primary-backend confidence. It does not invoke the fallback or measure end-to-end task completion.
- Confidence thresholds remain provisional. No threshold or benchmark-label changes were made during this review.

### Open issues
- Independently review benchmark labels and rationales before using the score to compare model versions.
- Measure cold-start and steady-state latency separately.
- Evaluate confidence calibration and fallback behavior independently.
- Review the original roadmap checklist before declaring the October 10 checklist complete.

### UNVERIFIED
- Whether benchmark labels consistently represent intended real-world behavior.
- Whether model confidence predicts correctness on representative unseen tasks.
- End-to-end task success and fallback effectiveness.
- Completion of every October 10 roadmap item.

### Next task
- Locate and review the original roadmap checklist.
- Independently review ambiguous benchmark labels without changing them merely to improve accuracy.

## 2026-10-12 — Cost Guard Configuration

- Added `src/jarvis/config.py` with free-by-default validated cost mode.
- Added `tests/unit/test_config.py` for defaults, invalid values, and explicit production opt-in.
- Updated README with the enforcement limitation.
- UNVERIFIED: application startup/provider-selection integration, paid-provider blocking, and completion of the roadmap checklist.
- Next: run full tests and wire `load_config()` into the real startup path.

## 2026-10-12 — CLI Startup and Cost-Guard Integration

- Added `src/jarvis/cli.py`; configuration is validated before backend imports/initialization.
- Registered `jarvis-decider` CLI entry point in `pyproject.toml`.
- Added CLI tests for free defaults, production rejection, and explicit opt-in.
- CLI currently performs startup/configuration checks only; it does not execute a full agent task.
- UNVERIFIED: editable installation exposes the entry point until reinstalled; application-wide provider policy beyond this CLI; end-to-end orchestration; complete roadmap checklist.
- Next: run all checks, reinstall editable package if needed, then implement trace schema and the first end-to-end traced task.

## 2026-10-12 — JSONL Decision Trace Schema

- Added a versioned JSONL decision event recorder with timestamp, run/decision identifiers, backend, choice, confidence, threshold, latency, escalation, final source, and status.
- Added validation and tests for append behavior, invalid values, and omission of prompt/context and secret fields.
- This is a standalone recorder; it is not yet wired into `DecisionEngine` or the CLI.
- UNVERIFIED: integration into real decisions, end-to-end trace completeness, concurrent writer behavior, and roadmap checklist completion.
- Next: add an explicit trace integration layer around the engine and verify one decision creates a trace event without changing decision semantics.

## 2026-10-12 — Decision Engine Trace Wrapper

- Added a public threshold accessor to `DecisionEngine` so tracing can record the configured threshold without reaching into private state.
- Added `TracingDecisionEngine`, which records successful decision results through the JSONL recorder and returns the original `DecisionResult`.
- Added tests for unchanged decision semantics, trace metadata, prompt/context omission, and one-event-per-decision append behavior.
- Verification: `python -m pytest -q` — 167 passed in 1.00s; `python -m compileall -q src tests eval` passed; `git diff --check` passed.

### UNVERIFIED
- Exceptions currently propagate without an error trace.
- Fallback/escalation trace behavior, concurrent writers, and integration into the CLI or full agent orchestration.
- Real GitHub end-to-end task execution and complete roadmap checklist status.

### Next task
- Inspect the CLI and trace recorder, then add a harmless mock-only CLI command that writes one trace without paid APIs or GitHub writes.

## 2026-10-12 — Mock CLI Trace Integration

- Added `--demo-trace` and configurable `--trace-path` to the CLI.
- The demo is restricted to the mock backend and records one sample decision through `TracingDecisionEngine`.
- Added tests for JSONL trace output and rejection of the local model backend for this demo.
- Verification: 169 tests passed; compileall and `git diff --check` passed.
- Manual smoke test: `jarvis-decider --demo-trace --trace-path <temporary-file>` wrote a valid JSONL event with decision ID D1, backend mock, threshold 0.6, final choice inspect, and status success.

### UNVERIFIED
- Error and fallback/escalation trace coverage.
- Concurrent trace writes and trace retention/rotation.
- Full natural-language agent orchestration, integrated GitHub authentication, and end-to-end task completion.
- Complete roadmap checklist status.

### Next task
- Add tests for the engine fallback/escalation path and verify that the trace accurately reflects the final decision.

## 2026-10-12 — Fallback and Escalation Trace Tests

- Added a deterministic test backend to exercise low-confidence primary decisions and fallback selection.
- Verified the trace preserves primary choice/backend/confidence while recording the fallback final choice/source, `escalated=true`, and `status=escalated`.
- Verified exactly one primary and one fallback call occur, even when fallback confidence is below threshold; fallback confidence is not recursively evaluated.
- Verified missing fallback raises `EscalationUnavailableError` and does not write a misleading success trace.
- Verification: 171 tests passed in 0.93s; compileall and `git diff --check` passed.

### UNVERIFIED
- Error events are not yet recorded when the engine raises an exception.
- Concurrent trace writes and trace retention/rotation.
- Full natural-language agent orchestration, integrated GitHub authentication, and end-to-end task completion.
- Complete roadmap checklist status.

### Next task
- Review trace failure handling and add safe error-event recording without exposing question, context, or secrets; then review GitHub MCP integration and the roadmap checklist.


## 2026-10-13 — Sanitized Error Tracing and Integration Review

- Updated `TracingDecisionEngine` to record sanitized error events when decision execution raises an exception.
- Error events record the exception class only; prompts, private context, and raw exception messages are excluded.
- The original engine exception is re-raised even if writing the error event fails.
- Updated tests for missing-fallback errors and trace-storage failure handling.
- Verification: `python -m pytest -q` — 172 passed in 1.14s; `python -m compileall -q src tests eval` passed; `git diff --check` passed.
- Reviewed GitHub MCP restrictions, repository scoping, timeout handling, and registration through `ToolExecutor`.

### UNVERIFIED
- Integrated GitHub authentication and full end-to-end agent execution.
- Concurrent trace writes and trace retention/rotation.
- Independent review of benchmark labels, confidence calibration, and cold versus steady-state latency.
- Original roadmap checklist: PDF text extraction has not succeeded, so its full completion status remains unknown.
- Overall roadmap completion.

### Next task
- Extract and review `FinalAmazonPlan.pdf`, then map each checklist item to implementation and verification evidence before declaring any roadmap day complete.
# 2026-10-18 — Day 1 Local Decision Workflow

### Completed
- Inspected repository state at `cbdfc2d`; the working tree was clean before implementation.
- Confirmed the project virtual environment and ran the existing baseline suite: 234 passed.
- Added an application workflow that validates a structured request, resolves the selected existing backend, applies the existing one-step confidence escalation engine, validates the final choice, and returns a structured local task-routing outcome.
- Strengthened the engine to reject malformed backend results, out-of-set primary choices, and scores for options outside the request. Invalid primary output terminates safely without fallback or action execution.
- Added `jarvis-decider --run-demo`; default path uses only the deterministic mock backend and routes to one allowlisted destination (`research`, `developer`, or `documentation`).
- Bedrock construction is blocked in the application path without `COST_MODE=production` and `ALLOW_PAID=true`. No AWS request was made.
- Added focused workflow, backend selection, allowlist, escalation, and CLI tests.

### Verification
- Baseline: `./.venv/bin/python -m pytest -q` — 234 passed.
- Focused tests: `./.venv/bin/python -m pytest -q tests/unit/test_application.py tests/unit/test_cli.py tests/unit/test_engine.py` — exit 0, 76 passed.
- Full suite: `./.venv/bin/python -m pytest -q` — exit 0, 249 passed.
- Compilation: `./.venv/bin/python -m compileall -q src tests eval` — exit 0.
- Whitespace check: `git diff --check` — exit 0.
- Documented mock invocation: `./.venv/bin/jarvis-decider --run-demo` — exit 0; output reported `backend=mock`, `choice=research`, `escalated=false`, and `destination=research`.

### Limitations and Day 2
- No live Bedrock request has been verified. Configuration is not a substitute for AWS IAM or account controls.
- Synthetic evaluation does not establish real-world accuracy; model confidence is not automatically calibrated.
- The routing action only returns a structured local result and performs no task execution.
- Day 1 does not claim submission readiness. Day 2: review dataset labels and confidence policy, improve observability/redaction, and plan separately authorized provider validation.
