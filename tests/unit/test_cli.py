from jarvis.cli import main

def test_cli_defaults_to_mock_and_validates_config_first(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main([]) == 0
    assert "backend=mock" in capsys.readouterr().out

def test_cli_runs_end_to_end_mock_demo(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main(["--run-demo"]) == 0
    output = capsys.readouterr().out
    assert "backend=mock" in output
    assert "choice=research" in output
    assert "escalated=false" in output
    assert "destination=research" in output

def test_cli_records_trace_for_run_demo(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setenv("COST_MODE", "free")
    monkeypatch.setenv("ALLOW_PAID", "false")
    path = tmp_path / "demo.jsonl"
    assert main(["--run-demo", "--record-trace", "--trace-path", str(path)]) == 0
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "decision"
    assert event["backend"] == "mock"
    assert "Decision complete" in capsys.readouterr().out

def test_cli_rejects_record_trace_without_run_demo(capsys):
    import pytest
    with pytest.raises(SystemExit) as caught:
        main(["--record-trace"])
    assert caught.value.code == 2
    assert "requires --run-demo" in capsys.readouterr().err

def test_cli_blocks_bedrock_demo_before_provider_request(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main(["--backend", "bedrock", "--run-demo"]) == 2
    assert "requires COST_MODE=production and ALLOW_PAID=true" in capsys.readouterr().err

def test_cli_backend_failure_returns_non_success_without_traceback(monkeypatch, capsys):
    import jarvis.application

    monkeypatch.setattr(
        jarvis.application,
        "run_default_demo",
        lambda backend, *, trace_path=None: (_ for _ in ()).throw(RuntimeError("backend unavailable")),
    )
    assert main(["--run-demo"]) == 1
    assert "backend unavailable" in capsys.readouterr().err

def test_cli_rejects_production_before_backend_init(monkeypatch, capsys):
    monkeypatch.setenv("COST_MODE", "production")
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main(["--backend", "local_hf"]) == 2
    assert "requires ALLOW_PAID=true" in capsys.readouterr().err

def test_cli_config_check_does_not_load_model(monkeypatch, capsys):
    monkeypatch.setenv("COST_MODE", "free")
    assert main(["--check-config"]) == 0
    assert "Configuration valid" in capsys.readouterr().out

def test_cli_allows_explicit_production_opt_in(monkeypatch, capsys):
    monkeypatch.setenv("COST_MODE", "production")
    monkeypatch.setenv("ALLOW_PAID", "true")
    assert main(["--check-config"]) == 0
    assert "COST_MODE=production" in capsys.readouterr().out


def test_cli_demo_trace_writes_jsonl(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    path = tmp_path / "trace.jsonl"
    assert main(["--demo-trace", "--trace-path", str(path)]) == 0
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["decision_id"] == "D1"
    assert event["backend"] == "mock"
    assert event["status"] in {"success", "escalated"}
    assert "Mock decision recorded" in capsys.readouterr().out


def test_cli_demo_trace_rejects_local_backend(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main(["--demo-trace", "--backend", "local_hf"]) == 2
    assert "requires --backend mock" in capsys.readouterr().err


def test_cli_blocks_bedrock_by_default(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main(["--backend", "bedrock"]) == 2
    assert "requires COST_MODE=production and ALLOW_PAID=true" in capsys.readouterr().err


def test_cli_blocks_bedrock_in_free_mode_even_with_paid_flag(monkeypatch, capsys):
    monkeypatch.setenv("COST_MODE", "free")
    monkeypatch.setenv("ALLOW_PAID", "true")
    assert main(["--backend", "bedrock"]) == 2
    assert "requires COST_MODE=production and ALLOW_PAID=true" in capsys.readouterr().err


def test_cli_allows_bedrock_selection_after_explicit_opt_in(monkeypatch, capsys):
    import boto3

    monkeypatch.setenv("COST_MODE", "production")
    monkeypatch.setenv("ALLOW_PAID", "true")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")

    def forbidden_client(*args, **kwargs):
        raise AssertionError("readiness must not create an AWS client")

    monkeypatch.setattr(boto3, "client", forbidden_client)
    assert main(["--backend", "bedrock"]) == 0
    assert "backend=bedrock" in capsys.readouterr().out
