"""Extra unit tests for ``ResultsAnalyzer`` helpers and plots.

This suite complements the basic analyzer tests by exercising:
- formatting helpers (latency stats pretty-printer),
- server-id ordering,
- throughput recomputation with a custom window,
- metric accessors tolerant to enum/string keys,
- per-metric series time bases,
- the compact "base dashboard" plotting helper,
- single-server plots (ready queue, I/O queue, RAM),
- multi-server helpers (axes allocation and error handling).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from matplotlib.figure import Figure

from asyncflow.analysis import ResultsAnalyzer
from asyncflow.enums import SampledMetricName

if TYPE_CHECKING:
    from asyncflow.runtime.actors.client import ClientRuntime
    from asyncflow.runtime.actors.edge import EdgeRuntime
    from asyncflow.runtime.actors.server import ServerRuntime
    from asyncflow.schemas.settings.simulation import SimulationSettings


# ---------------------------------------------------------------------- #
# Test doubles (minimal)                                                  #
# ---------------------------------------------------------------------- #
class DummyClock:
    """Clock with *start* and *finish* timestamps to emulate one request."""

    def __init__(self, start: float, finish: float) -> None:
        """Initialize a synthetic request completion interval."""
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
        """Store the underlying string *value* used as a metric key."""
        self.value = value


class DummyServerConfig:
    """Minimal server config with only the ``id`` attribute."""

    def __init__(self, identifier: str) -> None:
        """Set the server identifier used by the analyzer."""
        self.id = identifier


class DummyServer:
    """Stub for ``ServerRuntime`` exposing ``enabled_metrics`` and config."""

    def __init__(self, identifier: str, metrics: dict[str, list[float]]) -> None:
        """Create a fake server with the given per-metric time series."""
        self.server_config = DummyServerConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


class DummyEdgeConfig:
    """Minimal edge config with only the ``id`` attribute."""

    def __init__(self, identifier: str) -> None:
        """Set the edge identifier used by the analyzer."""
        self.id = identifier


class DummyEdge:
    """Stub for ``EdgeRuntime`` exposing ``enabled_metrics`` and config."""

    def __init__(self, identifier: str, metrics: dict[str, list[float]]) -> None:
        """Create a fake edge with the given per-metric time series."""
        self.edge_config = DummyEdgeConfig(identifier)
        self.enabled_metrics = {
            DummyName(name): values for name, values in metrics.items()
        }


# ---------------------------------------------------------------------- #
# Fixtures                                                                #
# ---------------------------------------------------------------------- #
@pytest.fixture
def analyzer_with_metrics(sim_settings: SimulationSettings) -> ResultsAnalyzer:
    """Provide an analyzer with one server and ready/io/ram signals.

    The fixture sets:
      - total_simulation_time = 3 s,
      - sample_period_s = 1 s,
      - two completed requests at t=1s and t=2s.
    """
    sim_settings.total_simulation_time = 3
    sim_settings.sample_period_s = 1.0
    client = DummyClient([DummyClock(0.0, 1.0), DummyClock(0.0, 2.0)])
    server = DummyServer(
        "srvX",
        {
            "ready_queue_len": [0, 1, 2],
            "event_loop_io_sleep": [0, 0, 1],
            "ram_in_use": [10.0, 20.0, 30.0],
        },
    )
    edge = DummyEdge("edgeX", {})
    return ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[cast("ServerRuntime", server)],
        edges=[cast("EdgeRuntime", edge)],
        settings=sim_settings,
    )


# ---------------------------------------------------------------------- #
# Accessors / formatting                                                  #
# ---------------------------------------------------------------------- #
def test_format_latency_stats_contains_header_and_lines(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """Ensure the formatted stats contain a header and canonical keys."""
    text = analyzer_with_metrics.format_latency_stats()
    assert "LATENCY STATS" in text
    assert "MEAN" in text
    assert "MEDIAN" in text


def test_list_server_ids_preserves_topology_order(
    sim_settings: SimulationSettings,
) -> None:
    """Verify that server IDs are returned in topology order."""
    sim_settings.total_simulation_time = 1
    client = DummyClient([])
    s1 = DummyServer("s1", {})
    s2 = DummyServer("s2", {})
    s3 = DummyServer("s3", {})
    an = ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[
            cast("ServerRuntime", s1),
            cast("ServerRuntime", s2),
            cast("ServerRuntime", s3),
        ],
        edges=[],
        settings=sim_settings,
    )
    assert an.list_server_ids() == ["s1", "s2", "s3"]


# ---------------------------------------------------------------------- #
# Throughput with custom window                                           #
# ---------------------------------------------------------------------- #
def test_get_throughput_series_custom_window_half_second(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """Check recomputation of throughput with a 0.5 s window."""
    # Completions at 1s and 2s; with 0.5s buckets counts are [0,1,0,1,0,0].
    # Rates are counts / 0.5 => [0, 2, 0, 2, 0, 0].
    ts, rps = analyzer_with_metrics.get_throughput_series(window_s=0.5)
    assert ts[:4] == [0.5, 1.0, 1.5, 2.0]
    assert rps[:4] == [0.0, 2.0, 0.0, 2.0]


# ---------------------------------------------------------------------- #
# Metric map / series helpers                                             #
# ---------------------------------------------------------------------- #
def test_get_metric_map_accepts_enum_and_string(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """Ensure metric retrieval works for enum and raw-string keys."""
    m_enum = analyzer_with_metrics.get_metric_map(
        SampledMetricName.READY_QUEUE_LEN,
    )
    m_str = analyzer_with_metrics.get_metric_map("ready_queue_len")

    # PT018: split assertions into multiple parts.
    assert "srvX" in m_enum
    assert "srvX" in m_str
    assert m_enum["srvX"] == [0, 1, 2]
    assert m_str["srvX"] == [0, 1, 2]

def test_get_series_respects_sample_period(
    sim_settings: SimulationSettings,
) -> None:
    """Confirm that series time base honors ``sample_period_s``."""
    sim_settings.total_simulation_time = 5
    sim_settings.sample_period_s = 1.5
    client = DummyClient([])
    server = DummyServer("srv1", {"ready_queue_len": [3, 4, 5]})
    an = ResultsAnalyzer(
        client=cast("ClientRuntime", client),
        servers=[cast("ServerRuntime", server)],
        edges=[],
        settings=sim_settings,
    )
    times, vals = an.get_series(SampledMetricName.READY_QUEUE_LEN, "srv1")
    assert vals == [3, 4, 5]
    assert times == [0.0, 1.5, 3.0]


# ---------------------------------------------------------------------- #
# Plotting: base dashboard                                                #
# ---------------------------------------------------------------------- #
def test_plot_base_dashboard_sets_titles(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """Validate that the base dashboard sets expected axis titles."""
    fig = Figure()
    ax_lat, ax_thr = fig.subplots(1, 2)
    analyzer_with_metrics.plot_base_dashboard(ax_lat, ax_thr)
    assert ax_lat.get_title() == "Request Latency Distribution"
    assert ax_thr.get_title() == "Throughput (RPS)"


# ---------------------------------------------------------------------- #
# Plotting: single-server dedicated plots                                 #
# ---------------------------------------------------------------------- #
def test_plot_single_server_ready_queue(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """Ready-queue plot should have a title and a legend with mean/min/max."""
    fig = Figure()
    ax = fig.subplots()
    analyzer_with_metrics.plot_single_server_ready_queue(ax, "srvX")

    assert "Ready Queue" in ax.get_title()

    legend = ax.get_legend()
    assert legend is not None

    labels = [t.get_text() for t in legend.get_texts()]
    assert any(lbl.lower().startswith("mean") for lbl in labels)
    assert any(lbl.lower().startswith("min") for lbl in labels)
    assert any(lbl.lower().startswith("max") for lbl in labels)
    assert len(labels) == 3


def test_plot_single_server_io_queue(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """I/O-queue plot should have a title and a legend with mean/min/max."""
    fig = Figure()
    ax = fig.subplots()
    analyzer_with_metrics.plot_single_server_io_queue(ax, "srvX")

    assert "I/O Queue" in ax.get_title()

    legend = ax.get_legend()
    assert legend is not None

    labels = [t.get_text() for t in legend.get_texts()]
    assert any(lbl.lower().startswith("mean") for lbl in labels)
    assert any(lbl.lower().startswith("min") for lbl in labels)
    assert any(lbl.lower().startswith("max") for lbl in labels)
    assert len(labels) == 3


def test_plot_single_server_ram(
    analyzer_with_metrics: ResultsAnalyzer,
) -> None:
    """RAM plot should have a title and a legend with mean/min/max."""
    fig = Figure()
    ax = fig.subplots()
    analyzer_with_metrics.plot_single_server_ram(ax, "srvX")

    assert "RAM" in ax.get_title()

    legend = ax.get_legend()
    assert legend is not None

    labels = [t.get_text() for t in legend.get_texts()]
    assert any(lbl.lower().startswith("mean") for lbl in labels)
    assert any(lbl.lower().startswith("min") for lbl in labels)
    assert any(lbl.lower().startswith("max") for lbl in labels)
    assert len(labels) == 3

