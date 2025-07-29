"""Module for post-simulation analysis and visualization."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:

    from matplotlib.axes import Axes

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
        self.latency_stats: dict[str, float] | None = None
        self.throughput_series: tuple[list[float], list[float]] | None = None
        self.sampled_metrics: dict[str, dict[str, list[float]]] | None = None

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
                "total_requests": float(arr.size),
                "mean": float(np.mean(arr)),
                "median": float(np.median(arr)),
                "std_dev": float(np.std(arr)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
            }
        else:
            self.latency_stats = {}

        # 3) Throughput per 1s window
        completion_times = sorted(clock.finish for clock in self._client.rqs_clock)
        window_size = 1.0
        end_time = self._settings.total_simulation_time

        timestamps: list[float] = []
        rps_values: list[float] = []
        count = 0
        idx = 0
        current_end = window_size

        while current_end <= end_time:
            while idx < len(completion_times) and completion_times[idx] <= current_end:
                count += 1
                idx += 1
            timestamps.append(current_end)
            rps_values.append(count / window_size)
            current_end += window_size
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

    def get_latency_stats(self) -> dict[str, float]:
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

    # TODO(Gioele Botta): create a class of constants to remove all magic words
    def plot_latency_distribution(self, ax: Axes) -> None:
        """Draw a histogram of request latencies onto the given Axes."""
        if not self.latencies:
            ax.text(0.5, 0.5, "No latency data", ha="center", va="center")
            return

        ax.hist(self.latencies, bins=50)
        ax.set_title("Request Latency Distribution")
        ax.set_xlabel("Latency (s)")
        ax.set_ylabel("Frequency")
        ax.grid(visible=True)

    def plot_throughput(self, ax: Axes) -> None:
        """Draw throughput (RPS) over time onto the given Axes."""
        timestamps, values = self.get_throughput_series()
        if not timestamps:
            ax.text(0.5, 0.5, "No throughput data", ha="center", va="center")
            return

        ax.plot(timestamps, values, marker="o", linestyle="-")
        ax.set_title("Throughput (RPS)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Requests/s")
        ax.grid(visible=True)

    def plot_server_queues(self, ax: Axes) -> None:
        """Draw server queue lengths over time onto the given Axes."""
        metrics = self.get_sampled_metrics()
        ready = metrics.get("ready_queue_len", {})
        io_q = metrics.get("event_loop_io_sleep", {})

        if not (ready or io_q):
            ax.text(0.5, 0.5, "No queue data", ha="center", va="center")
            return

        samples = len(next(iter(ready.values()), []))
        times = np.arange(samples) * self._settings.sample_period_s

        for sid, vals in ready.items():
            ax.plot(times, vals, label=f"{sid} (ready)")
        for sid, vals in io_q.items():
            ax.plot(times, vals, label=f"{sid} (I/O)", linestyle="--")

        ax.set_title("Server Queues")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Queue Length")
        ax.legend()
        ax.grid(visible=True)

    def plot_ram_usage(self, ax: Axes) -> None:
        """Draw RAM usage over time onto the given Axes."""
        metrics = self.get_sampled_metrics()
        ram = metrics.get("ram_in_use", {})

        if not ram:
            ax.text(0.5, 0.5, "No RAM data", ha="center", va="center")
            return

        samples = len(next(iter(ram.values())))
        times = np.arange(samples) * self._settings.sample_period_s

        for sid, vals in ram.items():
            ax.plot(times, vals, label=f"{sid} RAM")

        ax.set_title("RAM Usage")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("RAM (MB)")
        ax.legend()
        ax.grid(visible=True)
