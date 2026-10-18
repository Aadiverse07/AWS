from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"

class ConfigurationError(ValueError):
    """Invalid or unsafe application configuration."""

@dataclass(frozen=True, slots=True)
class AppConfig:
    cost_mode: str = "free"
    allow_paid: bool = False
    bedrock_model_id: str = DEFAULT_BEDROCK_MODEL_ID
    bedrock_region: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "AppConfig":
        mode = values.get("COST_MODE", "free")
        paid = values.get("ALLOW_PAID", "false")
        model_id = values.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
        region = values.get(
            "BEDROCK_REGION",
            values.get("AWS_REGION", values.get("AWS_DEFAULT_REGION")),
        )
        if not isinstance(mode, str) or mode.strip().lower() not in {"free", "production"}:
            raise ConfigurationError("COST_MODE must be free or production.")
        if not isinstance(paid, str) or paid.strip().lower() not in {"true", "false"}:
            raise ConfigurationError("ALLOW_PAID must be true or false.")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ConfigurationError("BEDROCK_MODEL_ID must not be blank.")
        if region is not None and (not isinstance(region, str) or not region.strip()):
            raise ConfigurationError("BEDROCK_REGION must not be blank when set.")
        mode, paid = mode.strip().lower(), paid.strip().lower() == "true"
        if mode == "production" and not paid:
            raise ConfigurationError("COST_MODE=production requires ALLOW_PAID=true.")
        return cls(
            cost_mode=mode,
            allow_paid=paid,
            bedrock_model_id=model_id.strip(),
            bedrock_region=region.strip() if region else None,
        )

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls.from_mapping(os.environ)

def load_config() -> AppConfig:
    """Load validated configuration; call this from application startup."""
    return AppConfig.from_env()
