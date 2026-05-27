"""
Sentry initialization.

Call `init_sentry()` once at startup (from main.py). If `SENTRY_DSN` is unset
the call is a no-op, so local dev and tests don't need a real Sentry project.

When configured, sentry-sdk auto-detects FastAPI, SQLAlchemy, asyncio and
hooks them — every unhandled exception bubbling up through the FastAPI
middleware stack (and every explicit `sentry_sdk.capture_exception(...)`)
gets reported with full traceback + request context.
"""

import sentry_sdk

from app.config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # Errors only. Bump to e.g. 0.1 to sample 10% of requests for performance monitoring ; but that uses Sentry quota fast.
        traces_sample_rate=0.0,
        # Don't send IPs / Authorization headers / cookies by default. Use sentry_sdk.set_user(...) explicitly if you want user context.
        send_default_pii=False,
    )
