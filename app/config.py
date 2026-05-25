# Defines the config settings for the application

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    secret_key: str
    environment: str = "development"
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    anthropic_api_key: str
    auth0_domain: str
    auth0_audience: str
    admin_secret: str

    # --- Production readiness additions (all safe defaults for local dev) ---
    sentry_dsn: str | None = None
    allowed_origins: str = "http://localhost:5173,http://localhost:5174"
    frontend_url: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated allowed_origins into a clean list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
