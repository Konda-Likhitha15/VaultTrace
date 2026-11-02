"""Environment-based application settings."""

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
    admin_bootstrap_email: str | None = None
    admin_bootstrap_username: str | None = None
    admin_bootstrap_password: str | None = None
    admin_bootstrap_full_name: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
