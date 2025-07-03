"""Database initialization and cleanup utilities."""

from .base import Base
from .session import engine


async def init_models() -> None:
    """Initialize database models by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Close the database engine and dispose of connections."""
    await engine.dispose()
