"""Isolated full-app server used by opt-in browser regression tests."""

import os
from pathlib import Path


def create_app():
    import app.config

    directory = Path(os.environ["QUALITY_UI_TEST_DIRECTORY"])
    configuration = app.config.Settings(
        _env_file=None,
        runtime_config_path=None,
        environment="development",
        user_secrets_enabled=False,
        app_username="ui.admin",
        app_password="Isolated-ui-password-123!",
        session_secret="isolated-browser-session-secret-1234567890",
        api_auth_token="",
        user_database_path=directory / "users.db",
        organizational_memory_path=directory / "memory.db",
        accepted_output_directory=directory / "output",
        organizational_memory_enabled=False,
        log_file_path=None,
        log_level="ERROR",
        detailed_logs_enabled=False,
        openai_api_key="",
        gemini_api_key="",
        copilot_github_token="",
    )
    def isolated_settings():
        from app.domain_profiles import effective_settings
        return effective_settings(configuration)

    app.config.get_settings = isolated_settings
    from app.main import app

    return app
