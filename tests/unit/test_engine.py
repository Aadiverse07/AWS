import pytest

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.backends.mock import MockBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult
from jarvis.decision.engine import (
    DecisionEngine,
    EscalationUnavailableError,
    InvalidFallbackChoiceError,
    MissingThresholdError,
)


def make_request(decision_id: str = "D1") -> DecisionRequest:
    return DecisionRequest(
        decision_id=decision_id,
        question="Which agent should handle this task?",
        context="The user asks about a GitHub repository.",
        options=["developer", "research"],
        run_id="run-001",
        step=0,
    )


class FakeBackend(DecisionBackend):
    """Scripted backend that records every call it receives."""

    def __init__(
        self,
        name: str,
        *,
        choice: str = "developer",
        confidence: float = 1.0,
        latency_ms: float = 1.0,
        scores: dict[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._name = name
        self.choice = choice
        self.confidence = confidence
        self.latency_ms = latency_ms
        self.scores = scores
        self.error = error
        self.requests: list[DecisionRequest] = []
        self.last_result: DecisionResult | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def calls(self) -> int:
        return len(self.requests)

    def decide(self, request: DecisionRequest) -> DecisionResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error

        scores = self.scores
        if scores is None:
            scores = {option: 0.0 for option in request.options}
            scores[self.choice] = 1.0

        self.last_result = DecisionResult(
            chosen=self.choice,
            scores=scores,
            confidence=self.confidence,
            latency_ms=self.latency_ms,
            backend=self._name,
        )
        return self.last_result


PRIMARY_SCORES = {"developer": 0.6, "research": 0.4}


def make_primary(confidence: float, **kwargs) -> FakeBackend:
    return FakeBackend(
        "primary",
        choice="developer",
        confidence=confidence,
        latency_ms=12.5,
        scores=PRIMARY_SCORES,
        **kwargs,
    )


def make_fallback(**kwargs) -> FakeBackend:
    kwargs.setdefault("choice", "research")
    kwargs.setdefault("confidence", 0.95)
    kwargs.setdefault("latency_ms", 900.0)
    return FakeBackend("fallback", **kwargs)


# --- Decision behavior -------------------------------------------------------


def test_high_confidence_returns_primary_without_calling_fallback():
    primary = make_primary(confidence=0.9)
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)
    request = make_request()

    result = engine.decide(request)

    assert result.escalated is False
    assert result.chosen == "developer"
    assert result.final_choice == "developer"
    assert result.final_source == "primary"
    assert result.backend == "primary"
    assert result.scores == PRIMARY_SCORES
    assert result.confidence == 0.9
    assert result.latency_ms == 12.5
    assert primary.requests == [request]
    assert fallback.calls == 0


def test_low_confidence_calls_fallback_once_and_uses_its_choice():
    primary = make_primary(confidence=0.4)
    fallback = make_fallback(choice="research")
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)
    request = make_request()

    result = engine.decide(request)

    assert result.escalated is True
    assert result.final_choice == "research"
    assert result.final_source == "fallback"
    assert primary.requests == [request]
    assert fallback.requests == [request]


def test_escalation_preserves_original_primary_fields():
    primary = make_primary(confidence=0.4)
    engine = DecisionEngine(primary, {"D1": 0.7}, make_fallback())

    result = engine.decide(make_request())

    assert result.chosen == "developer"
    assert result.scores == PRIMARY_SCORES
    assert result.confidence == 0.4
    assert result.latency_ms == 12.5
    assert result.backend == "primary"


def test_engine_does_not_mutate_the_backends_own_result():
    primary = make_primary(confidence=0.4)
    engine = DecisionEngine(primary, {"D1": 0.7}, make_fallback())

    engine.decide(make_request())

    assert primary.last_result is not None
    assert primary.last_result.escalated is False
    assert primary.last_result.final_choice is None
    assert primary.last_result.final_source is None


@pytest.mark.parametrize(
    ("threshold", "confidence", "should_escalate"),
    [
        (0.7, 0.7, False),
        (0.7, 0.7001, False),
        (0.7, 0.6999, True),
        (0.0, 0.0, False),
        (1.0, 1.0, False),
        (1, 1.0, False),
        (1.0, 0.9999, True),
    ],
)
def test_escalates_only_when_confidence_is_strictly_below_threshold(
    threshold, confidence, should_escalate
):
    primary = make_primary(confidence=confidence)
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": threshold}, fallback)

    result = engine.decide(make_request())

    assert result.escalated is should_escalate
    assert fallback.calls == (1 if should_escalate else 0)


def test_works_with_real_mock_backend_as_primary():
    fallback = make_fallback()
    engine = DecisionEngine(MockBackend(), {"D1": 0.9}, fallback)

    result = engine.decide(make_request())

    assert result.escalated is False
    assert result.final_choice == "developer"
    assert result.final_source == "mock"
    assert fallback.calls == 0


def test_high_confidence_does_not_need_a_fallback():
    engine = DecisionEngine(make_primary(confidence=0.9), {"D1": 0.7})

    result = engine.decide(make_request())

    assert result.escalated is False
    assert result.final_source == "primary"


def test_each_decision_id_uses_its_own_threshold():
    primary = make_primary(confidence=0.5)
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": 0.4, "D2": 0.8}, fallback)

    assert engine.decide(make_request("D1")).escalated is False
    assert engine.decide(make_request("D2")).escalated is True


# --- Error handling at decision time -----------------------------------------


