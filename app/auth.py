"""
Auth0 JWT validation and business_id resolution.

Usage in routes:
    business_id: int = Depends(get_current_business_id)
"""

import asyncio
import time
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models import Business

bearer = HTTPBearer()


# JWKS cache with a 5 minute TTL. The lock prevents N concurrent first
# requests from each firing the HTTP call on a cold container — they all
# wait on the first one and then read from cache.
_JWKS_TTL_SECONDS = 300
_jwks_cache: tuple[float, dict] | None = None
_jwks_lock = asyncio.Lock()


async def _get_jwks() -> dict:
    global _jwks_cache
    now = time.monotonic()
    if _jwks_cache is not None and now - _jwks_cache[0] < _JWKS_TTL_SECONDS:
        return _jwks_cache[1]

    async with _jwks_lock:
        # Re-check under the lock — another coroutine may have populated it.
        now = time.monotonic()
        if _jwks_cache is not None and now - _jwks_cache[0] < _JWKS_TTL_SECONDS:
            return _jwks_cache[1]

        url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        jwks = resp.json()
        _jwks_cache = (now, jwks)
        return jwks


async def _decode_token(token: str) -> dict:
    jwks = await _get_jwks()
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )
    return payload


async def get_current_business_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> int:
    payload = await _decode_token(credentials.credentials)
    auth0_user_id: str = payload.get("sub", "")

    result = await db.execute(
        select(Business).where(Business.owner_auth0_id == auth0_user_id)
    )
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No business associated with this account.",
        )

    return business.id


async def get_current_auth0_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> str:
    payload = await _decode_token(credentials.credentials)
    return payload.get("sub", "")
