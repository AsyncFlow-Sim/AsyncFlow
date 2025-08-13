"""Unit-tests for ``ResultsAnalyzer`` (latency, throughput, plots)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from matplotlib.figure import Figure

from asyncflow.config.constants import LatencyKey
from asyncflow.metrics.analyzer import ResultsAnalyzer

if TYPE_CHECKING:
    from asyncflow.runtime.actors.client import ClientRuntime
    from asyncflow.runtime.actors.edge import EdgeRuntime
    from asyncflow.runtime.actors.server import ServerRuntime
    from asyncflow.schemas.simulation_settings_input import SimulationSettings


# ---------------------------------------------------------------------- #
# Dummy objects (test doubles)                                           #
# ---------------------------------------------------------------------- #
class DummyClock:
    """Clock with *start* / *finish* timestamps to emulate a request."""

    def __init__(self, start: float, finish: float) -> None:
        """Save *start* and *finish* times."""
        self.start = start
        self.finish = finish


class DummyClient:
    """Emulates ``ClientRuntime`` by exposing ``rqs_clock``."""

    def __init__(self, clocks: list[DummyClock]) -> None:
        """Attach a list of dummy clocks to the stub client."""
        self.rqs_clock = clocks


class DummyName:
    """Mimic an Enum member that carries a ``.value`` attribute."""

    def __init__(self, value: str) -> None:
        """Store the dummy string *value*."""
        self.value = value


class DummyServerConfig:
    """Lightweight replacement for the real ``ServerConfig``."""

    def __init__(self, identifier: str) -> None:
        """Expose only the *id* field required by the analyzer."""
        self.id = identifier


class DummyServer:
    """Stub for ``ServerRuntime`` exposing ``enabled_metrics``."""

    def __init__(self, identifier: str, metrics: dict[str, list[float]]) -> None:
        """Create a fake server with the given *metrics*."""
        self.server_config = DummyServerConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


class DummyEdgeConfig:
    """Minified replacement for the real ``EdgeConfig``."""

    def __init__(self, identifier: str) -> None:
        """Expose only the *id* property."""
        self.id = identifier


class DummyEdge:
    """Stub for ``EdgeRuntime`` exposing ``enabled_metrics``."""

    def __init__(self, identifier: str, metrics: dict[str, list[float]]) -> None:
        """Create a fake edge with the given *metrics*."""
        self.edge_config = DummyEdgeConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


# ---------------------------------------------------------------------- #
# Fixtures                                                               #
# ---------------------------------------------------------------------- #
@pytest.fixture
def simple_analyzer(sim_settings: SimulationSettings) -> ResultsAnalyzer:
    """
    Analyzer with two synthetic requests (durations 1 s and 2 s) on a
    3-second horizon and **no** sampled metrics.
    """
    sim_settings.total_simulation_time = 3
    clocks = [DummyClock(0.0, 1.0), DummyClock(0.0, 2.0)]
    client = DummyClient(clocks)
    return ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[],
        edges=[],
        settings=sim_settings,
    )


# ---------------------------------------------------------------------- #
# Tests for computed metrics                                             #
# ---------------------------------------------------------------------- #
def test_latency_stats(simple_analyzer: ResultsAnalyzer) -> None:
    stats = simple_analyzer.get_latency_stats()
    assert stats[LatencyKey.TOTAL_REQUESTS] == 2.0
    assert stats[LatencyKey.MEAN] == pytest.approx(1.5)
    assert stats[LatencyKey.MEDIAN] == pytest.approx(1.5)
    assert stats[LatencyKey.MIN] == pytest.approx(1.0)
    assert stats[LatencyKey.MAX] == pytest.approx(2.0)
    assert stats[LatencyKey.P95] == pytest.approx(1.95, rel=1e-3)


def test_throughput_series(simple_analyzer: ResultsAnalyzer) -> None:
    timestamps, rps = simple_analyzer.get_throughput_series()
    assert timestamps == [1.0, 2.0, 3.0]
    assert rps == [1.0, 1.0, 0.0]


def test_sampled_metrics_empty(simple_analyzer: ResultsAnalyzer) -> None:
    assert simple_analyzer.get_sampled_metrics() == {}


# ---------------------------------------------------------------------- #
# Tests for plotting methods                                             #
# ---------------------------------------------------------------------- #
def test_plot_latency_distribution(simple_analyzer: ResultsAnalyzer) -> None:
    fig = Figure()
    ax = fig.subplots()
    simple_analyzer.process_all_metrics()
    simple_analyzer.plot_latency_distribution(ax)
    assert ax.get_title() == "Request Latency Distribution"


def test_plot_throughput(simple_analyzer: ResultsAnalyzer) -> None:
    fig = Figure()
    ax = fig.subplots()
    simple_analyzer.process_all_metrics()
    simple_analyzer.plot_throughput(ax)
    assert ax.get_title() == "Throughput (RPS)"


def test_plot_server_queues_with_data(sim_settings: SimulationSettings) -> None:
    sim_settings.total_simulation_time = 3
    client = DummyClient([])
    server = DummyServer("srv1", {"ready_queue_len": [1, 2, 3]})
    edge = DummyEdge("edge1", {})
    analyzer = ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[cast("ServerRuntime", server)],
        edges=[cast("EdgeRuntime", edge)],
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
    assert "srv1 Ready queue" in texts


def test_plot_ram_usage_with_data(sim_settings: SimulationSettings) -> None:
    sim_settings.total_simulation_time = 3
    client = DummyClient([])
    edge = DummyEdge("edgeA", {"ram_in_use": [10.0, 20.0]})
    analyzer = ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[],
        edges=[cast("EdgeRuntime", edge)],
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
