"""
Check if asyncflow under the hypothesis of a MMc queue
(c >= 1), reproduce the theory.
"""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING, Literal, TextIO, TypedDict, cast
from weakref import WeakSet

from asyncflow.config.enums import (
    Distribution,
    EndpointStepCPU,
    LatencyKey,
    LbAlgorithmsName,
    SampledMetricName,
)
from asyncflow.queue_theory_analysis.base import QueueTheoryBase
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.topology.edges import LinkEdge

if TYPE_CHECKING:

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload


class MMcParams(TypedDict):
    """
    Minimal global parameters for the M/M/c split model (round-robin into
    per-server queues). These are either directly specified by the payload
    or trivially derived and also observable from runs.

    - lambda_rate (λ): arrival rate [1/s]
    - mu_rate (μ): per-server service rate [1/s]
    - c: number of parallel servers (c >= 1)
    - rho (rho = λ/(cμ)): global utilization (stability requires rho < 1)
    - a (λ/μ): offered load (expected busy servers); derivable and observable
    - capacity_rate (cμ): total service capacity [1/s]
    """

    lambda_rate: float
    mu_rate: float
    c: int                  # c >= 1
    rho: float              # rho = λ / (c * μ)
    a: float                # λ / μ
    capacity_rate: float    # c * μ

MMcResultKey = Literal["lambda_rate", "mu_rate", "c", "rho", "L", "Lq", "W", "Wq"]

class MMcResults(TypedDict):
    """
    Closed-form KPIs for the M/M/c split model (round-robin), restricted to
    quantities you can also measure from the simulator (no Erlang-C terms).

    Exposes:
    - (λ, μ, c, rho) for clarity/logging and cross-checks
    - L, Lq via Little's Law (L = λW, Lq = λWq)
    - W, Wq (mean system time and mean waiting time)
    """

    # Parameters (echoed for convenience)
    lambda_rate: float
    mu_rate: float
    c: int
    rho: float

    # Queue sizes and times (all observable)
    L: float                # mean jobs in system
    Lq: float               # mean jobs in queue
    W: float                # mean time in system [s]
    Wq: float               # mean waiting time [s]



class MMcKPIRow(TypedDict):
    """
    One formatted row for theory vs observed comparison (M/M/c).
    Same shape as the MM1 KPIRow; separate name to avoid collisions.
    """

    symbol: str
    name: str
    theory: float | str
    observed: float | str
    abs_diff: float | str
    rel_diff_pct: float | str  # percentage (e.g., "3.2" means +3.2%)


class MMcCompatGlobalRow(TypedDict):
    """Row for global compatibility checks."""

    scope: str   # "topology" | "generator" | "edges"
    issue: str   # human-readable message


class MMcCompatServerRow(TypedDict):
    """Row for per-server compatibility checks."""

    server_index: int
    server_id: str
    issue: str


