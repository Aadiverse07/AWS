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
    """Calculate a nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((percentage / 100) * len(ordered)))
    return round(ordered[rank - 1], 3)


def evaluate(
    tasks: list[dict[str, Any]],
    backend: Any,
    thresholds: dict[str, float],
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    """Evaluate primary backend choices; do not invoke a fallback."""
    from jarvis.decision.contract import DecisionRequest

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

    for index, task in enumerate(tasks):
        category_totals[task["category"]] += 1
        started = time.perf_counter()

        try:
            request = DecisionRequest(
                decision_id=task["decision_id"],
                question=task["question"],
                context=task["context"],
                options=task["options"],
                run_id="eval-v1",
                step=index,
            )
            result = backend.decide(request)
            elapsed_ms = (time.perf_counter() - started) * 1000

            if result.chosen not in task["options"]:
                raise ValueError(
                    f"Backend selected an option not supplied: {result.chosen!r}"
                )

            is_correct = result.chosen == task["expected_choice"]
            should_escalate = (
                result.confidence < thresholds[task["decision_id"]]
            )
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
                "latency_ms": round(elapsed_ms, 3),
                "backend_reported_latency_ms": result.latency_ms,
                "error": None,
            })

        except Exception as exc:
            records.append({
                "task_id": task["task_id"],
                "category": task["category"],
                "expected_choice": task["expected_choice"],
                "primary_choice": None,
                "correct": False,
                "confidence": None,
                "threshold": thresholds[task["decision_id"]],
                "would_escalate": None,
                "latency_ms": round(
                    (time.perf_counter() - started) * 1000, 3
                ),
                "error": f"{type(exc).__name__}: {exc}",
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
            "measurement": "Wall-clock time around backend.decide",
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        "by_category": by_category,
        "records": records,
    }


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
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
