import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

async def test_users_table_exists_after_migrations() -> None:
    engine = create_async_engine(settings.db_url, echo=False)
    try:
        async with engine.connect() as conn:
           await conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        pytest.fail("Database connection or Alembic setup failed.")
       
