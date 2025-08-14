"""Pytest configuration file for setting up test fixtures and plugins."""


import pytest
from numpy.random import Generator as NpGenerator
from numpy.random import default_rng

from asyncflow.config.constants import (
    Distribution,
    EventMetricName,
    SampledMetricName,
    SamplePeriods,
    TimeDefaults,
)
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    TopologyNodes,
)
from asyncflow.schemas.workload.generator import RqsGenerator

# ============================================================================
# STANDARD CONFIGURATION FOR INPUT VARIABLES
# ============================================================================

# ---------------------------------------------------------------------------
# RANDOM VARIABLE GENERATOR
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
        EventMetricName.RQS_CLOCK,
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
        sample_period_s=SamplePeriods.STANDARD_TIME,
    )


# --------------------------------------------------------------------------- #
# Traffic profile                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def rqs_input() -> RqsGenerator:
    """
    One active user issuing two requests per minute—sufficient to
    exercise the entire request-generator pipeline with minimal overhead.
    """
    return RqsGenerator(
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
    A valid *tiny* topology: one generator ➜ one client.

    The single edge has a negligible latency; its only purpose is to give the
    generator a valid ``out_edge`` so that the runtime can start.
    """
    client = Client(id="client-1")

    # Stub edge: generator id comes from rqs_input fixture (“rqs-1”)
    edge = Edge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )

    nodes = TopologyNodes(servers=[], client=client)
    return TopologyGraph(nodes=nodes, edges=[edge])

# --------------------------------------------------------------------------- #
# Complete simulation payload                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def payload_base(
    rqs_input: RqsGenerator,
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
