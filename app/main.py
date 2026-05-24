from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import webhooks, jobs, customers, dashboard
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="AI Receptionist", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router)
app.include_router(jobs.router)
app.include_router(customers.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"data": {"status": "ok"}, "error": None}
