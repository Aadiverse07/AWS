"""Offline evaluation runner for Jarvis Decider."""

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "eval/datasets/tasks_v1.jsonl"
DEFAULT_THRESHOLDS = ROOT / "configs/thresholds.yaml"


def load_tasks(path: Path) -> list[dict[str, Any]]:
    """Load and validate the JSONL evaluation dataset."""
    tasks = []
    required = {
        "task_id", "decision_id", "category", "question",
        "context", "options", "expected_choice", "rationale",
    }
    seen_ids = set()

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue

        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON on line {line_number}: {exc}"
            ) from exc

        if not isinstance(task, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object.")

        missing = required - task.keys()
        if missing:
            raise ValueError(
                f"Line {line_number} is missing fields: {sorted(missing)}"
            )

        task_id = task["task_id"]
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(f"Line {line_number} has an invalid task_id.")
        if task_id in seen_ids:
            raise ValueError(f"Duplicate task_id: {task_id}")
        seen_ids.add(task_id)

        for field in ("decision_id", "category", "question", "rationale"):
            if not isinstance(task[field], str) or not task[field].strip():
                raise ValueError(
                    f"Task {task_id}: {field} must be a nonblank string."
                )

        if not isinstance(task["context"], str):
            raise ValueError(f"Task {task_id}: context must be a string.")

        options = task["options"]
        if (
            not isinstance(options, list)
            or len(options) < 2
            or any(not isinstance(option, str) or not option.strip()
                   for option in options)
            or len(set(options)) != len(options)
        ):
            raise ValueError(f"Task {task_id}: invalid options list.")

        if task["expected_choice"] not in options:
            raise ValueError(
                f"Task {task_id}: expected_choice is not one of its options."
            )

        tasks.append(task)

    if not tasks:
        raise ValueError("The evaluation dataset is empty.")

    return tasks


def load_thresholds(path: Path) -> dict[str, float]:
    """Load and validate provisional confidence thresholds."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict) or not data:
        raise ValueError("Threshold configuration must be a nonempty mapping.")

    thresholds = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Threshold IDs must be nonblank strings.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Threshold {key!r} must be numeric.")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Threshold {key!r} must be between 0 and 1.")
        thresholds[key.strip()] = float(value)

    return thresholds


def percentile(values: list[float], percentage: float) -> float | None:
    """Calculate the nearest-rank percentile: sorted[ceil(p*n)-1]."""
    if (
        isinstance(percentage, bool)
        or not isinstance(percentage, (int, float))
        or not math.isfinite(percentage)
        or not 0 <= percentage <= 100
    ):
        raise ValueError("percentage must be a finite number from 0 to 100")
    if not values:
        return None
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("percentile values must be finite numbers")
    ordered = sorted(values)
    rank = max(1, math.ceil((percentage / 100) * len(ordered)))
    return round(ordered[rank - 1], 3)


def evaluate(
    tasks: list[dict[str, Any]],
    backend: Any,
    thresholds: dict[str, float],
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    """Evaluate primary choices; count all runner failures as incorrect.

    Timing covers only ``backend.decide`` and uses a monotonic clock. Lazy
    initialization performed inside that call is included in its first sample.
    The evaluator never constructs or invokes a fallback backend.
    """
    from jarvis.decision.contract import DecisionRequest, DecisionResult

    if not tasks:
        raise ValueError("Cannot evaluate an empty task list.")

    unknown_ids = sorted({
        task["decision_id"] for task in tasks
        if task["decision_id"] not in thresholds
    })
    if unknown_ids:
        raise ValueError(f"Missing thresholds for decision IDs: {unknown_ids}")

    records = []
    latencies = []
    category_totals = Counter()
    category_correct = Counter()
    category_successful = Counter()
    correct = 0
    successful = 0
    would_escalate = 0

    validation_failures: Counter[str] = Counter()
    for index, task in enumerate(tasks):
        category_totals[task["category"]] += 1
        try:
            request = DecisionRequest(
                decision_id=task["decision_id"],
                question=task["question"],
                context=task["context"],
                options=task["options"],
                run_id="eval-v1",
                step=index,
            )
        except Exception as exc:
            validation_failures["invalid_request"] += 1
            records.append({
                "task_id": task["task_id"],
                "category": task["category"],
                "expected_choice": task["expected_choice"],
                "primary_choice": None,
                "correct": False,
                "confidence": None,
                "threshold": thresholds[task["decision_id"]],
                "would_escalate": None,
                "escalation_reason": None,
                "latency_ms": None,
                "error_category": "invalid_request",
                "error": type(exc).__name__,
            })
            continue

        started = time.perf_counter()
        try:
            raw_result = backend.decide(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            validation_failures["backend_error"] += 1
            records.append({
                "task_id": task["task_id"],
                "category": task["category"],
                "expected_choice": task["expected_choice"],
                "primary_choice": None,
                "correct": False,
                "confidence": None,
                "threshold": thresholds[task["decision_id"]],
                "would_escalate": None,
                "escalation_reason": None,
                "latency_ms": round(elapsed_ms, 3),
                "error_category": "backend_error",
                "error": type(exc).__name__,
            })
            continue

        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            if not isinstance(raw_result, DecisionResult):
                raise TypeError("result is not a DecisionResult")
            result = DecisionResult.model_validate(raw_result.model_dump(mode="python"))
            if result.chosen not in task["options"]:
                raise ValueError("choice_outside_options")
            if not set(result.scores).issubset(task["options"]):
                raise ValueError("scores_outside_options")
        except Exception as exc:
            latencies.append(elapsed_ms)
            validation_failures["invalid_output"] += 1
            records.append({
                "task_id": task["task_id"],
                "category": task["category"],
                "expected_choice": task["expected_choice"],
                "primary_choice": None,
                "correct": False,
                "confidence": None,
                "threshold": thresholds[task["decision_id"]],
                "would_escalate": None,
                "escalation_reason": None,
                "latency_ms": round(elapsed_ms, 3),
                "error_category": "invalid_output",
                "error": type(exc).__name__,
            })
            continue

        is_correct = result.chosen == task["expected_choice"]
        reason = (
            "confidence_unavailable"
            if result.confidence is None
            else "below_threshold"
            if result.confidence < thresholds[task["decision_id"]]
            else None
        )
        should_escalate = reason is not None
        successful += 1
        category_successful[task["category"]] += 1
        correct += int(is_correct)
        category_correct[task["category"]] += int(is_correct)
        would_escalate += int(should_escalate)
        latencies.append(elapsed_ms)
        records.append({
            "task_id": task["task_id"],
            "category": task["category"],
            "expected_choice": task["expected_choice"],
            "primary_choice": result.chosen,
            "correct": is_correct,
            "confidence": result.confidence,
            "threshold": thresholds[task["decision_id"]],
            "would_escalate": should_escalate,
            "escalation_reason": reason,
            "latency_ms": round(elapsed_ms, 3),
            "backend_reported_latency_ms": result.latency_ms,
            "error_category": None,
            "error": None,
        })

    total = len(tasks)
    errors = sum(record["error"] is not None for record in records)

    by_category = {}
    for category, count in sorted(category_totals.items()):
        category_ok = category_correct[category]
        category_run = category_successful[category]
        by_category[category] = {
            "total": count,
            "successful_decisions": category_run,
            "errors": count - category_run,
            "correct": category_ok,
            "accuracy_over_all_tasks": round(category_ok / count, 4),
            "accuracy_on_successful_decisions": (
                round(category_ok / category_run, 4)
                if category_run else None
            ),
        }

    return {
        "benchmark": "Jarvis Decider synthetic prototype v1",
        "backend": backend.name,
        "dataset": str(dataset_path),
        "total_tasks": total,
        "successful_decisions": successful,
        "errors": errors,
        "correct": correct,
        "incorrect": total - correct,
        "accounting": {
            "successful_plus_errors": successful + errors,
            "correct_plus_incorrect": correct + total - correct,
            "denominator": "all dataset cases, including errors",
        },
        "validation_failures": dict(sorted(validation_failures.items())),
        "actual_fallback_invocations": 0,
        "accuracy_over_all_tasks": round(correct / total, 4),
        "accuracy_on_successful_decisions": (
            round(correct / successful, 4) if successful else None
        ),
        "escalation_policy": {
            "meaning": "Would escalate based on primary confidence; no fallback invoked.",
            "would_escalate": would_escalate,
            "rate_over_all_tasks": round(would_escalate / total, 4),
        },
        "latency_ms": {
            "measurement": (
                "Monotonic elapsed time around backend.decide only; lazy "
                "backend initialization inside the call is included"
            ),
            "percentile_convention": "Nearest rank: sorted[ceil(p*n)-1]",
            "observation_count": len(latencies),
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        "by_category": by_category,
        "records": records,
    }


def write_report(report: dict[str, Any], output_path: Path,
                 protected_paths: tuple[Path, ...] = ()) -> None:
    """Write a new JSON report without replacing existing or input files."""
    output_resolved = output_path.resolve()
    if any(output_resolved == protected.resolve() for protected in protected_paths):
        raise ValueError("Report output path must not overwrite an input file.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves prior user data on repeated invocations.
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=("mock", "local-hf"), default="mock"
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument(
        "--output", type=Path,
        help="Optional path to save the full JSON report.",
    )
    args = parser.parse_args()

    tasks = load_tasks(args.dataset)
    thresholds = load_thresholds(args.thresholds)

    if args.backend == "mock":
        from jarvis.decision.backends.mock import MockBackend
        backend = MockBackend()
    else:
        from jarvis.decision.backends.local_hf import LocalHFBackend
        backend = LocalHFBackend()

    report = evaluate(tasks, backend, thresholds, args.dataset)

    summary = {key: value for key, value in report.items() if key != "records"}
    print(json.dumps(summary, indent=2))

    if args.output:
        try:
            write_report(
                report,
                args.output,
                protected_paths=(args.dataset, args.thresholds),
            )
        except (OSError, ValueError) as exc:
            parser.error(f"cannot write report: {type(exc).__name__}: {exc}")
        print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
