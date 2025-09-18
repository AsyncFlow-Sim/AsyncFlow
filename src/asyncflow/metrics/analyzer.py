"""Module for post-simulation analysis and visualization."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

from asyncflow.config.constants import LatencyKey, SampledMetricName
from asyncflow.config.plot_constants import (
    LATENCY_PLOT,
    RAM_PLOT,
    SERVER_QUEUES_PLOT,
    THROUGHPUT_PLOT,
    PlotCfg,
)

if TYPE_CHECKING:
    # Standard library typing imports in type-checking block (TC003).
    from collections.abc import Iterable

    from matplotlib.axes import Axes
    from matplotlib.lines import Line2D

    from asyncflow.runtime.actors.client import ClientRuntime
    from asyncflow.runtime.actors.edge import EdgeRuntime
    from asyncflow.runtime.actors.server import ServerRuntime
    from asyncflow.schemas.settings.simulation import SimulationSettings


# Short alias to keep signatures within 88 chars (E501).
Series = tuple[list[float], list[float]]


class ResultsAnalyzer:
    """Analyze and visualize the results of a completed simulation.

    This class holds the raw runtime objects and lazily computes:
      - latency statistics
      - throughput time series (RPS)
      - sampled metrics from servers and edges

    It also exposes compact plotting/rendering helpers so that CLI scripts
    can be short and consistent.
    """

    # Default bucket size (seconds) used for cached throughput.
    _WINDOW_SIZE_S: float = 1.0

    def __init__(
        self,
        *,
        client: ClientRuntime,
        servers: list[ServerRuntime],
        edges: list[EdgeRuntime],
        settings: SimulationSettings,
    ) -> None:
        """Initialize with the runtime objects and original settings."""
        self._client = client
        self._servers = servers
        self._edges = edges
        self._settings = settings

        # Lazily computed caches
        self.latencies: list[float] | None = None
        self.latency_stats: dict[LatencyKey, float] | None = None
        self.throughput_series: Series | None = None
        # Sampled metrics are stored with string metric keys for simplicity.
        self.sampled_metrics: dict[str, dict[str, list[float]]] | None = None

    # ─────────────────────────────────────────────
    # Core computation
    # ─────────────────────────────────────────────
    def process_all_metrics(self) -> None:
        """Compute all aggregated and sampled metrics if not already done."""
        if self.latency_stats is None and self._client.rqs_clock:
            self._process_event_metrics()

        if self.sampled_metrics is None:
            self._extract_sampled_metrics()

    def _process_event_metrics(self) -> None:
        """Calculate latency stats and throughput time series (1s RPS)."""
        # 1) Latencies
        self.latencies = [
            clock.finish - clock.start
            for clock in self._client.rqs_clock
        ]

        # 2) Summary stats
        if self.latencies:
            arr = np.array(self.latencies, dtype=float)
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

        # 3) Throughput per 1s window (cached)
        completion_times = sorted(clock.finish for clock in self._client.rqs_clock)
        end_time = self._settings.total_simulation_time

        timestamps: list[float] = []
        rps_values: list[float] = []
        idx = 0
        current_end = ResultsAnalyzer._WINDOW_SIZE_S

        while current_end <= end_time:
            count = 0
            while idx < len(completion_times) and completion_times[idx] <= current_end:
                count += 1
                idx += 1
            timestamps.append(current_end)
            rps_values.append(count / ResultsAnalyzer._WINDOW_SIZE_S)
            current_end += ResultsAnalyzer._WINDOW_SIZE_S

        self.throughput_series = (timestamps, rps_values)

    def _extract_sampled_metrics(self) -> None:
        """Gather sampled metrics from servers and edges into a nested dict."""
        metrics: dict[str, dict[str, list[float]]] = defaultdict(dict)

        for server in self._servers:
            sid = server.server_config.id
            for name, values in server.enabled_metrics.items():
                # Store with string key for a consistent external API.
                metrics[name.value][sid] = values

        for edge in self._edges:
            eid = edge.edge_config.id
            for name, values in edge.enabled_metrics.items():
                metrics[name.value][eid] = values

        self.sampled_metrics = metrics

    # ─────────────────────────────────────────────
    # Public accessors & formatting
    # ─────────────────────────────────────────────
    def list_server_ids(self) -> list[str]:
        """Return server IDs in a stable order as given in the topology."""
        return [s.server_config.id for s in self._servers]

    def get_latency_stats(self) -> dict[LatencyKey, float]:
        """Return latency statistics, computing them if necessary."""
        self.process_all_metrics()
        return self.latency_stats or {}

    def format_latency_stats(self) -> str:
        """Return a human-readable block with latency stats."""
        stats = self.get_latency_stats()
        if not stats:
            return "Latency stats: (empty)"

        by_name: dict[str, float] = {
            getattr(k, "name", str(k)): v
            for k, v in stats.items()
        }
        order = [
            "TOTAL_REQUESTS",
            "MEAN",
            "MEDIAN",
            "STD_DEV",
            "P95",
            "P99",
            "MIN",
            "MAX",
        ]

        lines = ["════════ LATENCY STATS ════════"]
        # PERF401: build then extend instead of append in a loop.
        formatted = [
            f"{k:<20} = {by_name[k]:.6f}"
            for k in order
            if k in by_name
        ]
        lines.extend(formatted)
        return "\n".join(lines)

    def get_throughput_series(
        self,
        window_s: float | None = None,
    ) -> Series:
        """Return (timestamps, RPS). If `window_s` is provided, recompute on the fly."""
        self.process_all_metrics()

        # Use cached (1s) series when suitable.
        if window_s is None or window_s == ResultsAnalyzer._WINDOW_SIZE_S:
            return self.throughput_series or ([], [])

        # Recompute with a custom window size.
        completion_times = sorted(clock.finish for clock in self._client.rqs_clock)
        end_time = self._settings.total_simulation_time

        timestamps: list[float] = []
        rps_values: list[float] = []
        idx = 0
        current_end = float(window_s)

        while current_end <= end_time:
            count = 0
            while idx < len(completion_times) and completion_times[idx] <= current_end:
                count += 1
                idx += 1
            timestamps.append(current_end)
            rps_values.append(count / float(window_s))
            current_end += float(window_s)

        return (timestamps, rps_values)

    def get_sampled_metrics(self) -> dict[str, dict[str, list[float]]]:
        """Return sampled metrics from servers and edges."""
        self.process_all_metrics()
        assert self.sampled_metrics is not None
        return self.sampled_metrics

    def get_metric_map(self, key: SampledMetricName | str) -> dict[str, list[float]]:
        """Return a series map for a metric, tolerant to enum/string keys."""
        self.process_all_metrics()
        assert self.sampled_metrics is not None

        if isinstance(key, SampledMetricName):
            # Prefer the canonical .value key; fall back to .name.
            found = (
                self.sampled_metrics.get(key.value)
                or self.sampled_metrics.get(key.name, {})
            )
            return found or {}
        # If caller used a raw string:
        return self.sampled_metrics.get(key, {})

    def get_series(self, key: SampledMetricName | str, entity_id: str) -> Series:
        """Return (times, values) for a given sampled metric and entity id."""
        series_map = self.get_metric_map(key)
        vals = series_map.get(entity_id, [])
        times = (np.arange(len(vals)) * self._settings.sample_period_s).tolist()
        return times, vals

    # ─────────────────────────────────────────────
    # Plotting helpers
    # ─────────────────────────────────────────────
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

    def plot_base_dashboard(self, ax_latency: Axes, ax_throughput: Axes) -> None:
        """Plot a 2x1 header: latency histogram + throughput line."""
        self.plot_latency_distribution(ax_latency)
        self.plot_throughput(ax_throughput)

    def plot_latency_distribution(self, ax: Axes) -> None:
        """Plot latency histogram with mean/P50/P95/P99 lines and a single
        legend box with values.
        """
        self.process_all_metrics()
        if not self.latencies:
            ax.text(0.5, 0.5, LATENCY_PLOT.no_data, ha="center", va="center")
            return

        # Colors that pop on blue/white
        col_mean = "#d62728"   # red
        col_p50 = "#ff7f0e"    # orange
        col_p95 = "#2ca02c"    # green
        col_p99 = "#9467bd"    # purple
        hist_color = "#1f77b4" # soft blue

        arr = np.asarray(self.latencies, dtype=float)
        v_mean = float(np.mean(arr))
        v_p50 = float(np.percentile(arr, 50))
        v_p95 = float(np.percentile(arr, 95))
        v_p99 = float(np.percentile(arr, 99))

        # Histogram (subtle to let overlays stand out)
        ax.hist(
            arr, bins=50, color=hist_color, alpha=0.40,
            edgecolor="none", zorder=1,
        )

        # Vertical overlays
        ax.axvline(
            v_mean, color=col_mean, linestyle=":", linewidth=1.8,
            alpha=0.95, zorder=3,
        )
        ax.axvline(
            v_p50, color=col_p50, linestyle="-.", linewidth=1.6,
            alpha=0.90, zorder=3,
        )
        ax.axvline(
            v_p95, color=col_p95, linestyle="--", linewidth=1.6,
            alpha=0.90, zorder=3,
        )
        ax.axvline(
            v_p99, color=col_p99, linestyle="--", linewidth=1.6,
            alpha=0.90, zorder=3,
        )

        # Build legend handles (dummy lines, no data)
        h_mean = ax.plot(
            [], [], color=col_mean, linestyle=":", linewidth=2.4,
            label=f"mean = {v_mean:.3f}",
        )[0]
        h_p50 = ax.plot(
            [], [], color=col_p50, linestyle="-.", linewidth=2.4,
            label=f"P50  = {v_p50:.3f}",
        )[0]
        h_p95 = ax.plot(
            [], [], color=col_p95, linestyle="--", linewidth=2.4,
            label=f"P95  = {v_p95:.3f}",
        )[0]
        h_p99 = ax.plot(
            [], [], color=col_p99, linestyle="--", linewidth=2.4,
            label=f"P99  = {v_p99:.3f}",
        )[0]

        # Titles / labels / grid
        self._apply_plot_cfg(ax, LATENCY_PLOT)

        # Legend (top-right) with readable background
        leg = ax.legend(
            handles=[h_mean, h_p50, h_p95, h_p99],
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            borderaxespad=0.0,
            framealpha=0.90,
            fancybox=True,
            handlelength=2.6,
            fontsize=9.5,
        )
        leg.get_frame().set_facecolor("white")


    def plot_throughput(self, ax: Axes, *, window_s: float | None = None) -> None:
        """Plot throughput with mean/P95/max lines, EWMA curve, and a single
        legend box with values.
        """
        timestamps, values = self.get_throughput_series(window_s=window_s)
        if not timestamps:
            ax.text(0.5, 0.5, THROUGHPUT_PLOT.no_data, ha="center", va="center")
            return

        # Colors (high contrast on blue/white)
        col_series = "#1f77b4"  # blue main series
        col_mean = "#d62728"    # red
        col_p95 = "#2ca02c"     # green
        col_max = "#9467bd"     # purple


        vals = np.asarray(values, dtype=float)
        v_mean = float(np.mean(vals))
        v_p95 = float(np.percentile(vals, 95))
        v_max = float(np.max(vals))

        # Main series
        ax.plot(
            timestamps, vals, marker="o", linewidth=1.6, alpha=0.95,
            color=col_series, zorder=2,
        )

        # Horizontal overlays (match legend colors)
        ax.axhline(
            v_mean, color=col_mean, linestyle=":", linewidth=1.8,
            alpha=0.95, zorder=4,
        )
        ax.axhline(
            v_p95, color=col_p95, linestyle="--", linewidth=1.6,
            alpha=0.90, zorder=4,
        )
        ax.axhline(
            v_max, color=col_max, linestyle="--", linewidth=1.6,
            alpha=0.90, zorder=4,
        )

        # Legend handles (dummy, no data)
        h_mean = ax.plot(
            [], [], color=col_mean, linestyle=":", linewidth=2.4,
            label=f"mean = {v_mean:.3f}",
        )[0]
        h_p95 = ax.plot(
            [], [], color=col_p95, linestyle="--", linewidth=2.4,
            label=f"P95  = {v_p95:.3f}",
        )[0]
        h_max = ax.plot(
            [], [], color=col_max, linestyle="--", linewidth=2.4,
            label=f"max  = {v_max:.3f}",
        )[0]

        # Apply base cfg (titles/labels/grid)
        self._apply_plot_cfg(ax, THROUGHPUT_PLOT)

        # Legend: upper-right; single box with values
        leg = ax.legend(
            handles=[h_mean, h_p95, h_max],
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            borderaxespad=0.0,
            framealpha=0.90,
            fancybox=True,
            handlelength=2.6,
            fontsize=9.5,
        )
        leg.get_frame().set_facecolor("white")



    def plot_single_server_ready_queue(self, ax: Axes, server_id: str) -> None:
        """Plot Ready queue with mean/min/max lines and a single legend box with
        values. No trend/ewma, no legend entry for the main series.
        """
        times, vals = self.get_series(SampledMetricName.READY_QUEUE_LEN, server_id)
        if not vals:
            ax.text(0.5, 0.5, SERVER_QUEUES_PLOT.no_data, ha="center", va="center")
            return

        # Colors consistent with other charts
        col_mean = "#d62728"   # red
        col_min = "#2ca02c"    # green
        col_max = "#9467bd"    # purple

        y = np.asarray(vals, dtype=float)
        v_mean = float(np.mean(y))
        v_min = float(np.min(y))
        v_max = float(np.max(y))

        # Main series (no label/legend as requested)
        ax.plot(times, y, linewidth=1.6, alpha=0.95)

        # Overlays
        ax.axhline(v_mean, color=col_mean, linestyle=":", linewidth=1.8, alpha=0.95)
        ax.axhline(v_min, color=col_min, linestyle="--", linewidth=1.6, alpha=0.90)
        ax.axhline(v_max, color=col_max, linestyle="--", linewidth=1.6, alpha=0.90)

        # Legend handles (dummy lines with values)
        h_mean = ax.plot(
            [], [], color=col_mean, linestyle=":", linewidth=2.4,
            label=f"mean = {v_mean:.3f}",
        )[0]
        h_min = ax.plot(
            [], [], color=col_min, linestyle="--", linewidth=2.4,
            label=f"min  = {v_min:.3f}",
        )[0]
        h_max = ax.plot(
            [], [], color=col_max, linestyle="--", linewidth=2.4,
            label=f"max  = {v_max:.3f}",
        )[0]

        ax.set_title(f"Ready Queue — {server_id}")
        ax.set_xlabel(SERVER_QUEUES_PLOT.x_label)
        ax.set_ylabel(SERVER_QUEUES_PLOT.y_label)
        ax.grid(visible=True)

        leg = ax.legend(
            handles=[h_mean, h_min, h_max],
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            borderaxespad=0.0,
            framealpha=0.90,
            fancybox=True,
            handlelength=2.6,
            fontsize=9.5,
        )
        leg.get_frame().set_facecolor("white")

    def plot_single_server_io_queue(self, ax: Axes, server_id: str) -> None:
        """Plot I/O queue with mean/min/max lines and a single legend box with
        values. No trend/ewma, no legend entry for the main series.
        """
        times, vals = self.get_series(SampledMetricName.EVENT_LOOP_IO_SLEEP, server_id)
        if not vals:
            ax.text(0.5, 0.5, SERVER_QUEUES_PLOT.no_data, ha="center", va="center")
            return

        col_mean = "#d62728"   # red
        col_min = "#2ca02c"    # green
        col_max = "#9467bd"    # purple

        y = np.asarray(vals, dtype=float)
        v_mean = float(np.mean(y))
        v_min = float(np.min(y))
        v_max = float(np.max(y))

        ax.plot(times, y, linewidth=1.6, alpha=0.95)

        ax.axhline(v_mean, color=col_mean, linestyle=":", linewidth=1.8, alpha=0.95)
        ax.axhline(v_min, color=col_min, linestyle="--", linewidth=1.6, alpha=0.90)
        ax.axhline(v_max, color=col_max, linestyle="--", linewidth=1.6, alpha=0.90)

        h_mean = ax.plot(
            [], [], color=col_mean, linestyle=":", linewidth=2.4,
            label=f"mean = {v_mean:.3f}",
        )[0]
        h_min = ax.plot(
            [], [], color=col_min, linestyle="--", linewidth=2.4,
            label=f"min  = {v_min:.3f}",
        )[0]
        h_max = ax.plot(
            [], [], color=col_max, linestyle="--", linewidth=2.4,
            label=f"max  = {v_max:.3f}",
        )[0]

        ax.set_title(f"I/O Queue — {server_id}")
        ax.set_xlabel(SERVER_QUEUES_PLOT.x_label)
        ax.set_ylabel(SERVER_QUEUES_PLOT.y_label)
        ax.grid(visible=True)

        leg = ax.legend(
            handles=[h_mean, h_min, h_max],
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            borderaxespad=0.0,
            framealpha=0.90,
            fancybox=True,
            handlelength=2.6,
            fontsize=9.5,
        )
        leg.get_frame().set_facecolor("white")



    def plot_single_server_ram(self, ax: Axes, server_id: str) -> None:
        """Plot RAM usage with mean/min/max lines and a single legend box with
        values. No trend/ewma, no legend entry for the main series.
        """
        times, vals = self.get_series(SampledMetricName.RAM_IN_USE, server_id)
        if not vals:
            ax.text(0.5, 0.5, RAM_PLOT.no_data, ha="center", va="center")
            return

        col_mean = "#d62728"   # red
        col_min = "#2ca02c"    # green
        col_max = "#9467bd"    # purple

        y = np.asarray(vals, dtype=float)
        v_mean = float(np.mean(y))
        v_min = float(np.min(y))
        v_max = float(np.max(y))

        ax.plot(times, y, linewidth=1.6, alpha=0.95)

        ax.axhline(v_mean, color=col_mean, linestyle=":", linewidth=1.8, alpha=0.95)
        ax.axhline(v_min, color=col_min, linestyle="--", linewidth=1.6, alpha=0.90)
        ax.axhline(v_max, color=col_max, linestyle="--", linewidth=1.6, alpha=0.90)

        h_mean = ax.plot(
            [], [], color=col_mean, linestyle=":", linewidth=2.4,
            label=f"mean = {v_mean:.3f}",
        )[0]
        h_min = ax.plot(
            [], [], color=col_min, linestyle="--", linewidth=2.4,
            label=f"min  = {v_min:.3f}",
        )[0]
        h_max = ax.plot(
            [], [], color=col_max, linestyle="--", linewidth=2.4,
            label=f"max  = {v_max:.3f}",
        )[0]

        ax.set_title(f"{RAM_PLOT.title} — {server_id}")
        ax.set_xlabel(RAM_PLOT.x_label)
        ax.set_ylabel(RAM_PLOT.y_label)
        ax.grid(visible=True)

        leg = ax.legend(
            handles=[h_mean, h_min, h_max],
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            borderaxespad=0.0,
            framealpha=0.90,
            fancybox=True,
            handlelength=2.6,
            fontsize=9.5,
        )
        leg.get_frame().set_facecolor("white")
