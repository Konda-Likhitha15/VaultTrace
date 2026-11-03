"""Environment-based application settings."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "VaultTrace"
    app_env: str = "development"
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    frontend_origin: str = "http://localhost:5173"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    otp_hash_secret: str | None = None
    otp_expiration_minutes: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_sends_per_hour: int = 5
    otp_max_attempts: int = 5
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "vaulttrace@localhost"
    smtp_starttls: bool = False
    smtp_use_ssl: bool = False
    smtp_from_email: str | None = None
    smtp_use_tls: bool | None = None
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