def test_missing_threshold_raises_before_any_backend_call():
    primary = make_primary(confidence=0.9)
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    with pytest.raises(MissingThresholdError, match="'D2'") as excinfo:
        engine.decide(make_request("D2"))

    assert "'D1'" in str(excinfo.value)
    assert primary.calls == 0
    assert fallback.calls == 0



def test_unknown_confidence_calls_fallback_once_and_preserves_primary_result():
    primary = FakeBackend(
        "bedrock",
        choice="developer",
        confidence=None,
        scores={},
        latency_ms=15.0,
    )
    fallback = make_fallback(choice="research")
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)
    request = make_request()

    result = engine.decide(request)

    assert primary.calls == 1
    assert fallback.calls == 1
    assert result.escalated is True
    assert result.chosen == "developer"
    assert result.confidence is None
    assert result.scores == {}
    assert result.final_choice == "research"
    assert result.final_source == "fallback"


def test_unknown_confidence_without_fallback_raises_clear_error():
    primary = FakeBackend(
        "bedrock",
        choice="developer",
        confidence=None,
        scores={},
    )
    engine = DecisionEngine(primary, {"D1": 0.7})

    with pytest.raises(
        EscalationUnavailableError,
        match="confidence is unknown",
    ):
        engine.decide(make_request())

    assert primary.calls == 1

def test_low_confidence_without_fallback_raises_clear_error():
    primary = make_primary(confidence=0.4)
    engine = DecisionEngine(primary, {"D1": 0.7})

    with pytest.raises(EscalationUnavailableError, match="no fallback"):
        engine.decide(make_request())

    assert primary.calls == 1


def test_fallback_choice_outside_supplied_options_is_rejected():
    primary = make_primary(confidence=0.4)
    fallback = make_fallback(choice="unknown")
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    with pytest.raises(InvalidFallbackChoiceError, match="'unknown'"):
        engine.decide(make_request())

    assert primary.calls == 1
    assert fallback.calls == 1


# --- Call counts: no retries, loops, or recursion ----------------------------


def test_fallback_confidence_never_triggers_another_call():
    primary = make_primary(confidence=0.4)
    fallback = make_fallback(confidence=0.0)
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    result = engine.decide(make_request())

    assert result.final_source == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_each_decide_call_makes_exactly_one_call_per_backend_needed():
    primary = make_primary(confidence=0.4)
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    engine.decide(make_request())
    engine.decide(make_request())

    assert primary.calls == 2
    assert fallback.calls == 2


def test_primary_failure_propagates_without_retry_or_fallback():
    primary = make_primary(confidence=0.9, error=RuntimeError("primary down"))
    fallback = make_fallback()
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    with pytest.raises(RuntimeError, match="primary down"):
        engine.decide(make_request())

    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_failure_propagates_without_retry():
    primary = make_primary(confidence=0.4)
    fallback = make_fallback(error=RuntimeError("fallback down"))
    engine = DecisionEngine(primary, {"D1": 0.7}, fallback)

    with pytest.raises(RuntimeError, match="fallback down"):
        engine.decide(make_request())

    assert primary.calls == 1
    assert fallback.calls == 1


# --- Threshold validation ----------------------------------------------------


def test_empty_threshold_mapping_is_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        DecisionEngine(make_primary(confidence=0.9), {})


@pytest.mark.parametrize("thresholds", [None, ["D1"], 0.5])
def test_non_mapping_thresholds_are_rejected(thresholds):
    with pytest.raises(TypeError, match="mapping"):
        DecisionEngine(make_primary(confidence=0.9), thresholds)


@pytest.mark.parametrize("decision_id", ["", "   ", "\t\n", 1, None])
def test_blank_or_non_string_decision_ids_are_rejected(decision_id):
    with pytest.raises(ValueError, match="decision IDs must be non-blank"):
        DecisionEngine(make_primary(confidence=0.9), {decision_id: 0.5})


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.1,
        -1,
        1.1,
        2,
        "0.5",
        None,
    ],
    ids=[
        "true",
        "false",
        "nan",
        "inf",
        "-inf",
        "negative-float",
        "negative-int",
        "above-one-float",
        "above-one-int",
        "string",
        "none",
    ],
)
def test_invalid_threshold_values_are_rejected(value):
    with pytest.raises(ValueError, match="threshold for 'D1'"):
        DecisionEngine(make_primary(confidence=0.9), {"D1": value})


@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0])
def test_boundary_and_numeric_thresholds_are_accepted(value):
    engine = DecisionEngine(make_primary(confidence=1.0), {"D1": value})

    assert engine.decide(make_request()).escalated is False


def test_one_invalid_threshold_rejects_the_whole_mapping():
    with pytest.raises(ValueError, match="threshold for 'D2'"):
        DecisionEngine(
            make_primary(confidence=0.9),
            {"D1": 0.5, "D2": float("nan")},
        )


def test_decision_ids_are_matched_after_trimming_whitespace():
    primary = make_primary(confidence=0.9)
    engine = DecisionEngine(primary, {" D1 ": 0.5})

    result = engine.decide(make_request("D1"))

    assert result.escalated is False
    assert primary.calls == 1


def test_decision_ids_colliding_after_trimming_are_rejected():
    with pytest.raises(ValueError, match="duplicate decision ID"):
        DecisionEngine(
            make_primary(confidence=0.9),
            {"D1": 0.5, " D1 ": 0.6},
        )


def test_engine_copies_thresholds_so_later_mutation_has_no_effect():
    thresholds = {"D1": 0.5}
    fallback = make_fallback()
    engine = DecisionEngine(make_primary(confidence=0.6), thresholds, fallback)

    thresholds["D1"] = 0.9

    assert engine.decide(make_request()).escalated is False
    assert fallback.calls == 0
