"""Disposable backend for UI tests; never loads the user's .env or accounts."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app.config  # noqa: E402

with TemporaryDirectory(prefix="afq-mobile-ui-") as directory:
    settings = app.config.Settings(
        _env_file=None,
        user_secrets_enabled=False,
        environment="development",
        app_username="mobile-tester",
        app_password="Local-mobile-test-only-123!",
        session_secret="local-mobile-ui-test-session-secret-only-123456789",
        api_auth_token="",
        user_database_path=Path(directory) / "users.db",
        organizational_memory_path=Path(directory) / "memory.db",
        accepted_output_directory=Path(directory) / "output",
        organizational_memory_enabled=False,
        allowed_hosts="localhost,127.0.0.1",
        temporary_guest_access_until=None,
        log_level="WARNING",
        codex_executable="mobile-ui-test-no-provider",
        openai_api_key="",
        gemini_api_key="",
        copilot_github_token="",
    )
    app.config.get_settings = lambda: settings
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, log_level="warning")
