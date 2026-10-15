from __future__ import annotations
import argparse
import sys
from jarvis.config import ConfigurationError, load_config

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Decider local CLI")
    parser.add_argument("--check-config", action="store_true", help="validate config and exit")
    parser.add_argument("--backend", choices=("mock", "local_hf", "bedrock"), default="mock", help="free local backend (default: mock)")
    parser.add_argument("--demo-trace", action="store_true", help="run one safe mock decision and record a JSONL trace")
    parser.add_argument("--trace-path", default="traces/decisions.jsonl", help="JSONL output path for --demo-trace")
    args = parser.parse_args(argv)
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
    if args.backend == "mock":
        from jarvis.decision.backends.mock import MockBackend
        backend = MockBackend()
    elif args.backend == "local_hf":
        from jarvis.decision.backends.local_hf import LocalHFBackend
        backend = LocalHFBackend()
    else:
        from jarvis.decision.backends.bedrock import BedrockBackend
        backend = BedrockBackend()
    print(f"Jarvis Decider ready: backend={backend.name}; cost_mode={config.cost_mode}")
    print("No task was executed. Use the Python DecisionEngine API to submit a decision request.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
