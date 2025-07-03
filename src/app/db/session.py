"""Database session management and connection utilities."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings

engine = create_async_engine(
    settings.db_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a transactional database session.
    It commits the transaction on successful completion or rolls back on error.
    """
    async with AsyncSessionLocal() as session:
        try:

            yield session

            await session.commit()
        except Exception:

            await session.rollback()

            raise
