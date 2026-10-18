import pytest
from jarvis.config import AppConfig, ConfigurationError, load_config

def test_defaults_to_free():
    assert AppConfig.from_mapping({}) == AppConfig("free", False)

def test_bedrock_defaults_are_explicit_but_region_is_not_assumed():
    config = AppConfig.from_mapping({})
    assert config.bedrock_model_id == "amazon.nova-lite-v1:0"
    assert config.bedrock_region is None

@pytest.mark.parametrize("field", ["BEDROCK_MODEL_ID", "BEDROCK_REGION"])
def test_blank_bedrock_configuration_is_rejected(field):
    with pytest.raises(ConfigurationError):
        AppConfig.from_mapping({field: " "})

def test_bedrock_region_can_be_configured_explicitly():
    config = AppConfig.from_mapping({
        "BEDROCK_MODEL_ID": "us.amazon.nova-lite-v1:0",
        "BEDROCK_REGION": "us-east-1",
    })
    assert config.bedrock_model_id == "us.amazon.nova-lite-v1:0"
    assert config.bedrock_region == "us-east-1"

@pytest.mark.parametrize("field", ["AWS_REGION", "AWS_DEFAULT_REGION"])
def test_standard_aws_region_environment_is_used_as_fallback(field):
    config = AppConfig.from_mapping({field: "us-east-1"})
    assert config.bedrock_region == "us-east-1"

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
