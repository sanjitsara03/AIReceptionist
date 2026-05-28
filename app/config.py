# Defines the config settings for the application

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

# All user facing times (texts, voice replies, dashboard "today" cutoff, digest cron) are rendered in this zone. Storage stays in UTC.
BUSINESS_TZ = ZoneInfo("America/Los_Angeles")


def pt_today_bounds() -> tuple[datetime, datetime]:
    """Return [PT-midnight today, PT-midnight tomorrow), expressed in UTC.

    Use this anywhere a query needs to ask "rows from today" — UTC midnight
    rolls over at 5pm PT, which surprises everyone.
    """
    now_pt = datetime.now(BUSINESS_TZ)
    start_pt = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    end_pt = start_pt + timedelta(days=1)
    return start_pt.astimezone(timezone.utc), end_pt.astimezone(timezone.utc)


def fmt_pt(dt: datetime, fmt: str) -> str:
    """Render a datetime in PT using strftime.

    Naive datetimes are assumed to be UTC (our DB stores UTC instants in
    tz-aware columns, but a few code paths build datetimes without tzinfo).
    Without this assumption, `astimezone` on a naive value silently uses
    the system's local TZ — fine on a CA laptop, wrong on a UTC container.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BUSINESS_TZ).strftime(fmt)


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

    # Production readiness additions (all safe defaults for local dev)
    sentry_dsn: str | None = None
    allowed_origins: str = "http://localhost:5173,http://localhost:5174"
    frontend_url: str = "http://localhost:5173"

    # Abuse / cost control safety --- Validate the X Twilio Signature on inbound webhooks. Disable only in tests.
    validate_twilio_signature: bool = True
    # The PUBLIC https URL the webhooks live at ; this is the exact string Twilio's HMAC is computed against. If unset we fall back to reconstructing from X Forwarded-* headers, but Railway's proxy can make that brittle, so setting this explicitly in prod is strongly recommended. e.g. "https://aireceptionist production 8ab7.up.railway.app"
    webhook_base_url: str | None = None
    # Hard ceiling on inbound AI handled messages per business per UTC day. Hit → the agent is skipped and we reply with a polite "limit reached" note.
    daily_message_limit_per_business: int = 500
    # Comma separated E.164 phone numbers allowed to interact with the AI. When set, any inbound SMS/voice from a number NOT in this list is dropped with a polite "demo line" reply ; no LLM run, no booking possible. Leave blank to allow all callers (production / approved A2P mode).
    sms_allowlist: str = ""
    # Mask customer phone numbers in API responses so they aren't exposed via the shared demo dashboard. DB keeps the real number so the agent can still text/call back. Set true in any deployment where the dashboard credentials are publicly shared.
    mask_customer_phones: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated allowed_origins into a clean list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sms_allowlist_set(self) -> frozenset[str]:
        """Parse SMS_ALLOWLIST into a normalized E.164 set. Empty = allow all."""
        return frozenset(n.strip() for n in self.sms_allowlist.split(",") if n.strip())

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
