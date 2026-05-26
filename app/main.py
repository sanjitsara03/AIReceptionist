import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.config import settings
from app.limiter import limiter
from app.middleware.errors import unhandled_exception_handler
from app.routes import webhooks, jobs, customers, dashboard, technicians, conversations, businesses, auth, invites, events, timeslots, admin
from app.scheduler import start_scheduler, stop_scheduler
from app.sentry import init_sentry

# Initialize Sentry as early as possible — even import-time errors should be
# captured. No-op if SENTRY_DSN is unset.
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Surface the resolved webhook base URL so a typo in WEBHOOK_BASE_URL
    # (trailing slash, http vs https, wrong host) is obvious in startup logs
    # rather than silently 403-ing every Twilio webhook.
    log = logging.getLogger("startup")
    if settings.validate_twilio_signature:
        if settings.webhook_base_url:
            log.info("Twilio signature validation: STRICT, base=%s", settings.webhook_base_url)
        else:
            log.warning(
                "Twilio signature validation: enabled but WEBHOOK_BASE_URL unset — "
                "falling back to X-Forwarded-* reconstruction. Set WEBHOOK_BASE_URL in prod."
            )
    else:
        log.warning("Twilio signature validation is DISABLED — only acceptable in tests.")

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="AI Receptionist", lifespan=lifespan)

# Rate limiting — slowapi needs the limiter on app.state, plus a handler that
# turns RateLimitExceeded into a 429 response with a Retry-After header.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Catch all for unexpected exceptions
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(webhooks.router)
app.include_router(auth.router)
app.include_router(invites.router)
app.include_router(businesses.router)
app.include_router(jobs.router)
app.include_router(timeslots.router)
app.include_router(customers.router)
app.include_router(technicians.router)
app.include_router(conversations.router)
app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"data": {"status": "ok"}, "error": None}
