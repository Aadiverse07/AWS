import json
from urllib.error import URLError

import pytest

from jarvis.orchestrator.planner import (
    OllamaPlanner,
    Plan,
    PlannerError,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def response_for(content):
    return {"message": {"content": json.dumps(content)}}


def test_valid_plan_uses_local_ollama(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return FakeResponse(
            response_for(
                {
                    "plan": [
                        {"step": 1, "description": "Read the issue."},
                        {"step": 2, "description": "Check related reports."},
                    ]
                }
            )
        )

    monkeypatch.setattr("jarvis.orchestrator.planner.urlopen", fake_urlopen)
    result = OllamaPlanner().create_plan("Review this issue")

    assert len(result.plan) == 2
    assert [step.step for step in result.plan] == [1, 2]
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["model"] == "qwen2.5:3b"
    assert captured["body"]["format"] == Plan.model_json_schema()


def test_rejects_more_than_five_steps():
    content = {
        "plan": [
            {"step": i, "description": f"Step {i}"}
            for i in range(1, 7)
        ]
    }
    with pytest.raises(ValueError):
        Plan.model_validate(content)


def test_rejects_nonconsecutive_step_numbers():
    with pytest.raises(ValueError):
        Plan.model_validate(
            {"plan": [{"step": 2, "description": "Skip step one"}]}
        )


def test_rejects_extra_fields():
    with pytest.raises(ValueError):
        Plan.model_validate(
            {
                "plan": [{"step": 1, "description": "Read issue"}],
                "execute_now": True,
            }
        )


def test_handles_invalid_model_json(monkeypatch):
    monkeypatch.setattr(
        "jarvis.orchestrator.planner.urlopen",
        lambda *args, **kwargs: FakeResponse(
            {"message": {"content": '{"plan": []}'}}
        ),
    )
    with pytest.raises(PlannerError, match="invalid plan"):
        OllamaPlanner().create_plan("Review issue")


def test_handles_unavailable_ollama(monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr("jarvis.orchestrator.planner.urlopen", fail)
    with pytest.raises(PlannerError, match="unavailable or timed out"):
        OllamaPlanner().create_plan("Review issue")


def test_rejects_nonlocal_server():
    with pytest.raises(ValueError, match="local loopback"):
        OllamaPlanner(base_url="https://example.com")


def test_rejects_empty_task():
    with pytest.raises(ValueError, match="Task cannot be empty"):
        OllamaPlanner().create_plan("   ")
