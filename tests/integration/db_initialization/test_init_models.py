import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

async def test_users_table_exists_after_migrations() -> None:
    engine = create_async_engine(settings.db_url, echo=False)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "  AND table_name = 'users';",
            ),
        )
        assert result.scalar_one() == 1
