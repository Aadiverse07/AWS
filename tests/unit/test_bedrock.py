import json

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from jarvis.decision.backends.bedrock import (
    CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MODEL_ID,
    MAX_PROMPT_BYTES,
    READ_TIMEOUT_SECONDS,
    TOTAL_MAX_ATTEMPTS,
    BedrockBackend,
    BedrockBackendError,
)
from jarvis.decision.contract import DecisionRequest


def make_request(question="Which step should happen next?", context="A required input is missing."):
    return DecisionRequest(
        decision_id="D1",
        question=question,
        context=context,
        options=["request_input", "continue", "escalate"],
        run_id="test-run",
        step=0,
    )


def make_backend(**kwargs):
    return BedrockBackend(paid_use_enabled=True, **kwargs)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.error, list):
            error = self.error.pop(0) if self.error else None
            if error is not None:
                raise error
        elif self.error:
            raise self.error
        return self.response


def response_with_text(text):
    return {"output": {"message": {"content": [{"text": text}]}}}


def sdk_error(code, status):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "SIMULATED_SECRET_MESSAGE"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "Converse",
    )


def test_backend_defaults_and_normalized_valid_response():
    client = FakeClient(
        response=response_with_text(
            json.dumps({"chosen": "request_input", "rationale": "A required input is missing."})
        )
    )
    backend = make_backend(client=client)

    result = backend.decide(make_request())

    assert backend.name == "bedrock"
    assert backend.model_id == DEFAULT_MODEL_ID == "amazon.nova-lite-v1:0"
    assert result.chosen == "request_input"
    assert result.confidence is None
    assert result.scores == {}
    assert result.backend == "bedrock"
    assert result.latency_ms >= 0
    call = client.calls[0]
    assert call["modelId"] == DEFAULT_MODEL_ID
    assert call["inferenceConfig"] == {"maxTokens": 160, "temperature": 0}
    assert json.loads(call["messages"][0]["content"][0]["text"])["allowed_options"] == list(
        make_request().options
    )


@pytest.mark.parametrize("kwargs", [{"model_id": " "}, {"region_name": " "}])
def test_blank_provider_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        BedrockBackend(**kwargs)


def test_paid_use_guard_requires_boolean_opt_in():
    with pytest.raises(ValueError, match="must be a boolean"):
        BedrockBackend(paid_use_enabled="true")


def test_fenced_json_is_parsed():
    client = FakeClient(response=response_with_text('```json\n{"chosen":"continue"}\n```'))
    assert make_backend(client=client).decide(make_request()).chosen == "continue"


def test_direct_backend_invocation_is_disabled_without_paid_opt_in():
    client = FakeClient(response=response_with_text('{"chosen":"continue"}'))
    with pytest.raises(BedrockBackendError) as caught:
        BedrockBackend(client=client).decide(make_request())
    assert caught.value.category == "configuration"
    assert caught.value.request_attempted is False
    assert client.calls == []


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"output": {"message": {}}},
        {"output": {"message": {"content": "not-a-list"}}},
        {"output": {"message": {"content": [None]}}},
        {"output": {"message": {"content": [{"image": {}}]}}},
        {"output": {"message": {"content": [{"text": None}]}}},
        {"output": {"message": {"content": []}}},
    ],
)
def test_missing_empty_and_malformed_response_content_is_rejected(response):
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client=FakeClient(response=response)).decide(make_request())
    assert caught.value.category == "invalid_response"
    assert caught.value.request_attempted is True


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "null",
        "[]",
        "{}",
        '{"chosen":"unsupported"}',
        '{"chosen":4}',
        '{"chosen":"continue","confidence":0.99}',
        '{"chosen":"continue","scores":{"continue":1}}',
        '{"chosen":"continue","confidence":NaN}',
        '{"chosen":"continue","rationale":4}',
        '{"chosen":"continue","other":"not-supported"}',
    ],
)
def test_malformed_or_unsupported_decision_payload_is_rejected(text):
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client=FakeClient(response=response_with_text(text))).decide(
            make_request()
        )
    assert caught.value.category == "invalid_response"
    assert caught.value.request_attempted is True


def test_unclosed_json_fence_is_rejected():
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(
            client=FakeClient(response=response_with_text('```json {"chosen":"continue"}'))
        ).decide(make_request())
    assert caught.value.category == "invalid_response"


