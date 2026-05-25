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

    # --- Abuse / cost-control safety ---
    # Validate the X-Twilio-Signature on inbound webhooks. Disable only in tests.
    validate_twilio_signature: bool = True
    # The PUBLIC https URL the webhooks live at — this is the exact string
    # Twilio's HMAC is computed against. If unset we fall back to reconstructing
    # from X-Forwarded-* headers, but Railway's proxy can make that brittle, so
    # setting this explicitly in prod is strongly recommended.
    # e.g. "https://aireceptionist-production-8ab7.up.railway.app"
    webhook_base_url: str | None = None
    # Hard ceiling on inbound AI-handled messages per business per UTC day.
    # Hit → the agent is skipped and we reply with a polite "limit reached" note.
    daily_message_limit_per_business: int = 500

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated allowed_origins into a clean list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def async_database_url(self) -> str:
        """
        SQLAlchemy + asyncpg requires `postgresql+asyncpg://` URLs.
        Railway's Postgres add-on injects `postgresql://` — coerce so both
        local dev (already +asyncpg) and Railway (plain) work transparently.
        """
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
