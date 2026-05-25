#Sets up the database connection and session management using SQLAlchemy's asynchronous capabilities.
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,   # cheap SELECT 1 before handing out a pooled connection
    pool_recycle=1800,    # recycle any connection older than 30 min
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
