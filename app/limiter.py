"""
Shared rate-limiter singleton.

Lives in its own module so route files can import it without creating a
circular import with `app.main`. `main.py` is responsible for wiring this
limiter into the FastAPI app's state + registering the 429 handler.

Limits are *disabled* via `RATE_LIMITS_ENABLED=false` so the test suite
isn't flaky and so local dev can spam endpoints freely.
"""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address

_ENABLED = os.getenv("RATE_LIMITS_ENABLED", "true").lower() != "false"

limiter = Limiter(
    key_func=get_remote_address,
    enabled=_ENABLED,
    default_limits=[],
)
