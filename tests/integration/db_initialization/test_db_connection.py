import pytest
from sqlalchemy import text

from app.db.session import engine


@pytest.mark.integration
async def test_db_connection() -> None:
    """Verify that the SQLAlchemy engine can connect to the database.

    This test ensures that the database connection is properly configured
    and can execute a simple query.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
