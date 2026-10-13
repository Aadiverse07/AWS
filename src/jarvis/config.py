from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Mapping

class ConfigurationError(ValueError):
    """Invalid or unsafe application configuration."""

@dataclass(frozen=True, slots=True)
class AppConfig:
    cost_mode: str = "free"
    allow_paid: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "AppConfig":
        mode = values.get("COST_MODE", "free")
        paid = values.get("ALLOW_PAID", "false")
        if not isinstance(mode, str) or mode.strip().lower() not in {"free", "production"}:
            raise ConfigurationError("COST_MODE must be free or production.")
        if not isinstance(paid, str) or paid.strip().lower() not in {"true", "false"}:
            raise ConfigurationError("ALLOW_PAID must be true or false.")
        mode, paid = mode.strip().lower(), paid.strip().lower() == "true"
        if mode == "production" and not paid:
            raise ConfigurationError("COST_MODE=production requires ALLOW_PAID=true.")
        return cls(cost_mode=mode, allow_paid=paid)

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls.from_mapping(os.environ)

def load_config() -> AppConfig:
    """Load validated configuration; call this from application startup."""
    return AppConfig.from_env()
