import pytest
from jarvis.config import AppConfig, ConfigurationError, load_config

def test_defaults_to_free():
    assert AppConfig.from_mapping({}) == AppConfig("free", False)

@pytest.mark.parametrize("mode", ["free", " FREE ", "Free"])
def test_free_mode(mode):
    assert AppConfig.from_mapping({"COST_MODE": mode}).cost_mode == "free"

def test_production_requires_explicit_opt_in():
    with pytest.raises(ConfigurationError, match="requires ALLOW_PAID=true"):
        AppConfig.from_mapping({"COST_MODE": "production"})

def test_production_with_opt_in():
    assert AppConfig.from_mapping({"COST_MODE": "production", "ALLOW_PAID": "true"}).allow_paid is True

@pytest.mark.parametrize("mode", ["", "paid", "staging"])
def test_invalid_mode(mode):
    with pytest.raises(ConfigurationError): AppConfig.from_mapping({"COST_MODE": mode})

@pytest.mark.parametrize("paid", ["yes", "1", "maybe", ""])
def test_invalid_paid_value(paid):
    with pytest.raises(ConfigurationError): AppConfig.from_mapping({"ALLOW_PAID": paid})

def test_reads_environment(monkeypatch):
    monkeypatch.setenv("COST_MODE", "free")
    monkeypatch.setenv("ALLOW_PAID", "false")
    assert load_config() == AppConfig("free", False)
