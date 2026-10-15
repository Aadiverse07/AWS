"""Stable, provider-independent contracts for Jarvis decisions."""

import math

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class DecisionRequest(BaseModel):
    """A request to choose one option for a specific decision."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    context: str = ""
    options: list[str] = Field(min_length=2)
    run_id: str = Field(min_length=1)
    step: int = Field(ge=0)

    @field_validator("decision_id", "question", "run_id")
    @classmethod
    def required_strings_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("options")
    @classmethod
    def options_must_be_unique_and_nonblank(
        cls, options: list[str]
    ) -> list[str]:
        if any(not option for option in options):
            raise ValueError("options must not contain blank values")
        if len(set(options)) != len(options):
            raise ValueError("options must be unique")
        return options


class DecisionResult(BaseModel):
    """Normalized result returned by any decision backend."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chosen: str
    scores: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    latency_ms: float = Field(ge=0.0)
    backend: str = Field(min_length=1)
    escalated: bool = False
    final_choice: str | None = None
    final_source: str | None = None

    @field_validator("chosen", "backend")
    @classmethod
    def required_strings_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("scores")
    @classmethod
    def scores_must_be_valid_probabilities(
        cls, scores: dict[str, float]
    ) -> dict[str, float]:
        for option, score in scores.items():
            if not option.strip():
                raise ValueError("score option names must not be blank")
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError(
                    "each score must be a finite value between 0 and 1"
                )

        return scores

    @model_validator(mode="after")
    def chosen_must_have_a_score(self) -> "DecisionResult":
        if self.scores and self.chosen not in self.scores:
            raise ValueError("chosen must be a key in scores when scores are provided")
        return self

    @field_validator("final_choice", "final_source")
    @classmethod
    def optional_strings_must_not_be_blank(
        cls, value: str | None
    ) -> str | None:
        if value is not None and not value:
            raise ValueError("must not be blank when provided")
        return value
