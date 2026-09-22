from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from app.user_secrets import DEFAULT_USER_SECRETS_ID, UserSecretsSource


class Settings(BaseSettings):
    environment: str = "development"
    user_secrets_enabled: bool = False
    user_secrets_id: str = DEFAULT_USER_SECRETS_ID
    quality_lifecycle_base_url: str = ""
    log_level: str = "INFO"
    json_logs: bool = True
    api_auth_token: SecretStr = SecretStr("")
    app_username: str = "admin"
    app_display_name: str = ""
    user_database_path: Path = Path(".agent-memory/users.db")
    app_password: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    max_request_body_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    max_upload_bytes: int = Field(default=15 * 1024 * 1024, ge=1024)
    max_concurrent_requests: int = Field(default=20, ge=1, le=1000)
    max_concurrent_generations: int = Field(default=2, ge=1, le=100)
    automation_project_path: Path = Path("automation/QualityLifecycle.Automation.csproj")
    api_base_url: str = ""
    api_bearer_token: SecretStr = SecretStr("")
    api_fixture_file: str = ""
    api_request_method: str = ""
    api_request_path: str = ""
    automation_timeout_seconds: float = Field(default=900, gt=0, le=3600)
    automation_skip_build: bool = False
    automation_test_timeout_seconds: int = Field(default=60, ge=1, le=3600)
    allure_executable: str = "allure"
    allure_timeout_seconds: float = Field(default=120, gt=0, le=600)
    request_queue_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    model_directed_runtime_enabled: bool = True
    copilot_github_token: str = ""
    copilot_model: str = ""
    copilot_timeout_seconds: float = 300
    copilot_coordinator_timeout_seconds: float = Field(default=1800, gt=0, le=3600)
    copilot_working_directory: Path = Path.cwd()
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.4"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=300, gt=0, le=1800)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = Field(default=300, gt=0, le=1800)
    codex_executable: str = "codex"
    codex_model: str = ""
    codex_timeout_seconds: float = Field(default=300, gt=0, le=1800)
    codex_artifact_timeout_seconds: float = Field(default=900, gt=0, le=1800)
    agent_profile: str = "auto-finance-quotation"
    requirements_baseline_path: Path = Path("workspace/requirements-baseline.json")
    organizational_memory_enabled: bool = True
    organizational_memory_path: Path = Path(".agent-memory/test_suites.db")
    accepted_output_directory: Path = Path("output")
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_acceptance_criteria_fields: str = ""

    @property
    def jira_acceptance_criteria_field_list(self) -> list[str]:
        """Optional Jira custom-field IDs/names that contain acceptance criteria."""
        return [
            value.strip()
            for value in self.jira_acceptance_criteria_fields.split(",")
            if value.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            UserSecretsSource(settings_cls, dotenv_settings),
            dotenv_settings,
            file_secret_settings,
        )

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() == "production"

    @property
    def api_auth_token_value(self) -> str:
        return self.api_auth_token.get_secret_value()

    @property
    def app_password_value(self) -> str:
        return self.app_password.get_secret_value()

    @property
    def session_secret_value(self) -> str:
        return self.session_secret.get_secret_value()

    @property
    def openai_api_key_value(self) -> str:
        return self.openai_api_key.get_secret_value()

    @property
    def gemini_api_key_value(self) -> str:
        return self.gemini_api_key.get_secret_value()

    @property
    def browser_login_enabled(self) -> bool:
        return bool(self.app_password_value and self.session_secret_value)

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
            if bool(self.app_password_value) != bool(self.session_secret_value):
                raise ValueError(
                    "APP_PASSWORD and SESSION_SECRET must either both be configured "
                    "or both be empty"
                )
            if self.browser_login_enabled and (
                len(self.app_password_value) < 12 or len(self.session_secret_value) < 32
            ):
                raise ValueError(
                    "APP_PASSWORD must contain at least 12 characters and "
                    "SESSION_SECRET at least 32"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
