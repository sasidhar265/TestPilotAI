from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"
    json_logs: bool = True
    api_auth_token: SecretStr = SecretStr("")
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    max_request_body_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    max_upload_bytes: int = Field(default=15 * 1024 * 1024, ge=1024)
    max_concurrent_requests: int = Field(default=20, ge=1, le=1000)
    max_concurrent_generations: int = Field(default=2, ge=1, le=100)
    request_queue_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    copilot_github_token: str = ""
    copilot_model: str = ""
    copilot_timeout_seconds: float = 300
    copilot_coordinator_timeout_seconds: float = Field(default=1800, gt=0, le=3600)
    copilot_working_directory: Path = Path.cwd()
    agent_profile: str = "auto-finance-quotation"
    organizational_memory_enabled: bool = True
    organizational_memory_path: Path = Path(".agent-memory/test_suites.db")
    accepted_output_directory: Path = Path("output")
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() == "production"

    @property
    def api_auth_token_value(self) -> str:
        return self.api_auth_token.get_secret_value()

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @model_validator(mode="after")
    def validate_deployment_safety(self) -> "Settings":
        if self.max_upload_bytes >= self.max_request_body_bytes:
            raise ValueError("MAX_UPLOAD_BYTES must be smaller than MAX_REQUEST_BODY_BYTES")
        minimum_coordinator_budget = self.copilot_timeout_seconds * 4
        if self.copilot_coordinator_timeout_seconds < minimum_coordinator_budget:
            raise ValueError(
                "COPILOT_COORDINATOR_TIMEOUT_SECONDS must be at least four times "
                "COPILOT_TIMEOUT_SECONDS to cover both specialist routes and revisions"
            )
        if self.is_production:
            token = self.api_auth_token_value
            if len(token) < 32:
                raise ValueError("API_AUTH_TOKEN must contain at least 32 characters in production")
            if not self.allowed_host_list or "*" in self.allowed_host_list:
                raise ValueError("ALLOWED_HOSTS must contain explicit hosts in production")
            if not self.json_logs:
                raise ValueError("JSON_LOGS must remain enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
