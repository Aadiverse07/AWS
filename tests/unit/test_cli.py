from jarvis.cli import main

def test_cli_defaults_to_mock_and_validates_config_first(monkeypatch, capsys):
    monkeypatch.delenv("COST_MODE", raising=False)
    monkeypatch.delenv("ALLOW_PAID", raising=False)
    assert main([]) == 0
    assert "backend=mock" in capsys.readouterr().out

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
