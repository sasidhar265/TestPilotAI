from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"
    json_logs: bool = True
    copilot_github_token: str = ""
    copilot_model: str = ""
    copilot_timeout_seconds: float = 300
    copilot_working_directory: Path = Path.cwd()
    agent_profile: str = "auto-finance-quotation"
    organizational_memory_enabled: bool = True
    organizational_memory_path: Path = Path(".agent-memory/test_suites.db")
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
