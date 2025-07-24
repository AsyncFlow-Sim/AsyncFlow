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
from numpy.random import Generator as NpGenerator
from numpy.random import default_rng
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy_utils import create_database, database_exists, drop_database

from app.config.constants import (
    EventMetricName,
    SampledMetricName,
    TimeDefaults,
)
from app.config.settings import settings
from app.db.session import get_db
from app.main import app
from app.schemas.full_simulation_input import SimulationPayload
from app.schemas.random_variables_config import RVConfig
from app.schemas.rqs_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology.full_system_topology import (
    Client,
    TopologyGraph,
    TopologyNodes,
)

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

# ============================================================================
# STANDARD CONFIGURATION FOR INPUT VARIABLES
# ============================================================================

# ---------------------------------------------------------------------------
# RNG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rng() -> NpGenerator:
    """Deterministic NumPy RNG shared across tests (seed=0)."""
    return default_rng(0)


# --------------------------------------------------------------------------- #
# Metric sets                                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def enabled_sample_metrics() -> set[SampledMetricName]:
    """Default time-series KPIs collected in most tests."""
    return {
        SampledMetricName.READY_QUEUE_LEN,
        SampledMetricName.RAM_IN_USE,
    }


@pytest.fixture(scope="session")
def enabled_event_metrics() -> set[EventMetricName]:
    """Default per-event KPIs collected in most tests."""
    return {
        EventMetricName.RQS_LATENCY,
    }


# --------------------------------------------------------------------------- #
# Global simulation settings                                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture
def sim_settings(
    enabled_sample_metrics: set[SampledMetricName],
    enabled_event_metrics: set[EventMetricName],
) -> SimulationSettings:
    """
    Minimal :class:`SimulationSettings` instance.

    The simulation horizon is fixed to the lowest allowed value so that unit
    tests run quickly.
    """
    return SimulationSettings(
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,
        enabled_sample_metrics=enabled_sample_metrics,
        enabled_event_metrics=enabled_event_metrics,
    )


# --------------------------------------------------------------------------- #
# Traffic profile                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def rqs_input() -> RqsGeneratorInput:
    """
    One active user issuing two requests per minute—sufficient to
    exercise the entire request-generator pipeline with minimal overhead.
    """
    return RqsGeneratorInput(
        id="rqs-1",
        avg_active_users=RVConfig(mean=1.0),
        avg_request_per_minute_per_user=RVConfig(mean=2.0),
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )


# --------------------------------------------------------------------------- #
# Minimal topology (one client, no servers, no edges)                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def topology_minimal() -> TopologyGraph:
    """
    A valid topology containing a single client and **no** servers or edges.

    Suitable for low-level tests that do not need to traverse the server
    layer or network graph.
    """
    client = Client(id="client-1")
    nodes = TopologyNodes(servers=[], client=client)
    return TopologyGraph(nodes=nodes, edges=[])


# --------------------------------------------------------------------------- #
# Complete simulation payload                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def payload_base(
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    topology_minimal: TopologyGraph,
) -> SimulationPayload:
    """
    End-to-end payload used by integration tests and FastAPI endpoint tests.

    It wires together the individual fixtures into the single object expected
    by the simulation engine.
    """
    return SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=topology_minimal,
        sim_settings=sim_settings,
    )
