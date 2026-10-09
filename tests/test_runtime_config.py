from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.model_policy import CODEX_MODEL, COPILOT_MODEL


@pytest.fixture
def runtime_file(tmp_path, monkeypatch):
    for name in (
        "RUNTIME_CONFIG_PATH",
        "MODEL_DIRECTED_RUNTIME_ENABLED",
        "TREE_SITTER_DIAGNOSTICS_ENABLED",
        "USER_SECRETS_ENABLED",
        "ORGANIZATIONAL_MEMORY_ENABLED",
        "AUTOMATION_SKIP_BUILD",
        "JSON_LOGS",
        "CODEX_MODEL",
        "COPILOT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "runtime.toml"
    path.write_text(
        "model_directed_runtime_enabled = false\ntree_sitter_diagnostics_enabled = false\n"
    )
    return path


def test_runtime_config_controls_existing_flags_and_options(runtime_file):
    runtime_file.write_text(runtime_file.read_text() + "automation_timeout_seconds = 120\n")
    settings = Settings(_env_file=None, runtime_config_path=runtime_file)
    assert not settings.model_directed_runtime_enabled
    assert not settings.tree_sitter_diagnostics_enabled
    assert settings.automation_timeout_seconds == 120


def test_settings_precedence_is_preserved(runtime_file, tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("MODEL_DIRECTED_RUNTIME_ENABLED=true\n")
    assert Settings(
        _env_file=dotenv, runtime_config_path=runtime_file
    ).model_directed_runtime_enabled
    monkeypatch.setenv("MODEL_DIRECTED_RUNTIME_ENABLED", "false")
    assert not Settings(
        _env_file=dotenv, runtime_config_path=runtime_file
    ).model_directed_runtime_enabled
    assert Settings(
        _env_file=dotenv, runtime_config_path=runtime_file, model_directed_runtime_enabled=True
    ).model_directed_runtime_enabled


def test_config_file_path_can_come_from_environment_or_dotenv(runtime_file, tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"RUNTIME_CONFIG_PATH={runtime_file}\n")
    assert not Settings(_env_file=dotenv).model_directed_runtime_enabled
    other = tmp_path / "other.toml"
    other.write_text("model_directed_runtime_enabled = true\n")
    monkeypatch.setenv("RUNTIME_CONFIG_PATH", str(other))
    assert Settings(_env_file=dotenv).model_directed_runtime_enabled
    assert not Settings(
        _env_file=dotenv, runtime_config_path=runtime_file
    ).model_directed_runtime_enabled


def test_config_edit_is_loaded_by_new_settings_instances(runtime_file):
    assert not Settings(
        _env_file=None, runtime_config_path=runtime_file
    ).tree_sitter_diagnostics_enabled
    runtime_file.write_text("tree_sitter_diagnostics_enabled = true\n")
    assert Settings(
        _env_file=None, runtime_config_path=runtime_file
    ).tree_sitter_diagnostics_enabled


def test_explicitly_disabling_file_uses_normal_settings_defaults(runtime_file):
    assert Settings(_env_file=None, runtime_config_path=None).tree_sitter_diagnostics_enabled


@pytest.mark.parametrize(
    "contents,message",
    [
        ("unknown_toggle = true\n", "Unknown runtime configuration options"),
        ('api_auth_token = "private-test-token"\n', "cannot contain credentials"),
        ('copilot_github_token = "private-test-token"\n', "cannot contain credentials"),
        ('runtime_config_path = "another.toml"\n', "change its own path"),
        ("tree_sitter_diagnostics_enabled = [", "check TOML syntax"),
    ],
)
def test_invalid_files_fail_without_exposing_values(runtime_file, contents, message):
    runtime_file.write_text(contents)
    with pytest.raises(ValueError, match=message) as error:
        Settings(_env_file=None, runtime_config_path=runtime_file)
    assert "private-test-token" not in str(error.value)


def test_missing_file_is_not_silently_ignored(runtime_file):
    with pytest.raises(ValueError, match="does not exist"):
        Settings(_env_file=None, runtime_config_path=runtime_file.with_name("missing.toml"))


def test_flag_types_and_production_policy_are_validated(runtime_file):
    runtime_file.write_text('tree_sitter_diagnostics_enabled = "maybe"\n')
    with pytest.raises(ValidationError, match="tree_sitter_diagnostics_enabled"):
        Settings(_env_file=None, runtime_config_path=runtime_file)
    runtime_file.write_text("json_logs = false\n")
    with pytest.raises(ValidationError, match="JSON_LOGS must remain enabled"):
        Settings(
            _env_file=None,
            runtime_config_path=runtime_file,
            environment="production",
            api_auth_token="a" * 32,
            app_password="",
            session_secret="",
        )


def test_toml_cannot_override_mandatory_models(runtime_file):
    runtime_file.write_text('codex_model = "other"\ncopilot_model = "other"\n')
    settings = Settings(_env_file=None, runtime_config_path=runtime_file)
    assert settings.codex_model == CODEX_MODEL
    assert settings.copilot_model == COPILOT_MODEL


def test_user_secrets_opt_in_can_come_from_toml(runtime_file, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: runtime_file.parent)
    store = (
        runtime_file.parent / ".microsoft/usersecrets/quality-lifecycle-studio-local/secrets.json"
    )
    store.parent.mkdir(parents=True)
    store.write_text('{"APP_USERNAME":"from-secrets"}')
    runtime_file.write_text("user_secrets_enabled = true\n")
    settings = Settings(_env_file=None, runtime_config_path=runtime_file, environment="development")
    assert settings.user_secrets_enabled
    assert settings.app_username == "from-secrets"


@pytest.mark.parametrize("enabled", [False, True])
def test_coordinator_flag_changes_actual_pipeline_composition(runtime_file, monkeypatch, enabled):
    from app.dependencies import get_agent_registry, get_multi_agent_pipeline

    sentinel = object()
    monkeypatch.setattr("app.dependencies.AgentRuntime", lambda *args: sentinel)
    runtime_file.write_text(
        f"model_directed_runtime_enabled = {str(enabled).lower()}\n"
        "organizational_memory_enabled = false\n"
    )
    settings = Settings(_env_file=None, runtime_config_path=runtime_file)
    pipeline = get_multi_agent_pipeline(get_agent_registry(settings), settings)
    assert pipeline.runtime is (sentinel if enabled else None)
