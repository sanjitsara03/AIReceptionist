"""
Shared test fixtures.

Strategy:
  - Use a dedicated test database (`receptionist_test`).
  - On session startup: drop & re-create all tables from the SQLAlchemy metadata.
  - For each test: wrap in a transaction that's rolled back at the end, so tests
    can't pollute each other.
  - Override FastAPI's `get_db` to hand out sessions bound to the test transaction.
  - Override `get_current_business_id` so we don't need real Auth0 JWTs in tests.
"""

import os
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

# Point the test process at a separate DB *before* any app code imports it.
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://receptionist:receptionist@localhost:5432/receptionist_test",
)
os.environ["DATABASE_URL"] = TEST_DB_URL

# Force-disable Sentry in tests, even if the local .env has a real DSN.
# Otherwise every CI run + every local test run would spam the real Sentry
# project with fake errors from `test_unhandled_exception_returns_envelope`.
os.environ["SENTRY_DSN"] = ""

# Disable production safety guards in tests:
#   - Twilio signature validation would require us to sign every test payload.
#   - Rate limits would make tests order-dependent + flaky.
# These flags are read by app.config and app.limiter at import time.
os.environ["VALIDATE_TWILIO_SIGNATURE"] = "false"
os.environ["RATE_LIMITS_ENABLED"] = "false"

from app.database import Base, get_db          # noqa: E402
from app.auth import get_current_business_id, get_current_auth0_id   # noqa: E402
from app.main import app                       # noqa: E402
from app.models import Business, Technician, Customer  # noqa: E402


# Module-level engine — one connection pool for the whole test session
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Drop and recreate all tables once for the whole test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db(setup_database) -> AsyncSession:
    """A clean session per test. Truncates all tables before the test runs."""
    async with TestSessionLocal() as session:
        # Truncate everything — fast and gives a clean slate without dropping tables
        from sqlalchemy import text
        await session.execute(text(
            "TRUNCATE invites, messages, conversations, jobs, time_slots, "
            "customers, technicians, businesses RESTART IDENTITY CASCADE"
        ))
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def client(db):
    """
    HTTP client wired to the test DB and a stub auth identity.

    By default the client is authenticated as the owner of business_id=1.
    Tests that need an unauthenticated request can use the raw `app` instead.
    """
    async def _override_get_db():
        async with TestSessionLocal() as session:
            yield session

    async def _override_business_id():
        return 1

    async def _override_auth0_id():
        return "test|user-1"

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_business_id] = _override_business_id
    app.dependency_overrides[get_current_auth0_id] = _override_auth0_id

    async with LifespanManager(app):
        # raise_app_exceptions=False — match production behavior where the
        # global exception handler converts crashes to 500 responses instead
        # of re-raising into the test caller.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def business(db) -> Business:
    """A standard test business + 2 technicians + 1 customer, with id=1."""
    biz = Business(
        name="Test Plumbing",
        twilio_number="+15550001000",
        services="Drain cleaning, leak repair",
        hours="Mon-Fri 9-5",
        address="1 Test St",
        owner_auth0_id="test|user-1",
    )
    db.add(biz)
    await db.flush()

    db.add_all([
        Technician(business_id=biz.id, name="Alice Tester", phone="+15550001001"),
        Technician(business_id=biz.id, name="Bob Tester",   phone="+15550001002"),
        Customer(  business_id=biz.id, name="Casey Customer", phone="+15550009999"),
    ])
    await db.commit()
    return biz
