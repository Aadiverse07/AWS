"""Local Strands Decider backend, isolated behind the generic interface."""

from collections.abc import Callable
from time import perf_counter
from typing import Any

from jarvis.decision.backends.base import DecisionBackend
from jarvis.decision.contract import DecisionRequest, DecisionResult


DEFAULT_MODEL_ID = "StrandsAgents/strands-decider-2B-hobson-v21"


class LocalHFBackend(DecisionBackend):
    """Use a local Strands Decider checkpoint for multiple-choice decisions.

    The model is loaded lazily on the first decision. An engine can be injected
    to test result normalization without loading model weights.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        device: str = "mps",
        engine: Any | None = None,
        engine_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must not be blank")
        if not device.strip():
            raise ValueError("device must not be blank")

        self.model_id = model_id
        self.device = device
        self._engine = engine
        self._engine_factory = engine_factory

    @property
    def name(self) -> str:
        return "local_hf"

    def _get_engine(self) -> Any:
        if self._engine is None:
            factory = self._engine_factory
            if factory is None:
                # Import only when real local inference is requested.
                from strands_decider.infer import load_engine

                factory = load_engine

            self._engine = factory(self.model_id, device=self.device)

        return self._engine

    def decide(self, request: DecisionRequest) -> DecisionResult:
        from strands_decider.schema import ChoiceQuestion

        question = ChoiceQuestion(
            instructions=request.question,
            criteria={option: option for option in request.options},
        )
        state = request.context or "No additional context provided."

        started = perf_counter()
        response = self._get_engine().ask(
            state=state,
            questions={"decision": question},
        )
        latency_ms = (perf_counter() - started) * 1000

        try:
            answer = response.answers["decision"]
        except (AttributeError, KeyError, TypeError) as exc:
            raise ValueError(
                "Strands Decider returned no 'decision' answer"
            ) from exc

        chosen = answer.choice
        scores = dict(answer.probabilities)

        if chosen not in request.options:
            raise ValueError(
                f"Backend selected {chosen!r}, which is not a supplied option"
            )

        if set(scores) != set(request.options):
            raise ValueError(
                "Backend probabilities must contain exactly the supplied options"
            )

        return DecisionResult(
            chosen=chosen,
            scores=scores,
            confidence=answer.confidence,
            latency_ms=latency_ms,
            backend=self.name,
        )
