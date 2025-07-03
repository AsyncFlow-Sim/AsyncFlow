"""Pytest configuration file for setting up test fixtures and plugins."""

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy_utils import create_database, database_exists, drop_database

from app.config.settings import settings
from app.db.session import get_db
from app.main import app

# Load test environment variables from .env.test
ENV_PATH = Path(__file__).resolve().parents[1] / "docker_fs" / ".env.test"
load_dotenv(dotenv_path=ENV_PATH, override=True)


class DummySession:
    """A no-op async session substitute for unit tests."""

    def add(self, instance: object) -> None:
        """Perform a no-op add."""

    async def commit(self) -> None:
        """Perform a no-op commit."""

    async def refresh(self, instance: object) -> None:
        """Perform a no-op refresh."""

    async def flush(self) -> None:
        """Perform a no-op flush, required for unit tests."""


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a dummy async session for DB dependency override in unit tests."""
    # Cast so mypy sees an AsyncSession
    yield cast("AsyncSession", DummySession())


# Override the get_db dependency for all tests that use the app directly
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the database dependency overridden."""
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Drop and recreate the test database, then apply migrations."""
    markexpr = request.config.option.markexpr or ""
    is_integration_test = (
        "integration" in markexpr and "not integration" not in markexpr
    )

    if not is_integration_test:
        yield
        return

    # --- SETUP: This code runs before the test session starts ---
    sync_db_url = settings.db_url.replace("+asyncpg", "")

    if database_exists(sync_db_url):
        drop_database(sync_db_url)
    create_database(sync_db_url)

    os.environ["ENVIRONMENT"] = "test"
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    try:
        # The test session runs at this point
        yield
    finally:
        # --- TEARDOWN: This code runs after the test session ends ---
        if database_exists(sync_db_url):
            drop_database(sync_db_url)


@pytest.fixture(scope="session")
def async_engine() -> AsyncEngine:
    """Create and return an async SQLAlchemy engine for the test session."""
    return create_async_engine(settings.db_url, future=True, echo=False)


@pytest.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session wrapped in a transaction that is always rolled back."""
    # This fixture ensures that each test is isolated from others
    # within the same session.
    connection = await async_engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    session = session_factory()

    try:
        yield session
    finally:
        # Roll back the transaction to discard any changes made during the test
        await transaction.rollback()
        # Close the connection
        await connection.close()
