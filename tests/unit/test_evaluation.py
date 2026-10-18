import json
from pathlib import Path

import pytest
import yaml

from jarvis.decision.contract import DecisionResult
from eval.run_eval import evaluate, load_tasks, load_thresholds, percentile, write_report


def task(
    task_id="task-1",
    expected_choice="yes",
    decision_id="D1",
    options=None,
):
    return {
        "task_id": task_id,
        "decision_id": decision_id,
        "category": "test",
        "question": "Choose an option",
        "context": "",
        "options": options or ["yes", "no"],
        "expected_choice": expected_choice,
        "rationale": "Test rationale",
    }


def write_jsonl(path: Path, tasks):
    path.write_text(
        "".join(json.dumps(item) + "\n" for item in tasks),
        encoding="utf-8",
    )
    return path


def write_yaml(path: Path, data):
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class FixedBackend:
    name = "fixed"

    def __init__(self, chosen="yes", confidence=0.9, error=None, result=None):
        self.chosen = chosen
        self.confidence = confidence
        self.error = error
        self.result = result

    def decide(self, request):
        if self.error:
            raise self.error
        if self.result is not None:
            return self.result
        return DecisionResult(
            chosen=self.chosen,
            scores={option: 1.0 if option == self.chosen else 0.0
                    for option in request.options},
            confidence=self.confidence,
            latency_ms=1.0,
            backend=self.name,
        )


def test_load_tasks_accepts_valid_dataset(tmp_path):
    path = write_jsonl(tmp_path / "tasks.jsonl", [task()])
    loaded = load_tasks(path)
    assert len(loaded) == 1
    assert loaded[0]["task_id"] == "task-1"


def test_load_tasks_rejects_duplicate_ids(tmp_path):
    path = write_jsonl(tmp_path / "tasks.jsonl", [task(), task()])
    with pytest.raises(ValueError, match="Duplicate task_id"):
        load_tasks(path)


def test_load_tasks_rejects_expected_choice_not_in_options(tmp_path):
    bad = task(expected_choice="maybe")
    path = write_jsonl(tmp_path / "tasks.jsonl", [bad])
    with pytest.raises(ValueError, match="expected_choice"):
        load_tasks(path)


