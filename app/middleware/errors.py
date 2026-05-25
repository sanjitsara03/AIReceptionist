"""
Global exception handler.

Catches anything that bubbles up out of our routes without being handled more
specifically (HTTPException and validation errors keep their default handlers
because they're registered for narrower types). For everything else:

1. Log the traceback so we can debug from server logs.
2. Report to Sentry. If Sentry isn't initialized (no DSN configured), the call
   is a silent no-op — safe to call unconditionally.
3. Return a clean envelope `{"data": null, "error": "Internal server error"}`
   with status 500, matching the project's response convention.

We deliberately don't leak the original exception message to the client — it
can contain stack-trace info, DB connection strings, or other internals.
"""

import logging
import sentry_sdk
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": "Internal server error"},
    )
