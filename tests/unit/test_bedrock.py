import json

import pytest

from jarvis.decision.backends.bedrock import (
    BedrockBackend,
    BedrockBackendError,
)
from jarvis.decision.contract import DecisionRequest


def make_request():
    return DecisionRequest(
        decision_id="D1",
        question="Which step should happen next?",
        context="A required input is missing.",
        options=["request_input", "continue", "escalate"],
        run_id="test-run",
        step=0,
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def response_with_text(text):
    return {
        "output": {
            "message": {
                "content": [{"text": text}],
            }
        }
    }


def test_backend_name_and_model_defaults():
    backend = BedrockBackend(client=FakeClient())

    assert backend.name == "bedrock"
    assert backend.model_id == "amazon.nova-lite-v1:0"


def test_invalid_model_id_is_rejected():
    with pytest.raises(ValueError, match="model_id"):
        BedrockBackend(model_id=" ")


def test_decision_prompt_contains_only_supplied_options():
    client = FakeClient(
        response=response_with_text(
            json.dumps(
                {
                    "chosen": "request_input",
                    "rationale": "A required input is missing.",
                }
            )
        )
    )
    backend = BedrockBackend(client=client)

    result = backend.decide(make_request())

    assert result.chosen == "request_input"
    assert result.confidence is None
    assert result.scores == {}
    assert result.backend == "bedrock"
    assert result.latency_ms >= 0
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["modelId"] == "amazon.nova-lite-v1:0"
    assert call["inferenceConfig"]["temperature"] == 0
    prompt = json.loads(call["messages"][0]["content"][0]["text"])
    assert prompt["allowed_options"] == [
        "request_input",
        "continue",
        "escalate",
    ]


def test_unapproved_choice_is_rejected():
    client = FakeClient(
        response=response_with_text(
            '{"chosen":"delete_everything","rationale":"unsafe"}'
        )
    )
    with pytest.raises(BedrockBackendError, match="not supplied"):
        BedrockBackend(client=client).decide(make_request())


def test_malformed_json_is_rejected():
    client = FakeClient(response=response_with_text("not json"))
    with pytest.raises(BedrockBackendError, match="valid JSON"):
        BedrockBackend(client=client).decide(make_request())


def test_unexpected_response_shape_is_rejected():
    client = FakeClient(response={})
    with pytest.raises(BedrockBackendError, match="response structure"):
        BedrockBackend(client=client).decide(make_request())


def test_provider_error_does_not_echo_provider_message():
    client = FakeClient(error=RuntimeError("sensitive provider detail"))
    with pytest.raises(BedrockBackendError) as exc:
        BedrockBackend(client=client).decide(make_request())

    assert "sensitive provider detail" not in str(exc.value)


def test_client_is_created_lazily():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeClient(response=response_with_text('{"chosen":"continue"}'))

    backend = BedrockBackend(
        region_name="eu-north-1",
        client_factory=factory,
    )

    assert calls == []
    result = backend.decide(make_request())

    assert result.chosen == "continue"
    assert result.confidence is None
    assert result.scores == {}

    assert calls == [
        {
            "service_name": "bedrock-runtime",
            "region_name": "eu-north-1",
        }
    ]


def test_fenced_json_is_parsed_before_contract_validation():
    client = FakeClient(
        response=response_with_text(
            '```json\n{"chosen":"continue","rationale":"ok"}\n```'
        )
    )
    result = BedrockBackend(client=client).decide(make_request())

    assert result.chosen == "continue"
    assert result.confidence is None
    assert result.scores == {}
