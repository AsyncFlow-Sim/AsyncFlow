"""Unit tests for SweepAnalyzer (global and per-server collections & plots)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

from asyncfow.config.enums importLatencyKey
from asyncflow.metrics.sweep_analyzer import SweepAnalyzer

# Headless backend for CI
mpl.use("Agg")

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResultsAnalyzer:
    """Minimal fake of ResultsAnalyzer for SweepAnalyzer tests."""

    def __init__(
        self,
        *,
        rps_series: list[float],
        latency_stats: dict[LatencyKey, float],
        server_ids: list[str],
        server_arrays: dict[str, dict[str, list[float]]],
    ) -> None:
        self._rps_series = list(rps_series)
        self._latency_stats = dict(latency_stats)
        self._server_ids = list(server_ids)
        self._server_arrays = {
            sid: {k: list(v) for k, v in arrays.items()}
            for sid, arrays in server_arrays.items()
        }
        self.process_calls = 0

    # Public API mirrored from the real analyzer

    def process_all_metrics(self) -> None:
        self.process_calls += 1

    def get_throughput_series(self) -> tuple[list[float], list[float]]:
        """Return (timestamps, rps). We only care about the RPS values."""
        n = len(self._rps_series)
        timestamps = [float(i + 1) for i in range(n)]
        return timestamps, list(self._rps_series)

    def get_latency_stats(self) -> dict[LatencyKey, float]:
        return dict(self._latency_stats)

    def list_server_ids(self) -> list[str]:
        return list(self._server_ids)

    def get_server_event_arrays(self) -> dict[str, dict[str, list[float]]]:
        return {
            sid: {k: list(v) for k, v in arrays.items()}
            for sid, arrays in self._server_arrays.items()
        }


def _cast_pair(
    users: int,
    fra: _FakeResultsAnalyzer,
) -> tuple[int, ResultsAnalyzer]:
    """Cast helper to satisfy mypy on constructor signature."""
    return users, cast("ResultsAnalyzer", fra)


# ---------------------------------------------------------------------------
# Tests — Global collection and plots
# ---------------------------------------------------------------------------


def test_global_collection_and_plots_match_expected_values() -> None:
    """Global throughput mean and mean latency must match the inputs."""
    # Pair 1: mean RPS = 100, mean latency = 0.05
    ra1 = _FakeResultsAnalyzer(
        rps_series=[100.0, 110.0, 90.0],
        latency_stats={
            LatencyKey.MEAN: 0.05,
            LatencyKey.MEDIAN: 0.04,
            LatencyKey.P95: 0.10,
            LatencyKey.P99: 0.20,
        },
        server_ids=["s1"],
        server_arrays={
            "s1": {
                "service_time": [0.01],
                "waiting_time": [0.005],
                "finish_times": [0.1, 0.2],
            },
        },
    )

    # Pair 2: mean RPS = 200, mean latency = 0.06
    ra2 = _FakeResultsAnalyzer(
        rps_series=[200.0, 190.0, 210.0],
        latency_stats={
            LatencyKey.MEAN: 0.06,
            LatencyKey.MEDIAN: 0.05,
            LatencyKey.P95: 0.12,
            LatencyKey.P99: 0.22,
        },
        server_ids=["s1"],
        server_arrays={
            "s1": {
                "service_time": [0.01],
                "waiting_time": [0.004],
                "finish_times": [0.3, 0.4],
            },
        },
    )

    sa = SweepAnalyzer(
        [_cast_pair(10, ra1), _cast_pair(20, ra2)],
    )

    # Global dashboard and line data
    fig = sa.plot_global_dashboard()
    axes = fig.get_axes()
    assert len(axes) == 2

    # Throughput axis
    thr_line = axes[0].lines[0]
    x_thr = list(cast("Iterable[float]", thr_line.get_xdata()))
    y_thr = list(cast("Iterable[float]", thr_line.get_ydata()))
    assert x_thr == [10, 20]
    assert pytest.approx(y_thr) == [100.0, 200.0]

    # Latency axis
    lat_line = axes[1].lines[0]
    x_lat = list(cast("Iterable[float]", lat_line.get_xdata()))
    y_lat = list(cast("Iterable[float]", lat_line.get_ydata()))
    assert x_lat == [10, 20]
    assert pytest.approx(y_lat) == [0.05, 0.06]

    plt.close(fig)


# ---------------------------------------------------------------------------
# Tests — Per-server collection and overlays
# ---------------------------------------------------------------------------


def test_server_overlays_compute_lambda_mu_rho_and_wq() -> None:
    """Per-server metrics must follow completions split and means."""
    # lambda_tot = 100 (mean of [100, 100])
    # completions: s1=60, s2=40 -> lambda1=60, lambda2=40
    # mu1 = 1/0.01 = 100, mu2 = 1/0.02 = 50
    # rho1 = 0.6, rho2 = 0.8
    # wq means from waiting_time arrays
    ra = _FakeResultsAnalyzer(
        rps_series=[100.0, 100.0],
        latency_stats={LatencyKey.MEAN: 0.05},
        server_ids=["s1", "s2"],
        server_arrays={
            "s1": {
                "service_time": [0.01] * 5,
                "waiting_time": [0.005] * 5,
                "finish_times": [0.0] * 60,
            },
            "s2": {
                "service_time": [0.02] * 5,
                "waiting_time": [0.004] * 5,
                "finish_times": [0.0] * 40,
            },
        },
    )

    sa = SweepAnalyzer([_cast_pair(10, ra)])

    # Utilization overlay
    fig1, ax1 = plt.subplots(1, 1)
    sa.plot_server_utilization_overlay(ax1, server_ids=["s1", "s2"])
    lines = {line.get_label(): line for line in ax1.get_lines()}
    assert "s1" in lines
    assert "s2" in lines
    y_rho_s1 = next(iter(cast("Iterable[float]", lines["s1"].get_ydata())))
    y_rho_s2 = next(iter(cast("Iterable[float]", lines["s2"].get_ydata())))
    assert pytest.approx(y_rho_s1) == 0.6
    assert pytest.approx(y_rho_s2) == 0.8
    plt.close(fig1)

    # Service rate overlay
    fig2, ax2 = plt.subplots(1, 1)
    sa.plot_server_service_rate_overlay(ax2, server_ids=["s1", "s2"])
    lines2 = {line.get_label(): line for line in ax2.get_lines()}
    mu_s1 = next(iter(cast("Iterable[float]", lines2["s1"].get_ydata())))
    mu_s2 = next(iter(cast("Iterable[float]", lines2["s2"].get_ydata())))
    assert pytest.approx(mu_s1) == 100.0
    assert pytest.approx(mu_s2) == 50.0
    plt.close(fig2)

    # Waiting time overlay
    fig3, ax3 = plt.subplots(1, 1)
    sa.plot_server_waiting_time_overlay(ax3, server_ids=["s1", "s2"])
    lines3 = {line.get_label(): line for line in ax3.get_lines()}
    wq_s1 = next(iter(cast("Iterable[float]", lines3["s1"].get_ydata())))
    wq_s2 = next(iter(cast("Iterable[float]", lines3["s2"].get_ydata())))
    assert pytest.approx(wq_s1) == 0.005
    assert pytest.approx(wq_s2) == 0.004
    plt.close(fig3)

    # Throughput overlay
    fig4, ax4 = plt.subplots(1, 1)
    sa.plot_server_throughput_overlay(ax4, server_ids=["s1", "s2"])
    lines4 = {line.get_label(): line for line in ax4.get_lines()}
    lam_s1 = next(iter(cast("Iterable[float]", lines4["s1"].get_ydata())))
    lam_s2 = next(iter(cast("Iterable[float]", lines4["s2"].get_ydata())))
    assert pytest.approx(lam_s1) == 60.0
    assert pytest.approx(lam_s2) == 40.0
    plt.close(fig4)


# ---------------------------------------------------------------------------
# Tests — Caching behavior
# ---------------------------------------------------------------------------


def test_precollect_runs_each_analyzer_once_per_collector() -> None:
    """precollect() plus plots should call process_all_metrics exactly twice."""
    # Two pairs to make sure iteration is covered.
    ra1 = _FakeResultsAnalyzer(
        rps_series=[10.0, 20.0],
        latency_stats={LatencyKey.MEAN: 0.1},
        server_ids=["s1"],
        server_arrays={"s1": {"service_time": [0.05], "waiting_time": [0.01]}},
    )
    ra2 = _FakeResultsAnalyzer(
        rps_series=[30.0, 40.0],
        latency_stats={LatencyKey.MEAN: 0.2},
        server_ids=["s2"],
        server_arrays={"s2": {"service_time": [0.02], "waiting_time": [0.02]}},
    )

    sa = SweepAnalyzer([_cast_pair(5, ra1), _cast_pair(15, ra2)])

    # Warm caches (global + servers)
    sa.precollect()

    # Plot both dashboards (should NOT trigger recomputation)
    fig_g = sa.plot_global_dashboard()
    fig_s = sa.plot_server_dashboard()
    plt.close(fig_g)
    plt.close(fig_s)

    # Each analyzer should have been processed exactly twice:
    # once for global collection + once for server collection.
    assert ra1.process_calls == 2
    assert ra2.process_calls == 2
