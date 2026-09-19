"""Development-only access to the Microsoft User Secrets JSON store."""

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

DEFAULT_USER_SECRETS_ID = "quality-lifecycle-studio-local"


class UserSecretsSource(PydanticBaseSettingsSource):
    def __init__(
        self, settings_cls: type[BaseSettings], dotenv: PydanticBaseSettingsSource
    ) -> None:
        super().__init__(settings_cls)
        self.dotenv = dotenv

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        # Consult .env for opt-in controls without giving its credential values higher
        # priority than User Secrets. Constructor arguments and process env win.
        controls = self.dotenv() | self.current_state
        enabled = str(controls.get("user_secrets_enabled", False)).casefold() in {"true", "1"}
        if (
            not enabled
            or str(controls.get("environment", "development")).casefold() != "development"
        ):
            return {}
        identifier = str(controls.get("user_secrets_id", DEFAULT_USER_SECRETS_ID))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identifier) or identifier in {".", ".."}:
            raise ValueError("USER_SECRETS_ID must be a simple store identifier")
        if os.name == "nt":
            root = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            path = root / "Microsoft" / "UserSecrets" / identifier / "secrets.json"
        else:
            path = Path.home() / ".microsoft" / "usersecrets" / identifier / "secrets.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise ValueError(
                "Cannot read Microsoft User Secrets; check secrets.json locally"
            ) from None
        if not isinstance(data, dict):
            raise ValueError("Microsoft User Secrets must contain a JSON object")
        controls_only = {"environment", "user_secrets_enabled", "user_secrets_id"}
        return {
            key.casefold(): value
            for key, value in data.items()
            if key.casefold() in self.settings_cls.model_fields
            and key.casefold() not in controls_only
        }
