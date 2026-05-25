from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.middleware.errors import unhandled_exception_handler
from app.routes import webhooks, jobs, customers, dashboard, technicians, conversations, businesses, auth, invites, events, timeslots
from app.scheduler import start_scheduler, stop_scheduler
from app.sentry import init_sentry

# Initialize Sentry as early as possible — even import-time errors should be
# captured. No-op if SENTRY_DSN is unset.
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="AI Receptionist", lifespan=lifespan)

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


@app.get("/health")
async def health():
    return {"data": {"status": "ok"}, "error": None}
