import json
from pathlib import Path

import pytest

from app.config import Settings
from app.user_secrets import DEFAULT_USER_SECRETS_ID


@pytest.fixture
def secret_store(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("API_AUTH_TOKEN", "USER_SECRETS_ENABLED", "USER_SECRETS_ID", "ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".microsoft" / "usersecrets" / DEFAULT_USER_SECRETS_ID / "secrets.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"API_AUTH_TOKEN": "from-user-secrets", "APP_USERNAME": "local-user"})
    )
    return path


def test_user_secrets_require_explicit_opt_in(secret_store):
    assert not Settings(_env_file=None).api_auth_token_value
    settings = Settings(_env_file=None, user_secrets_enabled=True)
    assert settings.api_auth_token_value == "from-user-secrets"
    assert settings.app_username == "local-user"


def test_precedence_constructor_environment_secrets_dotenv(secret_store, tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("USER_SECRETS_ENABLED=true\nAPI_AUTH_TOKEN=from-dotenv\n")
    assert Settings(_env_file=dotenv).api_auth_token_value == "from-user-secrets"
    monkeypatch.setenv("API_AUTH_TOKEN", "from-environment")
    assert Settings(_env_file=dotenv).api_auth_token_value == "from-environment"
    assert Settings(_env_file=dotenv, api_auth_token="explicit").api_auth_token_value == "explicit"
    monkeypatch.setenv("API_AUTH_TOKEN", "")
    assert Settings(_env_file=dotenv).api_auth_token_value == ""


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_hosted_environments_do_not_read_local_secrets(secret_store, environment):
    secret_store.write_text("invalid-json-private-content")
    settings = Settings(
        _env_file=None,
        environment=environment,
        user_secrets_enabled=True,
        api_auth_token="x" * 32,
    )
    assert settings.api_auth_token_value == "x" * 32


def test_missing_store_is_optional_and_invalid_json_does_not_expose_contents(secret_store):
    secret_store.unlink()
    assert not Settings(_env_file=None, user_secrets_enabled=True).api_auth_token_value
    secret_store.write_text("private-content")
    with pytest.raises(ValueError, match="Cannot read Microsoft User Secrets") as error:
        Settings(_env_file=None, user_secrets_enabled=True)
    assert "private-content" not in str(error.value)


def test_store_cannot_enable_itself_or_change_environment(secret_store):
    secret_store.write_text(
        json.dumps(
            {
                "ENVIRONMENT": "production",
                "USER_SECRETS_ID": "other-store",
                "USER_SECRETS_ENABLED": False,
                "API_AUTH_TOKEN": "local-value",
            }
        )
    )
    settings = Settings(_env_file=None, user_secrets_enabled=True)
    assert settings.environment == "development"
    assert settings.user_secrets_id == DEFAULT_USER_SECRETS_ID
    assert settings.user_secrets_enabled
    assert settings.api_auth_token_value == "local-value"


def test_invalid_store_id_is_rejected(secret_store):
    with pytest.raises(ValueError, match="simple store identifier"):
        Settings(_env_file=None, user_secrets_enabled=True, user_secrets_id="../outside")
