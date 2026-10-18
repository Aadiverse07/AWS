import pytest

from jarvis.application import (
    ROUTING_DESTINATIONS,
    TaskRoutingAction,
    build_backend,
    run_workflow,
)
from jarvis.config import AppConfig, ConfigurationError
from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import (
    BackendInvocationError,
    DecisionEngine,
    InvalidPrimaryChoiceError,
)


def request(options=None):
    return DecisionRequest(
        decision_id="D1",
        question="Choose a destination",
        options=list(ROUTING_DESTINATIONS) if options is None else options,
        run_id="test-run",
        step=0,
    )


class FixedBackend(DecisionBackend):
    def __init__(self, name, choice, confidence):
        self._name = name
        self.choice = choice
        self.confidence = confidence
        self.calls = 0

    @property
    def name(self):
        return self._name

    def decide(self, req):
        self.calls += 1
        return DecisionResult(
            chosen=self.choice,
            confidence=self.confidence,
            latency_ms=0,
            backend=self.name,
        )


def test_valid_mock_style_request_reaches_local_action_once():
    primary = FixedBackend("mock", "research", 1.0)
    engine = DecisionEngine(primary, {"D1": 0.6})
    calls = []

    class Action:
        def execute(self, destination):
            calls.append(destination)
            return TaskRoutingAction().execute(destination)

    result = run_workflow(request(), engine, action=Action())
    assert result.selected == "research"
    assert result.action.destination == "research"
    assert calls == ["research"]
    assert primary.calls == 1


@pytest.mark.parametrize("options", [[], ["research"], ["research", "research"]])
def test_invalid_options_rejected_before_backend_call(options):
    backend = FixedBackend("fake", "research", 1.0)
    engine = DecisionEngine(backend, {"D1": 0.6})
    with pytest.raises(ValueError):
        request(options)
    assert backend.calls == 0


def test_out_of_set_primary_choice_never_reaches_action_or_fallback():
    primary = FixedBackend("primary", "unsupported", 0.1)
    fallback = FixedBackend("fallback", "research", 1.0)
    engine = DecisionEngine(primary, {"D1": 0.6}, fallback)
    with pytest.raises(InvalidPrimaryChoiceError):
        run_workflow(request(), engine)
    assert primary.calls == 1
    assert fallback.calls == 0


def test_out_of_set_fallback_choice_never_reaches_action():
    primary = FixedBackend("primary", "research", 0.1)
    fallback = FixedBackend("fallback", "unsupported", 1.0)
    called = []

    class Action:
        def execute(self, destination):
            called.append(destination)
            return TaskRoutingAction().execute(destination)

    from jarvis.decision.engine import InvalidFallbackChoiceError

    engine = DecisionEngine(primary, {"D1": 0.6}, fallback)
    with pytest.raises(InvalidFallbackChoiceError):
        run_workflow(request(), engine, action=Action())
    assert fallback.calls == 1
    assert called == []


def test_unknown_confidence_escalates_once_and_records_it():
    primary = FixedBackend("primary", "research", None)
    fallback = FixedBackend("fallback", "developer", 0.95)
    result = run_workflow(request(), DecisionEngine(primary, {"D1": 0.6}, fallback))
    assert result.selected == "developer"
    assert result.escalated is True
    assert fallback.calls == 1


def test_bedrock_selection_requires_paid_opt_in_before_construction():
    with pytest.raises(ConfigurationError, match="COST_MODE=production"):
        build_backend("bedrock", AppConfig())


def test_paid_opt_in_constructs_bedrock_backend_without_network_client():
    backend = build_backend("bedrock", AppConfig("production", True))
    assert backend.name == "bedrock"
    assert backend._client is None


def test_unknown_backend_is_actionable():
    with pytest.raises(ConfigurationError, match="mock, local_hf, or bedrock"):
        build_backend("other", AppConfig())


def test_local_hf_selection_is_lazy():
    backend = build_backend("local_hf", AppConfig())
    assert backend.name == "local_hf"


def test_routing_action_rejects_unknown_destination():
    with pytest.raises(ValueError, match="not an allowed"):
        TaskRoutingAction().execute("shell")


def test_fallback_failure_prevents_action_execution():
    primary = FixedBackend("primary", "research", 0.1)

    class FailingFallback(FixedBackend):
        def decide(self, req):
            self.calls += 1
            raise RuntimeError("api_key=do-not-log")

    fallback = FailingFallback("fallback", "developer", 1.0)
    called = []

    class Action:
        def execute(self, destination):
            called.append(destination)
            return TaskRoutingAction().execute(destination)

    with pytest.raises(BackendInvocationError) as caught:
        run_workflow(
            request(), DecisionEngine(primary, {"D1": 0.6}, fallback), action=Action()
        )
    assert caught.value.backend_role == "fallback"
    assert "do-not-log" not in str(caught.value)
    assert fallback.calls == 1
    assert called == []


def test_action_failure_is_not_reported_as_success():
    class BrokenAction:
        def execute(self, destination):
            raise OSError("local action failed")

    engine = DecisionEngine(FixedBackend("mock", "research", 1.0), {"D1": 0.6})
    with pytest.raises(OSError, match="local action failed"):
        run_workflow(request(), engine, action=BrokenAction())


def test_trace_storage_failure_prevents_action_execution():
    from jarvis.observability.traced_engine import TracingDecisionEngine

    class BrokenRecorder:
        def record_decision(self, **kwargs):
            raise OSError("trace storage unavailable")

    called = []

    class Action:
        def execute(self, destination):
            called.append(destination)
            return TaskRoutingAction().execute(destination)

    traced = TracingDecisionEngine(
        DecisionEngine(FixedBackend("mock", "research", 1.0), {"D1": 0.6}),
        BrokenRecorder(),
    )
    with pytest.raises(OSError, match="trace storage unavailable"):
        run_workflow(request(), traced, action=Action())
    assert called == []
