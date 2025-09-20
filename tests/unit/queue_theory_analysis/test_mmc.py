"""Basic golden test for the MMc analyzer (RR split model).

This file intentionally contains both helpers and the first test,
so you can copy-paste a single file and extend incrementally.

It uses only public facades (like a pip-installed user would),
plus `LatencyKey` which MMc reads from `get_latency_stats()`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

from asyncflow import AsyncFlow
from asyncflow.analysis import MMc
from asyncflow.components import (
    ArrivalsGenerator,
    Client,
    Endpoint,
    LinkEdge,
    LoadBalancer,
    NetworkEdge,
    Server,
)

# Public facades (end-user API)
from asyncflow.config.enums import LatencyKey, LbAlgorithmsName, SampledMetricName
from asyncflow.enums import Distribution
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import NodesResources, TopologyNodes
from asyncflow.settings import SimulationSettings

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer

class _FakeResultsAnalyzerFCFS:
    """
    FCFS stub that returns:
      - throughput series (lambda)
      - server arrays with service_time → mu_hat
      - latency stats (W)
      - LB waiting times (Wq_hat source)
      - sampled metric maps for:
          * L_SYSTEM[arrivals_id]
          * LQ_LB[lb_id]
          * SERVER_UTILIZATION per server
    """

    def __init__( # noqa: PLR0913
        self,
        *,
        arrivals_id: str,
        lb_id: str,
        server_ids: Iterable[str],
        lambda_rps: float,
        mu_rate: float,
        w_mean: float,
        lb_waits: Iterable[float],
        l_system_series: Iterable[float],
        lq_lb_series: Iterable[float],
        server_util_series: dict[str, list[float]],
    ) -> None:
        self._arrivals_id = arrivals_id
        self._lb_id = lb_id
        self._server_ids = list(server_ids)
        self._lambda = float(lambda_rps)
        self._mu = float(mu_rate)
        self._w = float(w_mean)
        self._lb_waits = tuple(float(x) for x in lb_waits)
        self._l_system_series = [float(x) for x in l_system_series]
        self._lq_lb_series = [float(x) for x in lq_lb_series]
        self._server_util_series = {
            k: [float(v) for v in vs] for k, vs in server_util_series.items()
        }
    # ---- interface expected by MMc ----
    def process_all_metrics(self) -> None:  # no-op
        return

    def get_throughput_series(self) -> tuple[list[float], list[float]]:
        times = [float(i) for i in range(10)]
        return times, [self._lambda for _ in times]

    def get_server_event_arrays(self) -> Mapping[str, Mapping[str, list[float]]]:
        # Only service_time matters in FCFS branch for mu_hat (fallback)
        es = 1.0 / self._mu if self._mu > 0.0 else 0.0
        return {sid: {"service_time": [es] * 50} for sid in self._server_ids}

    def get_latency_stats(self) -> Mapping[LatencyKey, float]:
        return {LatencyKey.MEAN: self._w}

    def list_server_ids(self) -> list[str]:
        return list(self._server_ids)

    def get_metric_map(self, key: SampledMetricName | str) -> dict[str, list[float]]:
        if isinstance(key, SampledMetricName):
            key = key.value
        if key == SampledMetricName.L_SYSTEM.value:
            return {self._arrivals_id: list(self._l_system_series)}
        if key == SampledMetricName.LQ_LB.value:
            return {self._lb_id: list(self._lq_lb_series)}
        if key == SampledMetricName.SERVER_UTILIZATION.value:
            return dict(self._server_util_series)
        return {}

    def get_lb_waiting_times(self) -> tuple[float, ...]:
        return self._lb_waits


class _FakeResultsAnalyzer:
    """Minimal, typed stub of ResultsAnalyzer for unit testing MMc.

    Provide exactly what MMc calls:
      - process_all_metrics()
      - get_throughput_series()
      - get_server_event_arrays()
      - get_latency_stats()
    """

    def __init__(
        self,
        *,
        lambda_rps: float,
        mu_rate: float,
        w_mean: float,
        wq_mean: float,
        server_ids: Iterable[str],
    ) -> None:
        self._lambda_rps = float(lambda_rps)
        self._mu_rate = float(mu_rate)
        self._w_mean = float(w_mean)
        self._wq_mean = float(wq_mean)
        self._server_ids = list(server_ids)

    def process_all_metrics(self) -> None:
        """No-op in the stub; real analyzer would pre-compute metrics."""
        return

    def get_throughput_series(self) -> tuple[list[float], list[float]]:
        """Return a constant-RPS series with mean equal to lambda."""
        times = [float(i) for i in range(10)]
        rps = [self._lambda_rps for _ in times]
        return times, rps

    def get_server_event_arrays(self) -> Mapping[str, Mapping[str, list[float]]]:
        """Return arrays per server for service and waiting times.

        Means are set so the observed mu and Wq match the theoretical ones.
        """
        es = 1.0 / self._mu_rate if self._mu_rate > 0.0 else 0.0
        out: dict[str, dict[str, list[float]]] = {}
        for sid in self._server_ids:
            out[sid] = {
                "service_time": [es] * 50,
                "waiting_time": [self._wq_mean] * 50,
            }
        return out

    def get_latency_stats(self) -> Mapping[LatencyKey, float]:
        """Expose the mean latency using the LatencyKey expected by MMc."""
        return {LatencyKey.MEAN: self._w_mean}

    def list_server_ids(self) -> list[str]:
        return list(self._server_ids)

    def get_metric_map(
        self, _key: SampledMetricName | str) -> dict[str, list[float]]:
        """Return a sampled-metric map. In this stub we return empty dicts."""
        return {}

    def get_lb_waiting_times(self) -> tuple[float, ...]:
        """FCFS-only series; return empty in the stub."""
        return ()

def _build_payload_mmc_split(
    *,
    lambda_rps: float = 20.0,
    cpu_mean_s: float = 0.01,
    c: int = 2,
) -> SimulationPayload:
    """Build a minimal payload compatible with MMc split (RR/random) assumptions.

    - c identical servers
    - 1 exponential CPU step per server
    - deterministic tiny latencies (≤ 1 ms)
    - load balancer with algorithms="random" (matches current MMc check)
    """
    gen = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=lambda_rps,
        model="poisson",
    )

    client = Client(id="client-1")

    endpoint = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {
                "kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": cpu_mean_s, "distribution": "exponential"},
                },
            },
        ],
    )

    servers = [
        Server(
            id=f"srv-{i+1}",
            server_resources={"cpu_cores": 1, "ram_mb": 2048},
            endpoints=[endpoint],
        )
        for i in range(c)
    ]

    lb = LoadBalancer(
        id="lb-1",
        algorithms="random",
        server_covered={s.id for s in servers},
    )

    edges = [
        LinkEdge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
        ),
        LinkEdge(
            id="client-lb",
            source="client-1",
            target="lb-1",

        ),
    ]

    for s in servers:
        edges.append(
            LinkEdge(
                id=f"lb-{s.id}",
                source="lb-1",
                target=s.id,

            ),
        )
        edges.append(
            LinkEdge(
                id=f"{s.id}-client",
                source=s.id,
                target="rqs-1",
            ),
        )

    settings = SimulationSettings(
        total_simulation_time=60,
        sample_period_s=0.05,
    )

    return (
        AsyncFlow()
        .add_arrivals_generator(gen)
        .add_client(client)
        .add_servers(*servers)
        .add_load_balancer(lb)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    ).build_payload()


def _build_payload_mmc_fcfs(
    *,
    lambda_rps: float = 270.0,
    cpu_mean_s: float = 0.01,  # mu = 100 rps
    c: int = 3,
) -> SimulationPayload:
    """Like _build_payload_mmc_split but with a pooled FCFS LB."""
    gen = ArrivalsGenerator(
        id="rqs-1", lambda_rps=lambda_rps, model=Distribution.POISSON)
    client = Client(id="client-1")

    endpoint = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[{"kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": cpu_mean_s, "distribution": "exponential"},
                    }}],
    )

    servers = [
        Server(
            id=f"srv-{i+1}",
            server_resources={"cpu_cores": 1, "ram_mb": 2048},
            endpoints=[endpoint],
        )
        for i in range(c)
    ]

    lb = LoadBalancer(
        id="lb-1",
        algorithms=LbAlgorithmsName.FCFS,            # pooled queue
        server_covered={s.id for s in servers},
    )

    edges = [
        LinkEdge(id="gen-client",  source="rqs-1",  target="client-1"),
        LinkEdge(id="client-lb",   source="client-1", target="lb-1"),
    ]
    for s in servers:
        edges.append(LinkEdge(id=f"lb-{s.id}",  source="lb-1", target=s.id))
        edges.append(LinkEdge(id=f"{s.id}-cl",  source=s.id,   target="rqs-1"))

    settings = SimulationSettings(total_simulation_time=60, sample_period_s=0.05)

    return (
        AsyncFlow()
        .add_arrivals_generator(gen)
        .add_client(client)
        .add_servers(*servers)
        .add_load_balancer(lb)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    ).build_payload()




# ---------------------------------------------------------------------------
# Extra tests for MMc
# ---------------------------------------------------------------------------

def test_mmc_instability_returns_infinities() -> None:
    """If rho >= 1, closed-form KPIs must be +inf (W, Wq, L, Lq)."""
    # c = 1, mu = 100 rps (service = 0.01 s) -> capacity = 100 rps.
    # For instability set lambda >= 100.

    client = Client(id="client-1")
    endpoint = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {
                "kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": 0.01, "distribution": "exponential"},
                },
            },
        ],
    )  # 0.01 s -> mu = 100 rps
    srv = Server(
        id="srv-1",
        server_resources=NodesResources(cpu_cores=2),
        endpoints=[endpoint],
    )

    # Minimal LinkEdge topology (MMc expects LinkEdge, not NetworkEdge).
    edges = [
        LinkEdge(id="gen-client", source="gen", target="client-1"),
        LinkEdge(id="client-srv", source="client-1", target="srv-1"),
        LinkEdge(id="srv-client", source="srv-1", target="client-1"),
    ]

    nodes = TopologyNodes(servers=[srv], client=client, load_balancer=None)
    graph = TopologyGraph(nodes=nodes, edges=edges)

    # λ = 200 rps (>= capacity 100) -> rho >= 1
    arrivals = ArrivalsGenerator(
        id="gen", lambda_rps=200.0, model=Distribution.POISSON,
    )

    settings = SimulationSettings(total_simulation_time=5)
    payload = SimulationPayload(
        arrivals=arrivals, topology_graph=graph, sim_settings=settings,
    )

    mmc = MMc()
    res = mmc.evaluate(payload)

    assert res["rho"] >= 1.0
    for key in ("W", "Wq", "L", "Lq"):
        assert res[key] == float("inf")


def test_mmc_incompatible_server_model_requires_single_cpu_step() -> None:
    """Each server endpoint must have exactly one CPU step."""
    gen = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=20,
        model="poisson",
    )
    client = Client(id="client-1")

    # Valid endpoint (1 CPU step)
    endpoint_ok = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {
                "kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": 0.01, "distribution": "exponential"},
                },
            },
        ],
    )
    # Invalid endpoint (2 CPU steps)
    endpoint_bad = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {
                "kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": 0.01, "distribution": "exponential"},
                },
            },
            {
                "kind": "initial_parsing",
                "step_operation": {
                    "cpu_time": {"mean": 0.01, "distribution": "exponential"},
                },
            },
        ],
    )

    srv1 = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint_ok],
    )
    srv2 = Server(
        id="srv-2",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint_bad],
    )
    lb = LoadBalancer(
        id="lb-1",
        algorithms="random",
        server_covered={"srv-1", "srv-2"},
    )
    edges = [
        LinkEdge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
        ),
        LinkEdge(
            id="client-lb",
            source="client-1",
            target="lb-1",
        ),
        LinkEdge(
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
        ),
        LinkEdge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
        ),
        LinkEdge(
            id="srv1-client",
            source="srv-1",
            target="client-1",
        ),
        LinkEdge(
            id="srv2-client",
            source="srv-2",
            target="client-1",
        ),
    ]
    settings = SimulationSettings(
        total_simulation_time=60,
        sample_period_s=0.05,
    )
    payload = (
        AsyncFlow()
        .add_arrivals_generator(gen)
        .add_client(client)
        .add_servers(srv1, srv2)
        .add_load_balancer(lb)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    ).build_payload()

    mmc = MMc()
    assert not mmc.is_compatible(payload)
    reasons = mmc.explain_incompatibilities(payload)
    assert any("exactly one step" in r for r in reasons)


def test_mmc_split_theory_closed_form_matches_manual() -> None:
    """
    Split (RR/random): Wq = rho / (mu - lambda/c);
    W = 1/mu + Wq; L = lambda W; Lq = lambda Wq.
    """
    payload = _build_payload_mmc_split(lambda_rps=40, cpu_mean_s=0.01, c=2)
    mmc = MMc()
    res = mmc.evaluate(payload)

    lam = 40.0
    mu  = 100.0
    c   = 2
    rho = lam / (c * mu)
    lam_i = lam / c
    wq_manual = rho / (mu - lam_i)
    w_manual  = (1.0 / mu) + wq_manual
    lq_manual = lam * wq_manual
    l_manual  = lam * w_manual

    assert math.isclose(float(res["rho"]), rho, rel_tol=1e-12)
    assert math.isclose(float(res["Wq"]), wq_manual, rel_tol=1e-12)
    assert math.isclose(float(res["W"]),  w_manual,  rel_tol=1e-12)
    assert math.isclose(float(res["Lq"]), lq_manual, rel_tol=1e-12)
    assert math.isclose(float(res["L"]),  l_manual,  rel_tol=1e-12)


def test_mmc_observed_split_from_stub_independent_and_consistent() -> None:
    """
    Observed KPIs for split path come independently
    from stubbed series/arrays.
    """
    payload = _build_payload_mmc_split(lambda_rps=50, cpu_mean_s=0.02, c=4)
    mmc = MMc()

    fake = _FakeResultsAnalyzer(
        lambda_rps=50.0,    # mean throughput
        mu_rate=50.0,        # service rate from service_time = 0.02
        w_mean=0.08,         # mean client latency
        wq_mean=0.06,        # mean waiting_time (server arrays)
        server_ids=[f"srv-{i+1}" for i in range(4)],
    )

    obs = mmc._observed_kpis(payload, cast("ResultsAnalyzer", fake)) # noqa: SLF001

    # Direct expectations from stub:
    assert math.isclose(float(obs["lambda_rate"]), 50.0, rel_tol=1e-12)
    assert math.isclose(float(obs["mu_rate"]),     50.0, rel_tol=1e-12)
    assert math.isclose(float(obs["W"]),           0.08, rel_tol=1e-12)
    assert math.isclose(float(obs["Wq"]),          0.06, rel_tol=1e-12)
    # Derived via split fallbacks:
    assert math.isclose(float(obs["L"]),  50.0 * 0.08, rel_tol=1e-12)
    assert math.isclose(float(obs["Lq"]), 50.0 * 0.06, rel_tol=1e-12)
    # rho from lambda/(c*mu) since mu_hat is finite
    assert math.isclose(float(obs["rho"]), 50.0 / (4 * 50.0), rel_tol=1e-12)

def test_mmc_pooled_fcfs_theory_matches_erlang_c_manual() -> None:
    """Pooled FCFS (Erlang-C) closed forms match manual computation."""
    payload = _build_payload_mmc_fcfs(lambda_rps=270.0, cpu_mean_s=0.01, c=3)
    mmc = MMc()
    res = mmc.evaluate(payload)

    lam = 270.0
    mu  = 100.0
    c   = 3
    rho = lam / (c * mu)  # 0.9

    # Manual Erlang-C
    a = lam / mu
    s = sum((a**n) / math.factorial(n) for n in range(c))
    tail = (a**c) / math.factorial(c) * (1.0 / (1.0 - rho))
    p0 = 1.0 / (s + tail)
    pw = ((a**c) / math.factorial(c)) * (1.0 / (1.0 - rho)) * p0
    lq = pw * (rho / (1.0 - rho))
    wq = lq / lam
    w  = wq + 1.0 / mu
    l_sys  = lam * w

    assert math.isclose(float(res["rho"]), rho, rel_tol=1e-12)
    assert math.isclose(float(res["Wq"]),  wq,  rel_tol=1e-12)
    assert math.isclose(float(res["W"]),   w,   rel_tol=1e-12)
    assert math.isclose(float(res["Lq"]),  lq,  rel_tol=1e-12)
    assert math.isclose(float(res["L"]),   l_sys,   rel_tol=1e-12)


def test_mmc_observed_fcfs_uses_lb_and_series_over_fallbacks() -> None:
    payload = _build_payload_mmc_fcfs(lambda_rps=270.0, cpu_mean_s=0.01, c=3)
    mmc = MMc()

    # FCFS series: choose simple values, compute means from them
    l_system = [10.0, 10.0, 11.0]
    l_system_mean = sum(l_system) / len(l_system)

    lq_lb = [7.1, 7.3]
    lq_lb_mean = sum(lq_lb) / len(lq_lb)

    lb_waits = [0.02, 0.03]
    wq_mean = sum(lb_waits) / len(lb_waits)  # 0.025

    # Utilization series (per server) -> mean = 0.5 overall
    util = {
        "srv-1": [1.0, 1.0, 0.0, 0.0],
        "srv-2": [1.0, 0.0, 1.0, 0.0],
        "srv-3": [0.0, 1.0, 0.0, 1.0],
    }

    fake = _FakeResultsAnalyzerFCFS(
        arrivals_id="rqs-1",
        lb_id="lb-1",
        server_ids=["srv-1", "srv-2", "srv-3"],
        lambda_rps=270.0,
        mu_rate=100.0,     # from service_time=0.01
        w_mean=0.036,      # any value; L comes from L_SYSTEM series
        lb_waits=lb_waits,
        l_system_series=l_system,
        lq_lb_series=lq_lb,
        server_util_series=util,
    )

    obs = mmc._observed_kpis(payload, cast("ResultsAnalyzer", fake))  # noqa: SLF001

    assert math.isclose(float(obs["lambda_rate"]), 270.0, rel_tol=1e-12)
    assert math.isclose(float(obs["mu_rate"]), 100.0, rel_tol=1e-12)
    # FCFS path must prefer series over fallbacks:
    assert math.isclose(float(obs["Wq"]), wq_mean, rel_tol=1e-12)
    assert math.isclose(float(obs["Lq"]), lq_lb_mean, rel_tol=1e-12)
    assert math.isclose(float(obs["L"]), l_system_mean, rel_tol=1e-12)
    # rho from mean SERVER_UTILIZATION (0.5), not lambda/(c*mu)=0.9
    assert math.isclose(float(obs["rho"]), 0.5, rel_tol=1e-12)


def test_mmc_compat_edges_must_be_linkedge() -> None:
    """If the first edge is not a LinkEdge, flag incompatibility."""
    gen = ArrivalsGenerator(
        id="gen", lambda_rps=10.0, model=Distribution.POISSON,
    )
    client = Client(id="client-1")
    ep = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[{
            "kind": "initial_parsing",
            "step_operation": {
                "cpu_time": {"mean": 0.01, "distribution": "exponential"},
            },
        }],
    )
    s1 = Server(
        id="s1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[ep],
    )

    # First edge is NetworkEdge (not LinkEdge). Provide the required field
    # name "latency" (seconds), not "latency_ms".
    edges = [
        NetworkEdge(
            id="net-1", source="gen", target="client-1", latency=0.001,
        ),
    ]
    graph = TopologyGraph(
        nodes=TopologyNodes(servers=[s1], client=client, load_balancer=None),
        edges=edges,
    )
    payload = SimulationPayload(
        arrivals=gen,
        topology_graph=graph,
        sim_settings=SimulationSettings(total_simulation_time=5),
    )

    mmc = MMc()
    assert not mmc.is_compatible(payload)
    assert any(
        "use link_edge as a type" in r
        for r in mmc.explain_incompatibilities(payload)
    )


def test_mmc_compare_and_format_smoke_random_and_fcfs() -> None:
    mmc = MMc()
    # RANDOM
    p_split = _build_payload_mmc_split(
        lambda_rps=50.0, cpu_mean_s=0.02, c=2,
    )
    fake_r = _FakeResultsAnalyzer(
        lambda_rps=50.0,
        mu_rate=50.0,
        w_mean=0.08,
        wq_mean=0.05,
        server_ids=["srv-1", "srv-2"],
    )
    out_r = mmc.compare_and_format(
        p_split, cast("ResultsAnalyzer", fake_r),
    )
    assert "MMc (Random split)" in out_r
    assert "sym" in out_r
    assert "λ" in out_r

    # FCFS
    p_fcfs = _build_payload_mmc_fcfs(
        lambda_rps=270.0, cpu_mean_s=0.01, c=3,
    )
    fake_f = _FakeResultsAnalyzerFCFS(
        arrivals_id="rqs-1",
        lb_id="lb-1",
        server_ids=["srv-1", "srv-2", "srv-3"],
        lambda_rps=270.0,
        mu_rate=100.0,
        w_mean=0.036,
        lb_waits=[0.02, 0.03],
        l_system_series=[10.0, 10.0, 11.0],
        lq_lb_series=[7.1, 7.3],
        server_util_series={
            "srv-1": [1, 0],
            "srv-2": [0, 1],
            "srv-3": [1, 0],
        },
    )
    out_f = mmc.compare_and_format(
        p_fcfs, cast("ResultsAnalyzer", fake_f),
    )
    # Table prints the ASCII symbol "rho".
    assert "MMc (FCFS/Erlang-C)" in out_f
    assert "rho" in out_f
    assert "Wq" in out_f
