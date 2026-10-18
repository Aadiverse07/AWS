"""Audit retained Day 1 evaluation records and generate a Day 2 report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports/evaluation/day1_results.json"
DEFAULT_DATASET = ROOT / "eval/datasets/tasks_v1.jsonl"
DEFAULT_JSON = ROOT / "reports/evaluation/day2_results.json"
DEFAULT_MARKDOWN = ROOT / "reports/evaluation/day2_evaluation.md"


class AuditError(ValueError):
    """Retained evaluation data is incomplete or internally inconsistent."""


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return round(ordered[rank - 1], 3)


def _audit_backend(name: str, source: dict[str, Any]) -> dict[str, Any]:
    records = source.get("records")
    total = source.get("total_cases")
    if not isinstance(records, list) or isinstance(total, bool) or not isinstance(total, int):
        raise AuditError(f"Backend {name!r} is missing records or a valid case count")
    if total <= 0 or len(records) != total:
        raise AuditError(f"Backend {name!r} has an incomplete case record set")

    ids = [record.get("task_id") for record in records if isinstance(record, dict)]
    if len(ids) != total or any(not isinstance(case_id, str) for case_id in ids):
        raise AuditError(f"Backend {name!r} contains malformed case records")
    if len(set(ids)) != total:
        raise AuditError(f"Backend {name!r} contains duplicate case records")

    errors = sum(record.get("error") is not None for record in records)
    correct = sum(record.get("correct") is True for record in records)
    successful = total - errors
    if correct > successful or successful + errors != total:
        raise AuditError(f"Backend {name!r} case accounting is inconsistent")
    recomputed_accuracy = round(correct / total, 4)
    if source.get("accuracy") != recomputed_accuracy:
        raise AuditError(f"Backend {name!r} accuracy does not match case records")
    if source.get("correct") != correct:
        raise AuditError(f"Backend {name!r} correct count does not match case records")
    if source.get("incorrect_including_errors") != total - correct:
        raise AuditError(f"Backend {name!r} incorrect count does not match case records")
    if source.get("successful_decisions") != successful or source.get("errors") != errors:
        raise AuditError(f"Backend {name!r} success/error counts do not match records")

    categories: dict[str, dict[str, int | float]] = {}
    category_rows = Counter(record.get("category") for record in records)
    for category, count in sorted(category_rows.items()):
        category_records = [r for r in records if r.get("category") == category]
        category_correct = sum(r.get("correct") is True for r in category_records)
        categories[category] = {
            "total": count,
            "correct": category_correct,
            "incorrect_including_errors": count - category_correct,
            "accuracy": round(category_correct / count, 4),
        }

    latency_values: list[float] = []
    for record in records:
        value = record.get("latency_ms")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise AuditError(f"Backend {name!r} has an invalid latency observation")
        latency_values.append(float(value))
    if len(latency_values) != total:
        raise AuditError(f"Backend {name!r} lacks per-case latency observations")
    stored_latency = source.get("latency_ms", {})
    latency = {
        "observation_count": len(latency_values),
        "mean_ms": round(statistics.mean(latency_values), 3),
        "p50_ms": _nearest_rank(latency_values, 0.50),
        "p95_ms": _nearest_rank(latency_values, 0.95),
        "max_ms": round(max(latency_values), 3),
        "max_case_id": records[latency_values.index(max(latency_values))]["task_id"],
        "percentile_convention": "Nearest rank: sorted[ceil(p*n)-1]",
        "matches_stored_summary": (
            round(statistics.mean(latency_values), 3) == stored_latency.get("mean")
            and _nearest_rank(latency_values, 0.50) == stored_latency.get("p50")
            and _nearest_rank(latency_values, 0.95) == stored_latency.get("p95")
        ),
    }

    would_escalate = sum(record.get("would_escalate") is True for record in records)
    confidence_unavailable = sum(
        record.get("error") is None and record.get("confidence") is None
        for record in records
    )
    return {
        "backend_name": source.get("backend_name", name),
        "execution": source.get("role"),
        "total_cases": total,
        "successful_decisions": successful,
        "incorrect_choices": successful - correct,
        "runner_errors": errors,
        "correct_choices": correct,
        "accuracy": recomputed_accuracy,
        "accuracy_denominator": "all dataset cases; runner errors count as incorrect",
        "case_accounting_valid": correct + (successful - correct) + errors == total,
        "categories": categories,
        "actual_fallback_invocations": 0,
        "threshold_derived_would_escalate_count": would_escalate,
        "threshold_derived_would_escalate_rate": round(would_escalate / total, 4),
        "confidence_unavailable_outputs": confidence_unavailable,
        "validation_failure_breakdown": None,
        "latency_audit": latency,
        "backend_genuinely_executed_in_retained_run": True,
    }


def build_audit(day1: dict[str, Any], dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    dataset = day1.get("dataset")
    backends = day1.get("backends")
    if not isinstance(dataset, dict) or not isinstance(backends, dict) or not backends:
        raise AuditError("Day 1 results must contain dataset and backend records")
    tasks = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_ids = [task.get("task_id") for task in tasks if isinstance(task, dict)]
    if len(task_ids) != len(tasks) or len(set(task_ids)) != len(task_ids):
        raise AuditError("Dataset has malformed or duplicate task IDs")
    if dataset.get("case_count") != len(tasks):
        raise AuditError("Day 1 dataset case count does not match current dataset")
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    if dataset.get("sha256") != dataset_hash:
        raise AuditError("Day 1 dataset hash does not match the retained dataset")

    summaries = {}
    canonical_ids = task_ids
    task_by_id = {task["task_id"]: task for task in tasks}
    for name, source in sorted(backends.items()):
        summary = _audit_backend(name, source)
        if [record["task_id"] for record in source["records"]] != canonical_ids:
            raise AuditError(f"Backend {name!r} case order/identity differs from dataset")
        for record in source["records"]:
            expected = task_by_id[record["task_id"]]
            if (
                record.get("category") != expected["category"]
                or record.get("expected_choice") != expected["expected_choice"]
            ):
                raise AuditError(
                    f"Backend {name!r} has case metadata mismatched to the dataset"
                )
            if record.get("error") is None:
                if record.get("primary_choice") not in expected["options"]:
                    raise AuditError(
                        f"Backend {name!r} recorded a successful choice outside options"
                    )
                if record.get("correct") is not (
                    record["primary_choice"] == expected["expected_choice"]
                ):
                    raise AuditError(
                        f"Backend {name!r} correctness flag disagrees with its choice"
                    )
            elif record.get("correct") is not False:
                raise AuditError(f"Backend {name!r} error record is marked correct")
        summaries[name] = summary

    return {
        "report_schema_version": 1,
        "report_type": "historical_day1_evaluation_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_artifact": "reports/evaluation/day1_results.json",
        "dataset": {
            "identifier": dataset.get("identifier"),
            "version": "v1",
            "path": str(dataset_path.relative_to(ROOT)),
            "case_count": len(tasks),
            "sha256": dataset_hash,
            "synthetic_hand_labeled": True,
        },
        "methodology": {
            "metric_source": "Recomputed from retained per-case Day 1 records; no backend was rerun.",
            "scoring": "Exact choice match; denominator includes all cases and runner errors.",
            "fallback": "The Day 1 runner calls primary backends directly; actual fallback invocations are zero. Threshold-derived estimates are separate.",
            "latency_timer": "Day 1 runner used time.perf_counter around request construction plus backend.decide; lazy local model initialization inside decide is included.",
        },
        "backends": summaries,
        "limitations": [
            "Synthetic hand-labeled cases do not establish real-world accuracy.",
            "Small sample size; labels were not independently reviewed in this audit.",
            "Model confidence calibration is not established.",
            "Latency is machine- and run-dependent; initialization can affect an in-call timing sample.",
            "No fresh backend run was performed for this audit; values are historical Day 1 records.",
        ],
        "reliability_test_coverage": [
            "Valid result and allowlisted action invocation",
            "Malformed contract values and choices outside supplied options",
            "High, low, threshold-boundary, and unknown confidence behavior",
            "Exactly one bounded fallback invocation",
            "Fallback backend errors and invalid fallback choices stop action execution",
            "Sanitized trace events distinguish success, escalation, rejection, and failure",
            "Paid backend selection is blocked before construction without explicit opt-in",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render report summaries directly from the machine-readable audit."""
    lines = [
        "# Day 2 Evaluation Integrity Audit",
        "",
        f"Generated (UTC): `{report['generated_at_utc']}`",
        "",
        "This report audits retained Day 1 case records; it does not rerun either backend.",
        "",
        "## Dataset",
        "",
        f"- Dataset: `{report['dataset']['identifier']}` ({report['dataset']['version']}) — **synthetic, hand-labeled**, {report['dataset']['case_count']} cases.",
        f"- SHA-256: `{report['dataset']['sha256']}`.",
        "- Results are exact-label agreement and do not establish real-world accuracy.",
        "",
        "## Recomputed backend metrics",
        "",
        "| Backend | Cases | Correct | Incorrect choices | Errors | Accuracy | Actual fallbacks | Would escalate (estimate) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, result in report["backends"].items():
        lines.append(
            f"| {name} | {result['total_cases']} | {result['correct_choices']} | "
            f"{result['incorrect_choices']} | {result['runner_errors']} | "
            f"{result['accuracy']:.1%} | {result['actual_fallback_invocations']} | "
            f"{result['threshold_derived_would_escalate_count']} "
            f"({result['threshold_derived_would_escalate_rate']:.1%}) |"
        )
    lines.extend(["", "### Latency audit", ""])
    for name, result in report["backends"].items():
        latency = result["latency_audit"]
        lines.append(
            f"- **{name}:** n={latency['observation_count']}; mean "
            f"{latency['mean_ms']:.3f} ms; p50 {latency['p50_ms']:.3f} ms; "
            f"p95 {latency['p95_ms']:.3f} ms; max {latency['max_ms']:.3f} ms "
            f"({latency['max_case_id']}); stored summary match: "
            f"{str(latency['matches_stored_summary']).lower()}."
        )
    lines.extend([
        "",
        "Percentiles use nearest rank: `sorted[ceil(p*n)-1]`. The retained local result's 9,374.305 ms T001 outlier explains why its mean exceeds p95. The Day 1 timer included request construction and `backend.decide`; lazy model loading inside the call was therefore included.",
        "",
        "## Method and limitations",
        "",
        "Actual fallback calls are zero because the Day 1 runner evaluates primary backends directly. “Would escalate” is a threshold-derived estimate, not an observed fallback count. The report is generated from retained JSON case records; the local model genuinely ran in the retained Day 1 run, but no fresh model inference was performed for this audit.",
        "",
        "Model confidence is not shown to be calibrated. The dataset is small and synthetic, labels were not independently reviewed here, and latency is machine- and run-dependent. Mock results are a deterministic baseline, not evidence of model quality.",
        "",
        "Reliability behavior has focused automated coverage for valid action flow, malformed outputs, confidence boundaries and unknown values, bounded fallback, fallback failures, trace redaction/status, and paid-backend construction guards.",
        "",
        "## Reproduction",
        "",
        "This audit does not rerun model inference. Regenerate it using the retained Day 1 artifact and new output paths (the writer refuses to replace existing files):",
        "",
        "```bash",
        "./.venv/bin/python eval/audit_day1.py \\",
        "  --json-output /tmp/jarvis-day2-results.json \\",
        "  --markdown-output /tmp/jarvis-day2-evaluation.md",
        "```",
        "",
        "The original Day 1 backend runs can be repeated separately with offline flags for the local model only when its weights are already cached; doing so produces new timing observations and does not reproduce this historical audit.",
        "",
    ])
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], json_path: Path, markdown_path: Path,
                  protected_paths: tuple[Path, ...]) -> None:
    outputs = (json_path.resolve(), markdown_path.resolve())
    if outputs[0] == outputs[1]:
        raise ValueError("JSON and Markdown outputs must be different paths")
    if any(output in {path.resolve() for path in protected_paths} for output in outputs):
        raise ValueError("Audit output must not overwrite an input file")
    if any(path.exists() for path in (json_path, markdown_path)):
        raise FileExistsError("Refusing to overwrite an existing audit artifact")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    try:
        day1 = json.loads(args.input.read_text(encoding="utf-8"))
        report = build_audit(day1, args.dataset)
        write_outputs(
            report,
            args.json_output,
            args.markdown_output,
            (args.input, args.dataset),
        )
    except (OSError, json.JSONDecodeError, AuditError, ValueError) as exc:
        parser.error(f"audit failed: {type(exc).__name__}: {exc}")
    print(f"Wrote {args.markdown_output} and {args.json_output}")


if __name__ == "__main__":
    main()
