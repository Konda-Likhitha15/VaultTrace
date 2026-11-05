"""Environment-based application settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "VaultTrace"
    app_env: str = "development"
    database_url: str
    production_database_url: SecretStr | None = None
    alembic_use_production_database: bool = False
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    frontend_origin: str = "http://localhost:5173"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    otp_hash_secret: str | None = None
    otp_expiration_minutes: int = Field(default=5, ge=1)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=0)
    otp_max_sends_per_hour: int = Field(default=10, ge=1)
    otp_max_attempts: int = Field(default=5, ge=1)
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "vaulttrace@localhost"
    smtp_starttls: bool = False
    smtp_use_ssl: bool = False
    smtp_from_email: str | None = None
    smtp_use_tls: bool | None = None
    email_provider: Literal["mailpit", "gmail_api"] = "mailpit"
    gmail_client_id: str | None = None
    gmail_client_secret: SecretStr | None = None
    gmail_refresh_token: SecretStr | None = None
    gmail_sender_email: str | None = None
    password_reset_token_expire_minutes: int = 10
    storage_provider: Literal["local", "supabase"] | None = None
    local_storage_path: Path = Path("./private_storage")
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = "vaulttrace-documents"
    document_max_upload_bytes: int = 5_242_880
    document_allowed_extensions: str = "pdf,png,jpg,jpeg,txt,csv,docx,xlsx"
    admin_bootstrap_email: str | None = None
    admin_bootstrap_username: str | None = None
    admin_bootstrap_password: str | None = None
    admin_bootstrap_full_name: str | None = None
    admin2_email: str | None = None
    admin2_username: str | None = None
    admin2_password: str | None = None
    admin2_full_name: str | None = None

    @model_validator(mode="after")
    def choose_storage_provider(self) -> "Settings":
        """Default local environments to disk and production environments to Supabase."""
        is_production = self.app_env.lower() in {"prod", "production"}
        if is_production and self.storage_provider == "local":
            raise ValueError("STORAGE_PROVIDER must be 'supabase' when APP_ENV is production.")
        if self.storage_provider is None:
            self.storage_provider = "supabase" if is_production else "local"
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