class MMc(QueueTheoryBase):
    """Analyzer for the M/M/c split model (Round-Robin), c>=1, with strict checks."""

    def __init__(self) -> None:
        """Track analyzers we've already processed; weak refs avoid leaks."""
        self._processed_ras: WeakSet[ResultsAnalyzer] = WeakSet()

    # ──────────────────────────────────────────────────────────────────
    # Compatibility checks split into helpers to keep cyclomatic low
    # ──────────────────────────────────────────────────────────────────
    def _check_topology(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        nodes = payload.topology_graph.nodes
        c = len(nodes.servers)

        if c == 0:
            errs.append("requires at least one server.")
            return errs

        lb = nodes.load_balancer
        if c == 1:
            if lb is not None:
                errs.append("for c=1 the load balancer must be absent.")
        elif lb is None:
            errs.append("for c>1 a load balancer is required.")
        elif lb.algorithms not in {LbAlgorithmsName.RANDOM, LbAlgorithmsName.FCFS}:
             errs.append("supported lb algorithms: RANDOM (split) or FCFS (pooled).")

        return errs

    def _check_generator(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        arrivals = payload.arrivals
        if arrivals.model not in {Distribution.POISSON, Distribution.EXPONENTIAL}:
            errs.append("arrivals.model must be 'poisson' or 'exponential'.")
        return errs

    def _check_edges(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        if not payload.topology_graph.edges:
            errs.append("topology must include at least one edge.")
            return errs
        # In pydantic we define edges to be only of type Network or Link
        # The types are mutually exclusive hence we have to be sure only
        # one edge is of the link type
        edge = payload.topology_graph.edges[0]
        if not isinstance(edge, LinkEdge):
            errs.append(
                "In MMc models edges are just connector, use link_edge as a type",
            )
        return errs

    def _check_server_model(self, payload: SimulationPayload) -> list[str]:
        errs: list[str] = []
        servers = payload.topology_graph.nodes.servers

        mu_ref: float | None = None
        for idx, server in enumerate(servers):
            if len(server.endpoints) != 1:
                errs.append(f"server[{idx}] must expose exactly one endpoint.")
                continue

            steps = server.endpoints[0].steps
            if len(steps) != 1:
                errs.append(f"server[{idx}] endpoint must contain exactly one step.")
                continue

            step = steps[0]
            if not isinstance(step.kind, EndpointStepCPU):
                errs.append(f"server[{idx}] single step must be CPU-bound.")
                continue

            # Pydantic già fa CPU_TIME → qui prendiamo solo i parametri RV
            _, op_data = next(iter(step.step_operation.items()))

            if not isinstance(op_data, RVConfig):
                errs.append(
                    f"server[{idx}] service time must be an exponential RVConfig.")
                continue
            if op_data.distribution != Distribution.EXPONENTIAL:
                errs.append(
                    f"server[{idx}] service time distribution must be exponential.")
                continue
            if op_data.mean <= 0:
                errs.append(
                    f"server[{idx}] service time mean must be > 0.")
                continue

            mu_i = 1.0 / float(op_data.mean)
            if mu_ref is None:
                mu_ref = mu_i
            # identicità dei server (tolleranza numerica)
            elif abs(mu_i - mu_ref) > 1e-12 * max(1.0, mu_ref):
                errs.append(
                    f"all servers must be identical; "
                    f"found different μ at server[{idx}].",
                )

        return errs

    # ------------- Compatibility (public) --------------------------------
    def explain_incompatibilities(
        self, payload: SimulationPayload,
    ) -> list[str]:
        """Collect and return all MMc assumption violations."""
        errors: list[str] = []
        errors.extend(self._check_topology(payload))
        errors.extend(self._check_generator(payload))
        errors.extend(self._check_edges(payload))
        # Only check server model if we do have servers
        if payload.topology_graph.nodes.servers:
            errors.extend(self._check_server_model(payload))
        return errors

    # ------------- private method to build dict from theory --------------

    def _arrival_rate_lambda_rate(self, payload: SimulationPayload) -> float:
        """λ = users_mean * rpm_per_user / 60."""
        return payload.arrivals.lambda_rps


    def _service_rate_mu_rate(self, payload: SimulationPayload) -> float:
        """μ = 1 / E[S] from the (identical) CPU exponential step."""
        server0 = payload.topology_graph.nodes.servers[0]
        step0 = server0.endpoints[0].steps[0]
        _, rv = next(iter(step0.step_operation.items()))
        rv_cfg = cast("RVConfig", rv)
        return 1.0 / float(rv_cfg.mean)


    def _server_count(self, payload: SimulationPayload) -> int:
        """C = number of parallel servers."""
        return len(payload.topology_graph.nodes.servers)


    def _total_capacity_rate(self, server_count: int, mu_rate: float) -> float:
        """Total capacity = c * μ [1/s]."""
        return server_count * mu_rate


    def _rho_from(
        self,
        lambda_rate: float,
        server_count: int,
        mu_rate: float,
    ) -> float:
        """Rho = λ / (c * μ)."""
        capacity = server_count * mu_rate
        return (lambda_rate / capacity) if capacity > 0.0 else float("inf")


    def _offered_load_a(self, lambda_rate: float, mu_rate: float) -> float:
        """A = λ / μ (expected busy servers)."""
        return (lambda_rate / mu_rate) if mu_rate > 0.0 else float("inf")


    def _build_params(self, payload: SimulationPayload) -> MMcParams:
        """Build MMcParams (theory) from payload."""
        lambda_rate = self._arrival_rate_lambda_rate(payload)
        mu_rate = self._service_rate_mu_rate(payload)
        server_count = self._server_count(payload)
        capacity_rate = self._total_capacity_rate(server_count, mu_rate)
        rho = self._rho_from(lambda_rate, server_count, mu_rate)
        offered_load = self._offered_load_a(lambda_rate, mu_rate)
        return MMcParams(
            lambda_rate=lambda_rate,
            mu_rate=mu_rate,
            c=server_count,
            rho=rho,
            a=offered_load,
            capacity_rate=capacity_rate,
        )

    # ────────────────────────────────────────────────────────────────────
    # Centralized RA processing (avoid repeated processing)
    # ────────────────────────────────────────────────────────────────────

    def _ensure_metrics_processed(
        self,
        results_analyzer: ResultsAnalyzer,
    ) -> None:
        """Call process_all_metrics() at most once per ResultsAnalyzer."""
        if results_analyzer not in self._processed_ras:
            results_analyzer.process_all_metrics()
            self._processed_ras.add(results_analyzer)


    # ────────────────────────────────────────────────────────────────────
    # Helpers: observed (from ResultsAnalyzer)
    # ────────────────────────────────────────────────────────────────────

    def _observed_lambda_rate(self, results_analyzer: ResultsAnalyzer) -> float:
        """Estimate λ̂ from throughput series (mean RPS)."""
        self._ensure_metrics_processed(results_analyzer)
        _, rps_series = results_analyzer.get_throughput_series()
        return (sum(rps_series) / len(rps_series)) if rps_series else 0.0


    def _observed_mu_rate(self, results_analyzer: ResultsAnalyzer) -> float:
        """
        Estimate μ̂ = 1 / mean(service_time) aggregating all servers
        (weighted by number of jobs per server).
        """
        self._ensure_metrics_processed(results_analyzer)
        arrays_map = results_analyzer.get_server_event_arrays()

        service_time_sum: float = 0.0
        service_time_count: int = 0
        for arrays in arrays_map.values():
            values = arrays.get("service_time") or []
            service_time_sum += float(sum(values))
            service_time_count += len(values)

        mean_service_time = (
            service_time_sum / service_time_count if service_time_count > 0 else 0.0
        )
        return (1.0 / mean_service_time) if mean_service_time > 0.0 else float("inf")


    def _build_observed_params(
        self,
        payload: SimulationPayload,
        results_analyzer: ResultsAnalyzer,
    ) -> MMcParams:
        """Build MMcParams using observed λ̂, μ̂ and c from payload."""
        observed_lambda_rate = self._observed_lambda_rate(results_analyzer)
        observed_mu_rate = self._observed_mu_rate(results_analyzer)
        server_count = self._server_count(payload)
        capacity_rate = self._total_capacity_rate(server_count, observed_mu_rate)
        observed_rho = self._rho_from(
            observed_lambda_rate,
            server_count,
            observed_mu_rate,
        )
        observed_a = self._offered_load_a(
            observed_lambda_rate,
            observed_mu_rate,
        )
        return MMcParams(
            lambda_rate=observed_lambda_rate,
            mu_rate=observed_mu_rate,
            c=server_count,
            rho=observed_rho,
            a=observed_a,
            capacity_rate=capacity_rate,
        )

    # ────────────────────────────────────────────────────────────────────
    # Closed form (Random): theory → MMcResults split model ( n parallel mm1)
    # ────────────────────────────────────────────────────────────────────

    def _theoretical_kpis_split(self, payload: SimulationPayload) -> MMcResults:
        """
        Closed forms for Random split: λ_i=λ/c;
        Wq=rho/(μ-λ_i); W=1/μ+Wq; Lq=λWq; L=λW
        """
        self.validate_or_raise(payload)
        params = self._build_params(payload)

        lambda_rate = params["lambda_rate"]
        mu_rate = params["mu_rate"]
        server_count = params["c"]
        rho = params["rho"]

        if rho >= 1.0:
            inf = float("inf")
            return MMcResults(
                lambda_rate=lambda_rate,
                mu_rate=mu_rate,
                c=server_count,
                rho=rho,
                L=inf,
                Lq=inf,
                W=inf,
                Wq=inf,
            )

        per_server_lambda = lambda_rate / server_count
        denom = (mu_rate - per_server_lambda)
        wq = rho / denom if denom > 0.0 else float("inf")
        w = (1.0 / mu_rate) + wq
        lq = lambda_rate * wq
        l_sys = lambda_rate * w

        return MMcResults(
            lambda_rate=lambda_rate,
            mu_rate=mu_rate,
            c=server_count,
            rho=rho,
            L=l_sys,
            Lq=lq,
            W=w,
            Wq=wq,
        )


    def _theoretical_mmc_erlang_c_kpis(
        self,
        lambda_rate: float,
        mu_rate: float,
        c: int,
    ) -> MMcResults:
        """Closed forms for pooled M/M/c (FCFS, Erlang-C)."""
        rho = self._rho_from(lambda_rate, c, mu_rate)
        if rho >= 1.0:
            inf = float("inf")
            return MMcResults(
                lambda_rate=lambda_rate,
                mu_rate=mu_rate,
                c=c,
                rho=rho,
                L=inf, Lq=inf, W=inf, Wq=inf,
            )

        a = lambda_rate / mu_rate  # offered traffic
        # P0
        s = sum((a**n) / math.factorial(n) for n in range(c))
        tail = (a**c) / math.factorial(c) * (1.0 / (1.0 - rho))
        p0 = 1.0 / (s + tail)
        pw = ((a**c) / math.factorial(c)) * (1.0 / (1.0 - rho)) * p0
        lq = pw * (rho / (1.0 - rho))
        wq = lq / lambda_rate
        w = wq + 1.0 / mu_rate
        lam = lambda_rate * w

        return MMcResults(
            lambda_rate=lambda_rate,
            mu_rate=mu_rate,
            c=c,
            rho=rho,
            L=lam,
            Lq=lq,
            W=w,
            Wq=wq,
        )

    def _theoretical_kpis_pooled(self, payload: SimulationPayload) -> MMcResults:
        """Closed forms for pooled M/M/c (LB=FCFS, central queue)."""
        # riusa i builder che hai già
        params = self._build_params(payload)
        return self._theoretical_mmc_erlang_c_kpis(
            lambda_rate=params["lambda_rate"],
            mu_rate=params["mu_rate"],
            c=params["c"],
    )


    def evaluate(self, payload: SimulationPayload) -> MMcResults:
        """Return closed-form KPIs: split (RR/RANDOM) or pooled (FCFS)."""
        self.validate_or_raise(payload)
        lb = payload.topology_graph.nodes.load_balancer
        if (lb is not None) and (lb.algorithms == LbAlgorithmsName.FCFS):
            return self._theoretical_kpis_pooled(payload)
        # default: split (random/RR)
        return self._theoretical_kpis_split(payload)


    # ────────────────────────────────────────────────────────────────────
    # Observed KPIs → MMcResults (coerenti con definizioni sopra)
    # ────────────────────────────────────────────────────────────────────

    def _observed_kpis(
        self,
        payload: SimulationPayload,
        results_analyzer: ResultsAnalyzer,
    ) -> MMcResults:
        """
        Empirical KPIs:
        - λ̂: mean throughput
        - μ̂: 1 / mean(service_time)
        - Ŵ: mean client latency
        - Wq̂: FCFS -> mean LB waits; else -> mean server waiting_time
        - L̂: FCFS -> mean L_SYSTEM; else -> λ̂ * Ŵ
        - Lq̂: FCFS -> mean LQ_LB; else -> λ̂ * Wq̂
        - rho: FCFS -> mean SERVER_UTILIZATION; else -> λ̂ / (c μ̂)
        all computations are independent: we calculate each
        variable in a separate way
        """
        self._ensure_metrics_processed(results_analyzer)

        lambda_hat = self._observed_lambda_rate(results_analyzer)
        mu_hat = self._observed_mu_rate(results_analyzer)
        server_count = self._server_count(payload)

        # Ŵ from latency stats (generator-side);
        lat_stats = results_analyzer.get_latency_stats()
        w_hat = float(lat_stats.get(LatencyKey.MEAN, 0.0))

        lb = payload.topology_graph.nodes.load_balancer
        is_fcfs = (lb is not None) and (lb.algorithms == LbAlgorithmsName.FCFS)

        # Collect waiting time from LB if the algo is FCFS
        if is_fcfs:
            # --- L̂: mean L_SYSTEM timeseries (fallback λ̂·Ŵ) ---
            lsys_map = results_analyzer.get_metric_map(SampledMetricName.L_SYSTEM)
            aid = payload.arrivals.id
            lsys_series = lsys_map.get(aid, [])
            l_hat = (
                (sum(lsys_series) / len(lsys_series))
                if lsys_series else (lambda_hat * w_hat)
            )

            # --- Wq̂: keep LB waiting times ---
            lb_waits = list(results_analyzer.get_lb_waiting_times())
            wq_hat = (sum(lb_waits) / len(lb_waits)) if lb_waits else 0.0

            # --- Lq̂: mean LQ_LB timeseries (fallback λ̂·Wq̂) ---
            lq_map = results_analyzer.get_metric_map(SampledMetricName.LQ_LB)
            lb_id = lb.id if lb is not None else None
            lq_series = lq_map.get(lb_id, []) if lb_id is not None else []
            lq_hat = (
                (sum(lq_series) / len(lq_series))
                if lq_series else (lambda_hat * wq_hat)
            )

            # ---- rho  mean SERVER_UTILIZATION timeseries (fallback λ̂/(cμ̂)) ---
            util_map = (
                results_analyzer.get_metric_map(SampledMetricName.SERVER_UTILIZATION)
            )
            total_busy = 0.0
            total_samples = 0
            for series in util_map.values():
                total_busy += float(sum(series))
                total_samples += len(series)
            rho_hat = (total_busy / total_samples) if total_samples > 0 else (
                lambda_hat / (server_count * mu_hat)
                if mu_hat not in (0.0, float("inf")) else 0.0
        )

        else:
            arrays_map = results_analyzer.get_server_event_arrays()
            wait_sum = 0.0
            wait_count = 0
            for arrays in arrays_map.values():
                vals = arrays.get("waiting_time") or []
                wait_sum += float(sum(vals))
                wait_count += len(vals)
            wq_hat = (wait_sum / wait_count) if wait_count > 0 else 0.0

            l_hat = lambda_hat * w_hat
            lq_hat = lambda_hat * wq_hat
            rho_hat = (
                lambda_hat / (server_count * mu_hat)
                if mu_hat not in (0.0, float("inf")) else 0.0
            )

        return MMcResults(
            lambda_rate=lambda_hat,
            mu_rate=mu_hat,
            c=server_count,
            rho=rho_hat,
            L=l_hat,
            Lq=lq_hat,
            W=w_hat,
            Wq=wq_hat,
        )

    # ────────────────────────────────────────────────────────────────────
    # Comparison table (same shape as MM1, senza Erlang terms)
    # ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_delta(theory_value: float, observed_value: float) -> tuple[str, str, str]:
        """Return (theory_str, abs_diff_str, rel_diff_str) with inf-safe logic."""
        def fmt(x: float) -> str:
            return "∞" if x == float("inf") else f"{x:.6f}"
        theory_str = fmt(theory_value)
        if theory_value == float("inf"):
            return theory_str, "—", "—"
        abs_diff = observed_value - theory_value
        rel_pct = (
            abs_diff / theory_value * 100.0
            ) if theory_value != 0.0 else float("inf")
        rel_str = "∞" if rel_pct == float("inf") else f"{rel_pct:.2f}"
        return theory_str, f"{abs_diff:.6f}", rel_str


    def compare_against_run(
        self,
        payload: SimulationPayload,
        results_analyzer: ResultsAnalyzer,
    ) -> list[MMcKPIRow]:
        """Build a table with theory vs observed and deltas."""
        self.validate_or_raise(payload)

        lb = payload.topology_graph.nodes.load_balancer
        if (lb is not None) and (lb.algorithms == LbAlgorithmsName.FCFS):
            theory = self._theoretical_kpis_pooled(payload)
        else:
            theory = self._theoretical_kpis_split(payload)

        observed = self._observed_kpis(payload, results_analyzer)

        rows: list[MMcKPIRow] = []

        def add(symbol: str, name: str, key: MMcResultKey) -> None:
            theory_value = float(theory[key])
            observed_value = float(observed[key])
            th_s, abs_s, rel_s = self._safe_delta(theory_value, observed_value)
            rows.append(
                MMcKPIRow(
                    symbol=symbol,
                    name=name,
                    theory=th_s,
                    observed=f"{observed_value:.6f}",
                    abs_diff=abs_s,
                    rel_diff_pct=rel_s,
                ),
            )

        add("λ", "Arrival rate (1/s)", "lambda_rate")
        add("μ", "Service rate (1/s)", "mu_rate")
        add("rho", "Utilization", "rho")
        add("L", "Mean items in sys", "L")
        add("Lq", "Mean items in queue", "Lq")
        add("W", "Mean time in sys (s)", "W")
        add("Wq", "Mean waiting (s)", "Wq")

        return rows

    # ────────────────────────────────────────────────────────────────────
    # Pretty table (KPI):
    # ────────────────────────────────────────────────────────────────────

    def _title_for(self, payload: SimulationPayload) -> str:
        lb = payload.topology_graph.nodes.load_balancer
        if lb is not None and lb.algorithms == LbAlgorithmsName.FCFS:
            return "MMc (FCFS/Erlang-C) — Theory vs Observed"
        # default to random split when no LB or non-FCFS
        return "MMc (Random split) — Theory vs Observed"

    @staticmethod
    def _format_kpi_table(
        rows: list[MMcKPIRow],
        title: str = "MMc — Theory vs Observed",
    ) -> str:
        data = [
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
        w_sym = max(len(headers[0]), *(len(d[0]) for d in data))
        w_met = max(len(headers[1]), *(len(d[1]) for d in data))
        w_th  = max(len(headers[2]), *(len(d[2]) for d in data))
        w_ob  = max(len(headers[3]), *(len(d[3]) for d in data))
        w_abs = max(len(headers[4]), *(len(d[4]) for d in data))
        w_rel = max(len(headers[5]), *(len(d[5]) for d in data))

        header = (
            f"{headers[0]:<{w_sym}}  {headers[1]:<{w_met}}  "
            f"{headers[2]:>{w_th}}  {headers[3]:>{w_ob}}  "
            f"{headers[4]:>{w_abs}}  {headers[5]:>{w_rel}}"
        )
        sep = "-" * len(header)
        top = "=" * max(len(title), len(header))

        lines = [top, title, sep, header, sep]
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
        results_analyzer: ResultsAnalyzer,
    ) -> str:
        """Compare theoretical and simulated results"""
        rows = self.compare_against_run(payload, results_analyzer)
        title = self._title_for(payload)
        return self._format_kpi_table(rows, title=title)

    def print_comparison(
        self,
        payload: SimulationPayload,
        results_analyzer: ResultsAnalyzer,
        *,
        file: TextIO | None = None,
    ) -> None:
        """Print the MMc KPI table (theory vs observed)."""
        out = self.compare_and_format(payload, results_analyzer)
        stream: TextIO = sys.stdout if file is None else file
        print(out, file=stream)

