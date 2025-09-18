"""
SweepAnalyzer — build plots from a sweep over *mean rps*.

Global
------
- Throughput (mean RPS) vs. users
- Mean latency (W) vs. users
- (Opzionale) Latency percentiles vs. users

Per-server (overlay)
--------------------
- Utilization rho_i vs. users
- Waiting time Wq_i vs. users
- Service rate mu_i vs. users
- Throughput lambda_i vs. users
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

import matplotlib.pyplot as plt

from asyncflow.config.enums import LatencyKey

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer


# ──────────────────────────────────────────────────────────────────────
# Data containers
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GlobalPoint:
    """One sweep point (global/system metrics collected today)."""

    users: int
    lambda_rps: float          # mean throughput (RPS)
    W: float                   # mean end-to-end latency (s)
    p50: float                 # latency median (s)
    p95: float                 # latency P95 (s)
    p99: float                 # latency P99 (s)


@dataclass(frozen=True)
class ServerPoint:
    """One sweep point for a single server."""

    users: int
    server_id: str
    lambda_rps: float          # server throughput (estimated)
    mu_rps: float              # 1 / mean(service_time)
    rho: float                 # lambda / mu
    Wq: float                  # mean waiting time (s)
    service_mean_s: float      # mean service time (s)
    completions: int           # number of completed requests
    server_latency_mean_s: float


# ──────────────────────────────────────────────────────────────────────
# Analyzer
# ──────────────────────────────────────────────────────────────────────

class SweepAnalyzer:
    """
    Build plots from a sweep over *mean rps*.

    Input
    -----
    pairs : Iterable[tuple[int, ResultsAnalyzer]]
        Output of Sweep.sweep_on_user(...): (users, analyzer).

    Caching
    -------
    Collections are private and executed once. All plotters read from caches.
    """

    def __init__(self, pairs: Iterable[tuple[int, ResultsAnalyzer]]) -> None:
        """Initialize with (users, ResultsAnalyzer) pairs and prepare caches."""
        self._pairs: list[tuple[int, ResultsAnalyzer]] = sorted(
            (int(u), ra) for (u, ra) in pairs
        )
        # Caches
        self._global_points: list[GlobalPoint] = []
        self._server_points: dict[str, list[ServerPoint]] = {}
        self._collected_global: bool = False
        self._collected_servers: bool = False

    # ──────────────────────────────────────────────────────────────────
    # Public convenience
    # ──────────────────────────────────────────────────────────────────

    def precollect(self) -> None:
        """Warm both caches once (optional)."""
        self._ensure_global_collected()
        self._ensure_servers_collected()

    # ──────────────────────────────────────────────────────────────────
    # Private collectors (one-time)
    # ──────────────────────────────────────────────────────────────────

    def _ensure_global_collected(self) -> None:
        if self._collected_global:
            return
        self._collect_global()
        self._collected_global = True

    def _ensure_servers_collected(self) -> None:
        if self._collected_servers:
            return
        self._collect_servers()
        self._collected_servers = True

    def _collect_global(self) -> None:
        """Compute global/system metrics (throughput & latency) once."""
        out: list[GlobalPoint] = []

        for users, ra in self._pairs:
            # Ensure metrics are computed
            ra.process_all_metrics()

            # λ: mean throughput from the time series
            _, rps_series = ra.get_throughput_series()
            if rps_series:
                lambda_rps = float(sum(rps_series)) / float(len(rps_series))
            else:
                lambda_rps = 0.0

            # Latency stats → W and percentiles
            lat = ra.get_latency_stats()
            w_mean = float(lat.get(LatencyKey.MEAN, 0.0))
            p50 = float(lat.get(LatencyKey.MEDIAN, 0.0))
            p95 = float(lat.get(LatencyKey.P95, 0.0))
            p99 = float(lat.get(LatencyKey.P99, 0.0))

            out.append(
                GlobalPoint(
                    users=users,
                    lambda_rps=lambda_rps,
                    W=w_mean,
                    p50=p50,
                    p95=p95,
                    p99=p99,
                ),
            )

        self._global_points = out

    def _collect_servers(self) -> None:
        """
        Compute per-server metrics across the sweep once.

        Server throughput λᵢ is estimated via completions split:
            λᵢ ≈ (nᵢ / Σⱼ nⱼ) · λ_tot
        """
        points: dict[str, list[ServerPoint]] = {}

        for users, ra in self._pairs:
            ra.process_all_metrics()

            # Global lambda for proportional split
            _, rps_series = ra.get_throughput_series()
            lambda_tot = (
                float(sum(rps_series)) / float(len(rps_series))
                if rps_series
                else 0.0
            )

            arrays_map = cast(
                "dict[str, dict[str, list[float]]]",
                ra.get_server_event_arrays(),
            )
            sids = ra.list_server_ids()

            total_compl = 0
            per_server_compl: dict[str, int] = {}
            for sid in sids:
                arr_for_count: dict[str, list[float]] = arrays_map.get(sid, {})
                n = len(arr_for_count.get("finish_times", []))
                per_server_compl[sid] = n
                total_compl += n

            for sid in sids:
                arr: dict[str, list[float]] = arrays_map.get(sid, {})

                # μᵢ from mean(service_time)
                s_vals: list[float] = arr.get("service_time", [])
                if s_vals:
                    s_mean = float(sum(s_vals)) / float(len(s_vals))
                    mu = (1.0 / s_mean) if s_mean > 0.0 else float("inf")
                else:
                    s_mean = 0.0
                    mu = float("inf")

                # Wqᵢ from mean(waiting_time)
                wq_vals: list[float] = arr.get("waiting_time", [])
                wq_mean = (
                    float(sum(wq_vals)) / float(len(wq_vals))
                    if wq_vals
                    else 0.0
                )

                # server latency
                lat_vals: list[float] = arr.get("latencies", [])
                if lat_vals:
                    server_lat_mean = float(sum(lat_vals)) / float(len(lat_vals))
                else:
                    server_lat_mean = wq_mean + (
                        1.0 / mu if mu not in (0.0, float("inf")) else s_mean)

                # λᵢ via proportional split of completions
                n_i = per_server_compl.get(sid, 0)
                if total_compl > 0:
                    lambda_i = (n_i / float(total_compl)) * lambda_tot
                else:
                    lambda_i = 0.0

                # ρᵢ = λᵢ / μᵢ
                rho = (lambda_i / mu) if mu not in (0.0, float("inf")) else 0.0

                points.setdefault(sid, []).append(
                    ServerPoint(
                        users=users,
                        server_id=sid,
                        lambda_rps=lambda_i,
                        mu_rps=mu,
                        rho=rho,
                        Wq=wq_mean,
                        service_mean_s=s_mean,
                        completions=n_i,
                        server_latency_mean_s=server_lat_mean,
                    ),
                )

        self._server_points = points

    # ──────────────────────────────────────────────────────────────────
    # Global plotters (cached)
    # ──────────────────────────────────────────────────────────────────

    def plot_global_throughput(self, ax: Axes) -> None:
        """Plot mean throughput (RPS) vs. mean rps."""
        self._ensure_global_collected()
        pts = self._global_points
        xs = [p.users for p in pts]
        ys = [p.lambda_rps for p in pts]
        ax.plot(xs, ys, marker="o")
        ax.set_title("Throughput (mean RPS) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("RPS")
        ax.grid(visible=True, alpha=0.3)

    def plot_global_latency(self, ax: Axes) -> None:
        """Plot mean system time (W) vs. mean rps."""
        self._ensure_global_collected()
        pts = self._global_points
        xs = [p.users for p in pts]
        ys = [p.W for p in pts]
        ax.plot(xs, ys, marker="o")
        ax.set_title("Mean system time (W) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("W (seconds)")
        ax.grid(visible=True, alpha=0.3)

    def plot_global_latency_percentiles(self, ax: Axes) -> None:
        """Plot P50, P95, P99 latency vs. mean rps."""
        self._ensure_global_collected()
        pts = self._global_points
        xs = [p.users for p in pts]
        ax.plot(xs, [p.p50 for p in pts], marker="o", label="P50")
        ax.plot(xs, [p.p95 for p in pts], marker="o", label="P95")
        ax.plot(xs, [p.p99 for p in pts], marker="o", label="P99")
        ax.set_title("Latency percentiles vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("Latency (seconds)")
        ax.legend()
        ax.grid(visible=True, alpha=0.3)

    def plot_global_dashboard(self) -> Figure:
        """1x2 dashboard: throughput and mean latency (W)."""
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), dpi=130)
        self.plot_global_throughput(axes[0])
        self.plot_global_latency(axes[1])
        fig.tight_layout()
        return fig

    # ──────────────────────────────────────────────────────────────────
    # Per-server plotters (overlay; cached)
    # ──────────────────────────────────────────────────────────────────

    def _select_top_servers(
        self,
        by: Literal["rho", "Wq", "mu", "lambda"],
        max_servers: int,
    ) -> list[str]:
        """Pick up to `max_servers` “hottest” servers at max users (from cache)."""
        self._ensure_servers_collected()
        data = self._server_points
        if not data:
            return []

        max_users = max(
            (pt.users for pts in data.values() for pt in pts),
            default=0,
        )
        scores: list[tuple[str, float]] = []
        for sid, pts in data.items():
            at_max = [p for p in pts if p.users == max_users]
            if not at_max:
                continue
            p = at_max[-1]
            if by == "rho":
                val = p.rho
            elif by == "Wq":
                val = p.Wq
            elif by == "mu":
                val = -p.mu_rps if p.mu_rps not in (0.0, float("inf")) else -0.0
            else:  # "lambda"
                val = p.lambda_rps
            scores.append((sid, float(val)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [sid for sid, _ in scores[:max_servers]]

    def plot_server_utilization_overlay(
        self,
        ax: Axes,
        *,
        max_servers: int = 5,
        server_ids: list[str] | None = None,
    ) -> None:
        """Overlay of server utilization rho vs. users (auto-picks hottest)"""
        self._ensure_servers_collected()
        ids = server_ids or self._select_top_servers("rho", max_servers)
        for sid in sorted(ids):
            pts = self._server_points.get(sid, [])
            xs = [p.users for p in pts]
            ys = [p.rho for p in pts]
            ax.plot(xs, ys, marker="o", label=sid)
        ax.set_title("Server utilization (rho) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("rho")
        if ids:
            ax.legend()
        ax.grid(visible=True, alpha=0.3)

    def plot_server_waiting_time_overlay(
        self,
        ax: Axes,
        *,
        max_servers: int = 5,
        server_ids: list[str] | None = None,
    ) -> None:
        """Overlay of server waiting time Wqᵢ vs. users (auto-picks hottest)"""
        self._ensure_servers_collected()
        ids = server_ids or self._select_top_servers("Wq", max_servers)
        for sid in sorted(ids):
            pts = self._server_points.get(sid, [])
            xs = [p.users for p in pts]
            ys = [p.Wq for p in pts]
            ax.plot(xs, ys, marker="o", label=sid)
        ax.set_title("Server waiting time (Wq) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("Wq (seconds)")
        if ids:
            ax.legend()
        ax.grid(visible=True, alpha=0.3)

    def plot_server_service_rate_overlay(
        self,
        ax: Axes,
        *,
        max_servers: int = 5,
        server_ids: list[str] | None = None,
    ) -> None:
        """Overlay of server service rate μ vs. users (auto-picks hottest)"""
        self._ensure_servers_collected()
        ids = server_ids or self._select_top_servers("mu", max_servers)
        for sid in sorted(ids):
            pts = self._server_points.get(sid, [])
            xs = [p.users for p in pts]
            ys = [p.mu_rps for p in pts]
            ax.plot(xs, ys, marker="o", label=sid)
        ax.set_title("Server service rate (mu) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("mu (1/s)")
        if ids:
            ax.legend()
        ax.grid(visible=True, alpha=0.3)

    def plot_server_throughput_overlay(
        self,
        ax: Axes,
        *,
        max_servers: int = 5,
        server_ids: list[str] | None = None,
    ) -> None:
        """Overlay of server throughput λ vs. users (auto-picks hottest by default)."""
        self._ensure_servers_collected()
        ids = server_ids or self._select_top_servers("lambda", max_servers)
        for sid in sorted(ids):
            pts = self._server_points.get(sid, [])
            xs = [p.users for p in pts]
            ys = [p.lambda_rps for p in pts]
            ax.plot(xs, ys, marker="o", label=sid)
        ax.set_title("Server throughput (lambda) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("lambda (1/s)")
        if ids:
            ax.legend()
        ax.grid(visible=True, alpha=0.3)

    def plot_server_latency_overlay(
        self, ax: Axes, *, max_servers: int = 5, server_ids: list[str] | None = None,
    ) -> None:
        """Plot of the latency vs concurrent user"""
        self._ensure_servers_collected()
        ids = server_ids or self._select_top_servers("Wq", max_servers)
        for sid in sorted(ids):
            pts = self._server_points.get(sid, [])
            xs = [p.users for p in pts]
            ys = [p.server_latency_mean_s for p in pts]
            ax.plot(xs, ys, marker="o", label=sid)
        ax.set_title("Server latency (waiting+service) vs. mean Lambda_rps")
        ax.set_xlabel("mean rps")
        ax.set_ylabel("Server latency (s)")
        if ids:
            ax.legend()
        ax.grid(visible=True, alpha=0.3)


    def plot_server_dashboard(self) -> Figure:
        """2x3 per-server overlay: rho_i, Wq_i, mu_i, lambda_i, server latency."""
        fig, axes = plt.subplots(2, 3, figsize=(16, 8), dpi=130)

        # Row 1
        self.plot_server_utilization_overlay(axes[0, 0])
        self.plot_server_waiting_time_overlay(axes[0, 1])
        self.plot_server_service_rate_overlay(axes[0, 2])

        # Row 2
        self.plot_server_throughput_overlay(axes[1, 0])
        self.plot_server_latency_overlay(axes[1, 1])
        axes[1, 2].axis("off")  # keep layout symmetric

        fig.tight_layout()
        return fig

