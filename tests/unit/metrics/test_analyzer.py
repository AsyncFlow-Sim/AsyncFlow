# tests/unit/metrics/test_analyzer.py
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from matplotlib.figure import Figure

from app.metrics.analyzer import ResultsAnalyzer

if TYPE_CHECKING:

    from app.schemas.simulation_settings_input import SimulationSettings


class DummyClock:
    """Stub for a single request clock with start and finish timestamps."""

    def __init__(self, start: float, finish: float) -> None:
        """Initialize with start and finish times."""
        self.start = start
        self.finish = finish


class DummyClient:
    """Stub for ClientRuntime exposing a list of DummyClock in `rqs_clock`."""

    def __init__(self, clocks: list[DummyClock]) -> None:
        """Initialize with a list of DummyClock instances."""
        self.rqs_clock = clocks


class DummyName:
    """Stub to simulate an enum member with a `.value` attribute."""

    def __init__(self, value: str) -> None:
        """Initialize with the given string value."""
        self.value = value


class DummyServerConfig:
    """Stub for server configuration exposing an identifier."""

    def __init__(self, identifier: str) -> None:
        """Initialize with the server identifier."""
        self.id = identifier


class DummyServer:
    """Stub for ServerRuntime with server_config.id and enabled_metrics."""

    def __init__(
        self,
        identifier: str,
        metrics: dict[str, list[float]],
    ) -> None:
        """Initialize with an id and a dict of metric_name → values."""
        self.server_config = DummyServerConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


class DummyEdgeConfig:
    """Stub for edge configuration exposing an identifier."""

    def __init__(self, identifier: str) -> None:
        """Initialize with the edge identifier."""
        self.id = identifier


class DummyEdge:
    """Stub for EdgeRuntime with edge_config.id and enabled_metrics."""

    def __init__(
        self,
        identifier: str,
        metrics: dict[str, list[float]],
    ) -> None:
        """Initialize with an id and a dict of metric_name → values."""
        self.edge_config = DummyEdgeConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def simple_analyzer(
    sim_settings: SimulationSettings,
) -> ResultsAnalyzer:
    """
    Return an analyzer with two synthetic requests (durations 1s and 2s)
    over a 3-second horizon and no sampled metrics.
    """
    sim_settings.total_simulation_time = 3.0
    clocks = [DummyClock(0.0, 1.0), DummyClock(0.0, 2.0)]
    client = DummyClient(clocks)
    return ResultsAnalyzer(
        client=client,
        servers=[],
        edges=[],
        settings=sim_settings,
    )


# ----------------------------------------------------------------------
# Tests for computed metrics
# ----------------------------------------------------------------------

def test_latency_stats(simple_analyzer: ResultsAnalyzer) -> None:
    """Verify that latency statistics are computed correctly."""
    stats = simple_analyzer.get_latency_stats()
    # Durations are [1.0, 2.0]
    assert stats["total_requests"] == 2.0
    assert stats["mean"] == pytest.approx(1.5)
    assert stats["median"] == pytest.approx(1.5)
    assert stats["min"] == pytest.approx(1.0)
    assert stats["max"] == pytest.approx(2.0)
    # 95th percentile = 1 + 0.95 * (2 - 1) = 1.95
    assert stats["p95"] == pytest.approx(1.95, rel=1e-3)


def test_throughput_series(simple_analyzer: ResultsAnalyzer) -> None:
    """Verify throughput per 1s window is correct."""
    timestamps, rps = simple_analyzer.get_throughput_series()
    # Window ends at 1.0, 2.0, 3.0 seconds
    assert timestamps == [1.0, 2.0, 3.0]
    # One request in first, one in second, zero in third
    assert rps == [1.0, 1.0, 0.0]


def test_sampled_metrics_empty(simple_analyzer: ResultsAnalyzer) -> None:
    """If no servers or edges are given, sampled_metrics should be empty."""
    sampled = simple_analyzer.get_sampled_metrics()
    assert sampled == {}


# ----------------------------------------------------------------------
# Tests for plotting methods
# ----------------------------------------------------------------------

def test_plot_latency_distribution(simple_analyzer: ResultsAnalyzer) -> None:
    """Latency distribution plot should set the correct title."""
    fig = Figure()
    ax = fig.subplots()
    simple_analyzer.process_all_metrics()
    simple_analyzer.plot_latency_distribution(ax)
    assert ax.get_title() == "Request Latency Distribution"


def test_plot_throughput(simple_analyzer: ResultsAnalyzer) -> None:
    """Throughput plot should set the correct title."""
    fig = Figure()
    ax = fig.subplots()
    simple_analyzer.process_all_metrics()
    simple_analyzer.plot_throughput(ax)
    assert ax.get_title() == "Throughput (RPS)"


def test_plot_server_queues_with_data(
    sim_settings: SimulationSettings,
) -> None:
    """
    Server queue plot should handle non empty metrics and include
    legend entries for each server.
    """
    sim_settings.total_simulation_time = 3.0
    client = DummyClient([])
    server = DummyServer("srv1", {"ready_queue_len": [1, 2, 3]})
    edge = DummyEdge("edge1", {})
    analyzer = ResultsAnalyzer(
        client=client,
        servers=[server],
        edges=[edge],
        settings=sim_settings,
    )
    fig = Figure()
    ax = fig.subplots()
    analyzer.process_all_metrics()
    analyzer.plot_server_queues(ax)
    assert ax.get_title() == "Server Queues"
    legend = ax.get_legend()
    assert legend is not None
    texts = [t.get_text() for t in legend.get_texts()]
    assert "srv1 (ready)" in texts


def test_plot_ram_usage_with_data(
    sim_settings: SimulationSettings,
) -> None:
    """
    RAM usage plot should handle non empty metrics and include
    legend entries for each edge.
    """
    sim_settings.total_simulation_time = 3.0
    client = DummyClient([])
    edge = DummyEdge("edgeA", {"ram_in_use": [10.0, 20.0]})
    analyzer = ResultsAnalyzer(
        client=client,
        servers=[],
        edges=[edge],
        settings=sim_settings,
    )
    fig = Figure()
    ax = fig.subplots()
    analyzer.process_all_metrics()
    analyzer.plot_ram_usage(ax)
    assert ax.get_title() == "RAM Usage"
    legend = ax.get_legend()
    assert legend is not None
    texts = [t.get_text() for t in legend.get_texts()]
    assert "edgeA RAM" in texts
