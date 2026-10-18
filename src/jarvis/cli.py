from __future__ import annotations
import argparse
import sys
from jarvis.config import ConfigurationError, load_config

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Decider local CLI")
    parser.add_argument("--check-config", action="store_true", help="validate config and exit")
    parser.add_argument("--backend", choices=("mock", "local_hf", "bedrock"), default="mock", help="free local backend (default: mock)")
    parser.add_argument("--run-demo", action="store_true", help="run a decision and the safe local task-routing action")
    parser.add_argument("--record-trace", action="store_true", help="record a sanitized trace for --run-demo")
    parser.add_argument("--demo-trace", action="store_true", help="run one safe mock decision and record a JSONL trace")
    parser.add_argument("--trace-path", default="traces/decisions.jsonl", help="JSONL output path for --demo-trace")
    args = parser.parse_args(argv)
    if args.record_trace and not args.run_demo:
        parser.error("--record-trace requires --run-demo")
    try:
        config = load_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.check_config:
        print(f"Configuration valid: COST_MODE={config.cost_mode}; ALLOW_PAID={str(config.allow_paid).lower()}")
        return 0
    if args.backend == "bedrock" and not (
        config.cost_mode == "production" and config.allow_paid
    ):
        print(
            "Configuration error: the Bedrock backend requires "
            "COST_MODE=production and ALLOW_PAID=true",
            file=sys.stderr,
        )
        return 2
    if args.run_demo:
        try:
            from jarvis.application import run_default_demo

            outcome = run_default_demo(
                args.backend,
                trace_path=args.trace_path if args.record_trace else None,
            )
        except ConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            # Show controlled error details without a traceback (which could
            # include request/provider internals); never present failure as success.
            detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            print(f"Workflow error: {detail}", file=sys.stderr)
            return 1
        print(
            f"Decision complete: backend={outcome.primary_backend}; "
            f"choice={outcome.selected}; escalated={str(outcome.escalated).lower()}; "
            f"source={outcome.final_source}; action={outcome.action.action}; "
            f"destination={outcome.action.destination}"
        )
        return 0
    if args.demo_trace:
        if args.backend != "mock":
            print("Configuration error: --demo-trace requires --backend mock", file=sys.stderr)
            return 2
        from uuid import uuid4
        from jarvis.decision.backends.mock import MockBackend
        from jarvis.decision.contract import DecisionRequest
        from jarvis.decision.engine import DecisionEngine
        from jarvis.observability.trace import JSONLTraceRecorder
        from jarvis.observability.traced_engine import TracingDecisionEngine
        backend = MockBackend()
        engine = TracingDecisionEngine(DecisionEngine(backend, {"D1": 0.6}), JSONLTraceRecorder(args.trace_path))
        request = DecisionRequest(decision_id="D1", question="Choose a safe next step", context="", options=["inspect", "escalate"], run_id=uuid4().hex, step=0)
        result = engine.decide(request)
        print(f"Mock decision recorded: choice={result.final_choice or result.chosen}; trace={args.trace_path}")
        return 0
    try:
        from jarvis.application import build_backend

        backend = build_backend(args.backend, config)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    print(f"Jarvis Decider ready: backend={backend.name}; cost_mode={config.cost_mode}")
    print("No task was executed. Use the Python DecisionEngine API to submit a decision request.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
