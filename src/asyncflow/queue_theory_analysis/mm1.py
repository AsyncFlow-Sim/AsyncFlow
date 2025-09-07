"""
Check if asyncflow under the hypothesis of a mm1 queue
reproduce the theory.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO, TypedDict, cast

from asyncflow.config.constants import (
    Distribution,
    EndpointStepCPU,
    LatencyKey,
    StepOperation,
)
from asyncflow.queue_theory_analysis.base import QueueTheoryBase
from asyncflow.schemas.common.random_variables import RVConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload


class MM1Results(TypedDict):
    """Closed-form KPIs for an M/M/1 queue."""

    lambda_rate: float  # arrival rate (1/s)
    mu_rate: float      # service rate (1/s)
    rho: float          # utilization
    L: float            # mean items in system
    Lq: float           # mean items in queue
    W: float            # mean time in system (s)
    Wq: float           # mean waiting time (s)


class KPIRow(TypedDict):
    """One formatted row for theory vs observed comparison."""

    symbol: str
    name: str
    theory: float | str
    observed: float | str
    abs_diff: float | str
    rel_diff_pct: float | str  # percentage (e.g., "3.2" means +3.2%)


class MM1(QueueTheoryBase):
    """Analyzer for the M/M/1 queue with strict model checks."""

    # Upper bound for "negligible" deterministic network latency
    MAX_EDGE_LATENCY_S: float = 1e-3  # 1 ms

    # ──────────────────────────────────────────────────────────────────
    # Compatibility checks split into helpers to keep cyclomatic low
    # ──────────────────────────────────────────────────────────────────
    def _check_topology(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        nodes = payload.topology_graph.nodes
        if len(nodes.servers) != 1:
            errs.append("requires exactly one server (no parallel servers).")
        if nodes.load_balancer is not None:
            errs.append("load balancer must be absent (fan-out not allowed).")
        return errs

    def _check_generator(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        gen = payload.rqs_input
        if gen.avg_active_users.distribution != Distribution.POISSON:
            errs.append("avg_active_users must be Poisson.")
        if gen.avg_request_per_minute_per_user.distribution != Distribution.POISSON:
            errs.append("avg_request_per_minute_per_user must be Poisson.")
        if gen.avg_active_users.mean <= 0:
            errs.append("avg_active_users.mean must be > 0.")
        if gen.avg_request_per_minute_per_user.mean <= 0:
            errs.append("avg_request_per_minute_per_user.mean must be > 0.")
        return errs

    def _check_edges(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        for edge in payload.topology_graph.edges:
            latency = edge.latency
            if isinstance(latency, RVConfig):
                errs.append(
                    f"edge '{edge.id}' latency must be deterministic (<=1ms), "
                    "not a random variable.",
                )
                continue
            if float(latency) > self.MAX_EDGE_LATENCY_S:
                errs.append(
                    f"edge '{edge.id}' deterministic latency must be <= 1 ms.",
                )
        return errs

    def _check_server_model(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        srv = payload.topology_graph.nodes.servers[0]
        if len(srv.endpoints) != 1:
            errs.append("server must expose exactly one endpoint.")
            return errs

        steps = srv.endpoints[0].steps
        if len(steps) != 1:
            errs.append("endpoint must contain exactly one step.")
            return errs

        step = steps[0]
        if not isinstance(step.kind, EndpointStepCPU):
            errs.append("the single step must be CPU-bound.")
            return errs

        op_key, op_data = next(iter(step.step_operation.items()))
        if op_key is not StepOperation.CPU_TIME:
            errs.append("CPU step must use CPU_TIME as its operation.")
            return errs

        # Must be exponential RV (not deterministic)
        if not isinstance(op_data, RVConfig):
            errs.append("service time must be an exponential RVConfig.")
            return errs
        if op_data.distribution != Distribution.EXPONENTIAL:
            errs.append("service time distribution must be exponential.")
        if op_data.mean <= 0:
            errs.append("service time mean must be > 0.")
        return errs

    # ------------- Compatibility (public) --------------------------------
    def explain_incompatibilities(
        self, payload: SimulationPayload,
    ) -> list[str]:
        """Collect and return all MM1 assumption violations."""
        errors: list[str] = []
        errors.extend(self._check_topology(payload))
        errors.extend(self._check_generator(payload))
        errors.extend(self._check_edges(payload))
        # Only check server model if we do have servers
        if payload.topology_graph.nodes.servers:
            errors.extend(self._check_server_model(payload))
        return errors

    # ──────────────────────────────────────────────────────────────────
    # Closed forms
    # ──────────────────────────────────────────────────────────────────
    def _arrival_rate_lambda(self, payload: SimulationPayload) -> float:
        """λ = users_mean * rpm_per_user / 60."""
        gen = payload.rqs_input
        users = float(gen.avg_active_users.mean)
        rpm = float(gen.avg_request_per_minute_per_user.mean)
        return users * rpm / 60.0

    def _service_rate_mu(self, payload: SimulationPayload) -> float:
        """μ = 1 / E[S] from the single CPU exponential step."""
        srv = payload.topology_graph.nodes.servers[0]
        step = srv.endpoints[0].steps[0]
        op_key, op_val = next(iter(step.step_operation.items()))
        assert op_key is StepOperation.CPU_TIME
        rv = cast("RVConfig", op_val)
        assert rv.distribution is Distribution.EXPONENTIAL
        return 1.0 / float(rv.mean)

    def _theoretical_kpis(self, payload: SimulationPayload) -> MM1Results:
        """Closed-form KPIs. For rho>=1 returns +inf for divergent metrics."""
        self.validate_or_raise(payload)

        lam = self._arrival_rate_lambda(payload)
        mu = self._service_rate_mu(payload)
        rho = lam / mu

        if rho >= 1.0:
            inf = float("inf")
            return MM1Results(
                lambda_rate=lam,
                mu_rate=mu,
                rho=rho,
                L=inf,
                Lq=inf,
                W=inf,
                Wq=inf,
            )

        l_sys = rho / (1.0 - rho)
        lq = (rho * rho) / (1.0 - rho)
        w_sys = 1.0 / (mu - lam)
        wq = rho / (mu - lam)

        return MM1Results(
            lambda_rate=lam,
            mu_rate=mu,
            rho=rho,
            L=l_sys,
            Lq=lq,
            W=w_sys,
            Wq=wq,
        )

    def evaluate(self, payload: SimulationPayload) -> MM1Results:
        """Public entry-point: return closed-form KPIs for this payload."""
        return self._theoretical_kpis(payload)


    # ──────────────────────────────────────────────────────────────────
    # Observed KPIs from a run (no private members)
    # ──────────────────────────────────────────────────────────────────
    def _observed_kpis(self, ra: ResultsAnalyzer) -> MM1Results:
        """
        Empirical KPIs from the analyzer:
          - lambda_hat: average throughput across windows
          - mu_hat: 1 / mean(service_time)
          - W_hat: mean end-to-end latency (client)
          - Wq_hat: mean waiting_time (server arrays)
          - L_hat: lambda_hat * W_hat   (Little's law)
          - Lq_hat: lambda_hat * Wq_hat
        """
        ra.process_all_metrics()

        # λ̂ via throughput series (mean of window RPS)
        ts, rps = ra.get_throughput_series()
        lambda_hat = (sum(rps) / len(rps)) if rps else 0.0

        # Ŵ from latency stats
        lat_stats = ra.get_latency_stats()
        w_hat = float(lat_stats.get(LatencyKey.MEAN, 0.0))

        # Per-server arrays (first server if present)
        server_ids = ra.list_server_ids()
        arrays_map = ra.get_server_event_arrays()
        arrays = arrays_map.get(server_ids[0]) if server_ids else None

        # mean service time and wait
        if arrays and arrays["service_time"]:
            s_vals = arrays["service_time"]
            s_mean = float(sum(s_vals)) / float(len(s_vals))
        else:
            s_mean = 0.0
        mu_hat = (1.0 / s_mean) if s_mean > 0.0 else float("inf")

        if arrays and arrays["waiting_time"]:
            wq_vals = arrays["waiting_time"]
            wq_hat = float(sum(wq_vals)) / float(len(wq_vals))
        else:
            wq_hat = 0.0

        l_hat = lambda_hat * w_hat
        lq_hat = lambda_hat * wq_hat
        rho_hat = (
            lambda_hat / mu_hat if mu_hat not in (0.0, float("inf")) else 0.0
        )

        return MM1Results(
            lambda_rate=lambda_hat,
            mu_rate=mu_hat,
            rho=rho_hat,
            L=l_hat,
            Lq=lq_hat,
            W=w_hat,
            Wq=wq_hat,
        )

    # ──────────────────────────────────────────────────────────────────
    # Comparison table
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _safe_delta(theory: float, obs: float) -> tuple[str, str, str]:
        """Return (theory_str, abs_diff_str, rel_diff_str) with inf-safe logic."""
        def fmt(x: float) -> str:
            return "∞" if x == float("inf") else f"{x:.6f}"

        th_s = fmt(theory)
        if theory == float("inf"):
            return th_s, "—", "—"

        abs_d = obs - theory
        rel = (abs_d / theory * 100.0) if theory != 0.0 else float("inf")
        rel_s = "∞" if rel == float("inf") else f"{rel:.2f}"
        return th_s, f"{abs_d:.6f}", rel_s

    def compare_against_run(
        self,
        payload: SimulationPayload,
        ra: ResultsAnalyzer,
    ) -> list[KPIRow]:
        """
        Build a table with theory vs observed and absolute/relative deltas.

        Returns
        -------
        list[KPIRow]
            Rows in a stable order suitable for printing or DataFrame usage.

        """
        self.validate_or_raise(payload)

        th = self._theoretical_kpis(payload)
        ob = self._observed_kpis(ra)

        rows: list[KPIRow] = []

        def add(symbol: str, name: str, getter: Callable[[MM1Results], float]) -> None:
            th_v = float(getter(th))
            ob_v = float(getter(ob))
            th_s, abs_s, rel_s = self._safe_delta(th_v, ob_v)
            rows.append(
                KPIRow(
                    symbol=symbol,
                    name=name,
                    theory=th_s,
                    observed=f"{ob_v:.6f}",
                    abs_diff=abs_s,
                    rel_diff_pct=rel_s,
                ),
            )

        add("λ", "Arrival rate (1/s)", lambda m: m["lambda_rate"])
        add("μ", "Service rate (1/s)", lambda m: m["mu_rate"])
        add("rho", "Utilization", lambda m: m["rho"])
        add("L", "Mean items in system", lambda m: m["L"])
        add("Lq", "Mean items in queue", lambda m: m["Lq"])
        add("W", "Mean time in system (s)", lambda m: m["W"])
        add("Wq", "Mean waiting time (s)",  lambda m: m["Wq"])

        return rows

    # ──────────────────────────────────────────────────────────────────
    # Pretty printing
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_rows_table(rows: list[KPIRow]) -> str:
        """
        Return a compact ASCII table for `compare_against_run(...)` rows.

        The layout is stable, with right-aligned numeric columns and widths
        computed from the data for nice alignment in plain-text consoles.
        """
        # Extract as strings (observed/theory already formatted in rows).
        data: list[tuple[str, str, str, str, str, str]] = [
            (
                r["symbol"],
                r["name"],
                str(r["theory"]),
                str(r["observed"]),
                str(r["abs_diff"]),
                str(r["rel_diff_pct"]),
            )
            for r in rows
        ]

        headers = ("sym", "metric", "theory", "observed", "abs", "rel%")

        # Compute column widths.
        w_sym = max(len(headers[0]), *(len(d[0]) for d in data))
        w_met = max(len(headers[1]), *(len(d[1]) for d in data))
        w_th  = max(len(headers[2]), *(len(d[2]) for d in data))
        w_ob  = max(len(headers[3]), *(len(d[3]) for d in data))
        w_abs = max(len(headers[4]), *(len(d[4]) for d in data))
        w_rel = max(len(headers[5]), *(len(d[5]) for d in data))

        # Title and separators sized to the header length.
        header_line = (
            f"{headers[0]:<{w_sym}}  {headers[1]:<{w_met}}  "
            f"{headers[2]:>{w_th}}  {headers[3]:>{w_ob}}  "
            f"{headers[4]:>{w_abs}}  {headers[5]:>{w_rel}}"
        )
        sep = "-" * len(header_line)
        title = "MM1 - Theory vs Observed"
        top = "=" * max(len(title), len(header_line))

        lines: list[str] = [
            top,
            title,
            sep,
            header_line,
            sep,
        ]

        for sym, met, th, ob, ad, rd in data:
            lines.append(
                f"{sym:<{w_sym}}  {met:<{w_met}}  "
                f"{th:>{w_th}}  {ob:>{w_ob}}  {ad:>{w_abs}}  {rd:>{w_rel}}",
            )

        lines.append(top)
        return "\n".join(lines)

    def compare_and_format(
        self,
        payload: SimulationPayload,
        ra: ResultsAnalyzer,
    ) -> str:
        """
        Convenience: run `compare_against_run()` and return a formatted table.

        Use this when you want a ready-to-print string for logs/CLI output.
        """
        rows = self.compare_against_run(payload, ra)
        return self._format_rows_table(rows)

    def print_comparison(
        self,
        payload: SimulationPayload,
        ra: ResultsAnalyzer,
        *,
        file: TextIO | None = None,
    ) -> None:
        """
        Print a pretty 'theory vs observed' table to the given stream.

        Parameters
        ----------
        payload : SimulationPayload
            The validated simulation payload.
        ra : ResultsAnalyzer
            Results analyzer with processed metrics.
        file : TextIO | None
            Output stream (defaults to stdout).

        """
        out = self.compare_and_format(payload, ra)
        stream: TextIO = sys.stdout if file is None else file
        print(out, file=stream)

