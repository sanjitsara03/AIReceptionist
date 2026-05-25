"""Tests for the global unhandled-exception handler."""

from app.main import app
from app.auth import get_current_business_id


async def test_unhandled_exception_returns_envelope(client):
    """A bug in a route handler / dependency should produce our standard
    `{"data": null, "error": "..."}` envelope with status 500 — not leak the
    exception message and not return Starlette's default text/plain 500 page."""

    async def simulated_bug():
        raise ValueError("internal detail that should NOT leak")

    # Replace the test's normal auth override with one that raises an
    # unexpected exception. The global handler should catch it.
    app.dependency_overrides[get_current_business_id] = simulated_bug

    r = await client.get("/jobs")
    assert r.status_code == 500
    assert r.json() == {"data": None, "error": "Internal server error"}
    # Confirm the original message is NOT leaked to the client
    assert "internal detail" not in r.text


async def test_http_exception_still_passes_through(client):
    """Sanity check: HTTPException should keep its own {detail: ...} default
    response — the catch-all handler must NOT shadow it."""
    r = await client.get("/jobs/9999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Job not found"}
