"""Module for post-simulation analysis and visualization."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

from app.config.constants import LatencyKey, SampledMetricName
from app.config.plot_constants import (
    LATENCY_PLOT,
    RAM_PLOT,
    SERVER_QUEUES_PLOT,
    THROUGHPUT_PLOT,
    PlotCfg,
)

if TYPE_CHECKING:

    from collections.abc import Iterable

    from matplotlib.axes import Axes
    from matplotlib.lines import Line2D

    from app.runtime.actors.client import ClientRuntime
    from app.runtime.actors.edge import EdgeRuntime
    from app.runtime.actors.server import ServerRuntime
    from app.schemas.simulation_settings_input import SimulationSettings


class ResultsAnalyzer:
    """Analyze and visualize the results of a completed simulation.

    This class holds the raw runtime objects and lazily computes:
      - latency statistics
      - throughput time series (RPS)
      - sampled metrics from servers and edges
    """

    # Class attribute to define the period to calculate the throughput in s
    _WINDOW_SIZE_S: float = 1.0

    def __init__(
        self,
        *,
        client: ClientRuntime,
        servers: list[ServerRuntime],
        edges: list[EdgeRuntime],
        settings: SimulationSettings,
    ) -> None:
        """
        Args:
            client:      Client runtime object, containing RqsClock entries.
            servers:     List of server runtime objects.
            edges:       List of edge runtime objects.
            settings:    Original simulation settings.

        """
        self._client = client
        self._servers = servers
        self._edges = edges
        self._settings = settings

        # Lazily computed caches
        self.latencies: list[float] | None = None
        self.latency_stats: dict[LatencyKey, float] | None = None
        self.throughput_series: tuple[list[float], list[float]] | None = None
        self.sampled_metrics: dict[str, dict[str, list[float]]] | None = None

    @staticmethod
    def _apply_plot_cfg(
        ax: Axes,
        cfg: PlotCfg,
        *,
        legend_handles: Iterable[Line2D] | None = None,
    ) -> None:
        """Apply title / axis labels / grid and (optionally) legend to ax."""
        ax.set_title(cfg.title)
        ax.set_xlabel(cfg.x_label)
        ax.set_ylabel(cfg.y_label)
        ax.grid(visible=True)

        if legend_handles:
            ax.legend(handles=legend_handles)

    def process_all_metrics(self) -> None:
        """Compute all aggregated and sampled metrics if not already done."""
        if self.latency_stats is None and self._client.rqs_clock:
            self._process_event_metrics()

        if self.sampled_metrics is None:
            self._extract_sampled_metrics()

    def _process_event_metrics(self) -> None:
        """Calculate latency stats and throughput time series (RPS)."""
        # 1) Latencies
        self.latencies = [
            clock.finish - clock.start for clock in self._client.rqs_clock
        ]

        # 2) Summary stats
        if self.latencies:
            arr = np.array(self.latencies)
            self.latency_stats = {
                LatencyKey.TOTAL_REQUESTS: float(arr.size),
                LatencyKey.MEAN: float(np.mean(arr)),
                LatencyKey.MEDIAN: float(np.median(arr)),
                LatencyKey.STD_DEV: float(np.std(arr)),
                LatencyKey.P95: float(np.percentile(arr, 95)),
                LatencyKey.P99: float(np.percentile(arr, 99)),
                LatencyKey.MIN: float(np.min(arr)),
                LatencyKey.MAX: float(np.max(arr)),
            }
        else:
            self.latency_stats = {}

        # 3) Throughput per 1s window
        completion_times = sorted(clock.finish for clock in self._client.rqs_clock)
        end_time = self._settings.total_simulation_time

        timestamps: list[float] = []
        rps_values: list[float] = []
        count = 0
        idx = 0
        current_end = ResultsAnalyzer._WINDOW_SIZE_S

        while current_end <= end_time:
            while idx < len(completion_times) and completion_times[idx] <= current_end:
                count += 1
                idx += 1
            timestamps.append(current_end)
            rps_values.append(count / ResultsAnalyzer._WINDOW_SIZE_S)
            current_end += ResultsAnalyzer._WINDOW_SIZE_S
            count = 0

        self.throughput_series = (timestamps, rps_values)

    def _extract_sampled_metrics(self) -> None:
        """Gather sampled metrics from servers and edges into a nested dict."""
        metrics: dict[str, dict[str, list[float]]] = defaultdict(dict)

        for server in self._servers:
            sid = server.server_config.id
            for name, values in server.enabled_metrics.items():
                metrics[name.value][sid] = values

        for edge in self._edges:
            eid = edge.edge_config.id
            for name, values in edge.enabled_metrics.items():
                metrics[name.value][eid] = values

        self.sampled_metrics = metrics

    def get_latency_stats(self) -> dict[LatencyKey, float]:
        """Return latency statistics, computing them if necessary."""
        self.process_all_metrics()
        return self.latency_stats or {}

    def get_throughput_series(self) -> tuple[list[float], list[float]]:
        """Return throughput time series (timestamps, RPS)."""
        self.process_all_metrics()
        assert self.throughput_series is not None
        return self.throughput_series

    def get_sampled_metrics(self) -> dict[str, dict[str, list[float]]]:
        """Return sampled metrics from servers and edges."""
        self.process_all_metrics()
        assert self.sampled_metrics is not None
        return self.sampled_metrics

    def plot_latency_distribution(self, ax: Axes) -> None:
        """Plot the distribution of the latency"""
        if not self.latencies:
            ax.text(0.5, 0.5, LATENCY_PLOT.no_data, ha="center", va="center")
            return

        ax.hist(self.latencies, bins=50)
        self._apply_plot_cfg(ax, LATENCY_PLOT)

    def plot_throughput(self, ax: Axes) -> None:
        """Plot the distribution of the throughput"""
        timestamps, values = self.get_throughput_series()
        if not timestamps:
            ax.text(0.5, 0.5, THROUGHPUT_PLOT.no_data, ha="center", va="center")
            return

        ax.plot(timestamps, values, marker="o", linestyle="-")
        self._apply_plot_cfg(ax, THROUGHPUT_PLOT)

    def plot_server_queues(self, ax: Axes) -> None:
        """Plot the server queues"""
        metrics = self.get_sampled_metrics()
        ready = metrics.get(SampledMetricName.READY_QUEUE_LEN, {})
        io_q = metrics.get(SampledMetricName.EVENT_LOOP_IO_SLEEP, {})

        if not (ready or io_q):
            ax.text(0.5, 0.5, SERVER_QUEUES_PLOT.no_data, ha="center", va="center")
            return

        samples = len(next(iter(ready.values()), []))
        times = np.arange(samples) * self._settings.sample_period_s

        for sid, vals in ready.items():
            ax.plot(times, vals, label=f"{sid} {SERVER_QUEUES_PLOT.ready_label}")
        for sid, vals in io_q.items():
            ax.plot(
                times,
                vals,
                label=f"{sid} {SERVER_QUEUES_PLOT.io_label}",
                linestyle="--",
            )

        self._apply_plot_cfg(ax, SERVER_QUEUES_PLOT, legend_handles=ax.lines)


    def plot_ram_usage(self, ax: Axes) -> None:
        """Plot the ram usage"""
        metrics = self.get_sampled_metrics()
        ram = metrics.get(SampledMetricName.RAM_IN_USE, {})

        if not ram:
            ax.text(0.5, 0.5, RAM_PLOT.no_data, ha="center", va="center")
            return

        samples = len(next(iter(ram.values())))
        times = np.arange(samples) * self._settings.sample_period_s

        for sid, vals in ram.items():
            ax.plot(times, vals, label=f"{sid} {RAM_PLOT.legend_label}")

        self._apply_plot_cfg(ax, RAM_PLOT, legend_handles=ax.lines)
