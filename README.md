# Jarvis Decider

A decision-first agent runtime for Jarvis.

The core idea is to use a small decision model for narrow choices and
escalate to a larger language model only when necessary.

## Current Status

Phase 1: Decision Core

- Project skeleton: initialized
- Strands Decider feasibility: verified locally
- Decision contract: implemented
- Mock backend: implemented and tested
- Local Strands Decider backend: implemented and verified with one real inference
- Unit tests: 21 passing
- Decision engine and confidence-based escalation: next
- Evaluation: upcoming

## Cost mode and provider safety

The configuration module defaults to `COST_MODE=free`. `COST_MODE=production` is rejected unless `ALLOW_PAID=true` is explicitly set. `ALLOW_PAID` accepts only `true` or `false`, case-insensitively. Do not commit API keys.

**Enforcement limitation:** this module validates configuration only when loaded. Application-wide enforcement is not active until the actual application startup and provider-selection path calls `load_config()` and honors the result. Do not claim paid-provider blocking is enforced before that integration is implemented and tested.

## Local CLI

After installing the project in the active virtual environment, run `jarvis-decider --check-config` to validate environment configuration. `jarvis-decider` starts in mock mode by default; `jarvis-decider --backend local_hf` selects the local Strands Decider backend. The current CLI is a bootstrap/configuration check, not yet an end-to-end agent task runner.