def test_load_tasks_rejects_invalid_json(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_tasks(path)


def test_load_tasks_rejects_missing_fields(tmp_path):
    item = task()
    del item["rationale"]
    path = write_jsonl(tmp_path / "tasks.jsonl", [item])
    with pytest.raises(ValueError, match="missing fields"):
        load_tasks(path)


def test_load_tasks_rejects_non_object_record(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text("42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_tasks(path)


def test_load_tasks_rejects_empty_dataset(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_tasks(path)


def test_load_thresholds_accepts_valid_values(tmp_path):
    path = write_yaml(tmp_path / "thresholds.yaml", {"D1": 0.6, "D2": 1})
    assert load_thresholds(path) == {"D1": 0.6, "D2": 1.0}


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "0.5", float("nan")])
def test_load_thresholds_rejects_invalid_values(tmp_path, value):
    path = write_yaml(tmp_path / "thresholds.yaml", {"D1": value})
    with pytest.raises(ValueError):
        load_thresholds(path)


def test_percentile_uses_nearest_rank():
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 95) is None


@pytest.mark.parametrize("percentage", [-1, 101, float("nan"), True])
def test_percentile_rejects_invalid_percentage(percentage):
    with pytest.raises(ValueError, match="percentage"):
        percentile([1.0, 2.0], percentage)


@pytest.mark.parametrize("values", [[float("nan")], [True], ["1"]])
def test_percentile_rejects_invalid_observations(values):
    with pytest.raises(ValueError, match="finite numbers"):
        percentile(values, 50)


def test_evaluate_calculates_accuracy_and_escalation():
    tasks = [
        task(task_id="one", expected_choice="yes"),
        task(task_id="two", expected_choice="no"),
    ]
    report = evaluate(
        tasks,
        FixedBackend(chosen="yes", confidence=0.4),
        {"D1": 0.6},
    )

    assert report["total_tasks"] == 2
    assert report["successful_decisions"] == 2
    assert report["errors"] == 0
    assert report["correct"] == 1
    assert report["accuracy_over_all_tasks"] == 0.5
    assert report["escalation_policy"]["would_escalate"] == 2
    assert report["escalation_policy"]["rate_over_all_tasks"] == 1.0
    assert report["by_category"]["test"]["correct"] == 1
    assert report["incorrect"] == 1
    assert report["accounting"]["successful_plus_errors"] == 2
    assert report["accounting"]["correct_plus_incorrect"] == 2
    assert report["actual_fallback_invocations"] == 0


def test_evaluate_rejects_empty_cases_without_division_error():
    with pytest.raises(ValueError, match="empty task list"):
        evaluate([], FixedBackend(), {"D1": 0.6})


def test_unknown_confidence_is_valid_and_counted_as_would_escalate():
    result = DecisionResult(
        chosen="yes", scores={}, confidence=None, latency_ms=1.0, backend="fixed"
    )
    report = evaluate([task()], FixedBackend(result=result), {"D1": 0.6})
    record = report["records"][0]
    assert report["successful_decisions"] == 1
    assert report["errors"] == 0
    assert report["escalation_policy"]["would_escalate"] == 1
    assert record["would_escalate"] is True
    assert record["escalation_reason"] == "confidence_unavailable"


@pytest.mark.parametrize(
    ("result", "category"),
    [
        ({"chosen": "yes"}, "invalid_output"),
        (
            DecisionResult(
                chosen="outside", scores={}, confidence=0.9,
                latency_ms=1.0, backend="fixed"
            ),
            "invalid_output",
        ),
    ],
)
def test_invalid_backend_output_counts_as_error(result, category):
    report = evaluate([task()], FixedBackend(result=result), {"D1": 0.6})
    assert report["successful_decisions"] == 0
    assert report["errors"] == 1
    assert report["correct"] == 0
    assert report["incorrect"] == report["total_tasks"] == 1
    assert report["validation_failures"] == {category: 1}
    assert report["records"][0]["error_category"] == category


def test_evaluate_records_backend_errors():
    report = evaluate(
        [task()],
        FixedBackend(error=RuntimeError("backend unavailable")),
        {"D1": 0.6},
    )

    assert report["total_tasks"] == 1
    assert report["successful_decisions"] == 0
    assert report["errors"] == 1
    assert report["correct"] == 0
    assert "RuntimeError" in report["records"][0]["error"]
    assert report["records"][0]["error_category"] == "backend_error"
    assert report["latency_ms"]["observation_count"] == 1
    assert report["latency_ms"]["observation_count"] == 1


def test_evaluation_error_record_omits_exception_message():
    report = evaluate(
        [task()],
        FixedBackend(error=RuntimeError("Authorization: Bearer do-not-log")),
        {"D1": 0.6},
    )
    record = report["records"][0]
    assert record["error"] == "RuntimeError"
    assert "do-not-log" not in json.dumps(record)


def test_evaluate_rejects_missing_threshold():
    with pytest.raises(ValueError, match="Missing thresholds"):
        evaluate([task()], FixedBackend(), {})


def test_evaluate_records_actual_dataset_path(tmp_path):
    dataset = tmp_path / "custom.jsonl"
    report = evaluate(
        [task()],
        FixedBackend(),
        {"D1": 0.6},
        dataset_path=dataset,
    )
    assert report["dataset"] == str(dataset)


def test_write_report_refuses_input_path_and_existing_file(tmp_path):
    source = tmp_path / "input.jsonl"
    source.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="input file"):
        write_report({"ok": True}, source, protected_paths=(source,))
    assert source.read_text(encoding="utf-8") == "preserve"

    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_report({"ok": True}, output)
    assert output.read_text(encoding="utf-8") == "existing"
