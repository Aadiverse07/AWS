import pytest

from app.demo_workflow import run_demo_decision, threshold_explanation, workflow_tree_state


def test_standard_demo_runs_mock_engine_and_records_matching_trace():
    run = run_demo_decision(
        scenario="Standard mock",
        question="Summarize the benchmark",
        preferred_route="developer",
    )

    assert run.outcome is not None
    assert run.outcome.primary_backend == "mock"
    assert run.outcome.selected == "developer"
    assert run.outcome.escalated is False
    assert len(run.trace_events) == 1
    event = run.trace_events[0]
    assert event["final_choice"] == run.outcome.selected
    assert event["confidence"] == run.outcome.confidence == 1.0
    assert event["threshold"] == 0.60
    assert event["run_id"] == run.request.run_id
    assert "Summarize the benchmark" not in str(event)


def test_low_confidence_fixture_exercises_real_single_fallback_path():
    run = run_demo_decision(
        scenario="Low-confidence fallback fixture",
        question="Route a documentation review",
        preferred_route="research",
    )

    assert run.outcome is not None
    assert run.outcome.primary_choice == "documentation"
    assert run.outcome.selected == "research"
    assert run.outcome.escalated is True
    assert run.outcome.final_source == "mock"
    event = run.trace_events[0]
    assert event["escalated"] is True
    assert event["fallback_invoked"] is True
    assert event["escalation_reason"] == "below_threshold"
    assert event["final_choice"] == run.outcome.selected


def test_backend_error_fixture_records_error_and_does_not_route():
    run = run_demo_decision(
        scenario="Backend error fixture",
        question="Route a failed task",
        preferred_route="documentation",
    )

    assert run.outcome is None
    assert run.error_type == "BackendInvocationError"
    assert len(run.trace_events) == 1
    assert run.trace_events[0]["status"] == "error"
    assert run.trace_events[0]["error_category"] == "primary_backend_error"
    assert run.trace_events[0]["final_choice"] is None


def test_tree_state_matches_recorded_standard_and_fallback_branches():
    normal = run_demo_decision(
        scenario="Standard mock", question="Review reports", preferred_route="research"
    )
    fallback = run_demo_decision(
        scenario="Low-confidence fallback fixture",
        question="Review reports",
        preferred_route="research",
    )

    normal_tree = workflow_tree_state(normal)
    assert normal_tree["primary_branch_state"] == "selected"
    assert normal_tree["fallback_branch_state"] == "unselected"
    assert normal_tree["condition"] == "1.00 ≥ 0.60"
    assert normal_tree["selected_route"] == normal.outcome.selected

    fallback_tree = workflow_tree_state(fallback)
    assert fallback_tree["primary_branch_state"] == "unselected"
    assert fallback_tree["fallback_branch_state"] == "selected"
    assert fallback_tree["condition"] == "0.20 < 0.60"
    assert fallback_tree["selected_route"] == fallback.outcome.selected


def test_tree_state_marks_backend_error_as_stopped_and_values_unavailable():
    run = run_demo_decision(
        scenario="Backend error fixture",
        question="Review reports",
        preferred_route="research",
    )
    tree = workflow_tree_state(run)

    assert tree["stopped"] is True
    assert tree["primary_state"] == "error"
    assert tree["condition"] == "Not available in this trace"
    assert tree["fallback_branch_state"] == "blocked"
    assert tree["action_state"] == "blocked"


@pytest.mark.parametrize(
    ("event", "expected_text", "source"),
    [
        (
            {"confidence": 1.0, "threshold": 0.6, "escalated": False},
            "meets threshold",
            "Derived from recorded fields",
        ),
        (
            {"confidence": 0.2, "threshold": 0.6, "escalated": True},
            "below threshold",
            "Derived from recorded fields",
        ),
        ({"confidence": None, "threshold": 0.6}, "unavailable", "Not available"),
        ({"confidence": 0.2}, "unavailable", "Not available"),
    ],
)
def test_threshold_explanation_uses_only_present_trace_fields(event, expected_text, source):
    text, evidence = threshold_explanation(event)
    assert expected_text in text
    assert evidence == source


def test_demo_rejects_unlisted_scenario_or_route():
    with pytest.raises(ValueError):
        run_demo_decision(scenario="Bedrock", question="test", preferred_route="research")
    with pytest.raises(ValueError):
        run_demo_decision(scenario="Standard mock", question="test", preferred_route="shell")
