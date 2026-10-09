"""Validated, non-secret runtime settings from a shared TOML file."""

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, TomlConfigSettingsSource

DEFAULT_RUNTIME_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "workspace/runtime-config.toml"
)
_SECRET_FIELDS = frozenset(
    {
        "api_auth_token",
        "app_password",
        "session_secret",
        "api_bearer_token",
        "organizational_memory_encryption_key",
        "copilot_github_token",
        "openai_api_key",
        "gemini_api_key",
        "jira_api_token",
    }
)


class RuntimeConfigSource(TomlConfigSettingsSource):
    def __init__(
        self,
        settings_cls: type[BaseSettings],
        init: PydanticBaseSettingsSource,
        env: PydanticBaseSettingsSource,
        dotenv: PydanticBaseSettingsSource,
    ) -> None:
        controls = dotenv() | env() | init()
        selected = controls.get("runtime_config_path", DEFAULT_RUNTIME_CONFIG_PATH)
        path = Path(selected) if selected is not None else None
        if path is not None and not path.is_file():
            raise ValueError(f"Runtime configuration file does not exist: {path}")
        try:
            super().__init__(settings_cls, toml_file=path)
        except (OSError, ValueError):
            raise ValueError(
                "Cannot read runtime configuration; check TOML syntax and permissions"
            ) from None

    def __call__(self) -> dict[str, Any]:
        values = super().__call__()
        unknown = set(values) - self.settings_cls.model_fields.keys()
        if unknown:
            raise ValueError("Unknown runtime configuration options: " + ", ".join(sorted(unknown)))
        if set(values) & (_SECRET_FIELDS | {"runtime_config_path"}):
            raise ValueError(
                "Runtime configuration cannot contain credentials or change its own path"
            )
        return values