def test_prompt_limit_rejects_before_client_creation_or_request():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeClient()

    backend = make_backend(client_factory=factory)
    with pytest.raises(BedrockBackendError) as caught:
        backend.decide(make_request(context="x" * MAX_PROMPT_BYTES))
    assert caught.value.category == "invalid_request"
    assert caught.value.request_attempted is False
    assert calls == []


def test_oversized_model_response_is_rejected():
    client = FakeClient(response=response_with_text("x" * 9_000))
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client=client).decide(make_request())
    assert caught.value.category == "invalid_response"
    assert caught.value.request_attempted is True


def test_client_is_lazy_and_uses_explicit_region_and_bounded_sdk_settings():
    factory_calls = []
    client = FakeClient(response=response_with_text('{"chosen":"continue"}'))

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return client

    backend = make_backend(
        model_id="us.amazon.nova-lite-v1:0",
        region_name="us-east-1",
        client_factory=factory,
    )
    assert factory_calls == []
    backend.decide(make_request())

    assert len(factory_calls) == 1
    config = factory_calls[0]["config"]
    assert factory_calls[0]["service_name"] == "bedrock-runtime"
    assert factory_calls[0]["region_name"] == "us-east-1"
    assert config.connect_timeout == CONNECT_TIMEOUT_SECONDS == 5
    assert config.read_timeout == READ_TIMEOUT_SECONDS == 30
    assert config.retries == {
        "mode": "standard",
        "total_max_attempts": 1,
    }


@pytest.mark.parametrize(
    ("error", "expected", "expected_attempts"),
    [
        (sdk_error("ThrottlingException", 429), "throttling", 2),
        (sdk_error("ServiceQuotaExceededException", 429), "throttling", 2),
        (sdk_error("AccessDeniedException", 403), "authorization", 1),
        (sdk_error("UnrecognizedClientException", 403), "authentication", 1),
        (sdk_error("ValidationException", 400), "invalid_request", 1),
        (sdk_error("ResourceNotFoundException", 404), "configuration", 1),
        (sdk_error("ServiceUnavailableException", 503), "service_unavailable", 2),
        (sdk_error("InternalServerException", 500), "service_unavailable", 2),
        (ReadTimeoutError(endpoint_url="https://example.invalid"), "timeout", 1),
        (TimeoutError("SIMULATED_SECRET_MESSAGE"), "timeout", 1),
        (ConnectionError("SIMULATED_SECRET_MESSAGE"), "network_error", 1),
        (RuntimeError("SIMULATED_SECRET_MESSAGE"), "backend_error", 1),
    ],
)
def test_provider_errors_are_classified_and_sanitized(error, expected, expected_attempts):
    client = FakeClient(error=error)
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client=client).decide(make_request())
    assert caught.value.category == expected
    assert caught.value.request_attempted is True
    assert "SIMULATED_SECRET_MESSAGE" not in str(caught.value)
    assert len(client.calls) == expected_attempts


def test_transient_error_retries_once_then_returns_valid_response(monkeypatch):
    monkeypatch.setattr("jarvis.decision.backends.bedrock.time.sleep", lambda _delay: None)
    monkeypatch.setattr("jarvis.decision.backends.bedrock.random.uniform", lambda _a, _b: 0)
    client = FakeClient(
        response=response_with_text('{"chosen":"continue"}'),
        error=[sdk_error("ThrottlingException", 429), None],
    )
    result = make_backend(client=client).decide(make_request())
    assert result.chosen == "continue"
    assert len(client.calls) == TOTAL_MAX_ATTEMPTS == 2


def test_retry_limit_is_respected_without_unbounded_loop(monkeypatch):
    monkeypatch.setattr("jarvis.decision.backends.bedrock.time.sleep", lambda _delay: None)
    monkeypatch.setattr("jarvis.decision.backends.bedrock.random.uniform", lambda _a, _b: 0)
    client = FakeClient(error=sdk_error("ThrottlingException", 429))
    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client=client).decide(make_request())
    assert caught.value.category == "throttling"
    assert caught.value.attempt_count == TOTAL_MAX_ATTEMPTS
    assert len(client.calls) == TOTAL_MAX_ATTEMPTS


def test_client_creation_error_is_classified_before_request():
    def factory(**kwargs):
        raise RuntimeError("SIMULATED_SECRET_MESSAGE")

    with pytest.raises(BedrockBackendError) as caught:
        make_backend(client_factory=factory).decide(make_request())
    assert caught.value.category == "backend_error"
    assert caught.value.request_attempted is False
    assert "SIMULATED_SECRET_MESSAGE" not in str(caught.value)
