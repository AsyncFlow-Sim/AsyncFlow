"""Basic golden test for the MMc analyzer (RR split model).

This file intentionally contains both helpers and the first test,
so you can copy-paste a single file and extend incrementally.

It uses only public facades (like a pip-installed user would),
plus `LatencyKey` which MMc reads from `get_latency_stats()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

# Public facades (end-user API)
from asyncflow import AsyncFlow
from asyncflow.analysis import MMc
from asyncflow.components import (
    ArrivalsGenerator,
    Client,
    Edge,
    Endpoint,
    LoadBalancer,
    Server,
)
from asyncflow.config.enums import LatencyKey  # used by get_latency_stats()
from asyncflow.enums import Distribution
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import NodesResources, TopologyNodes
from asyncflow.settings import SimulationSettings

if TYPE_CHECKING:
    # Types used only for static checking (mypy), not imported at runtime.
    from collections.abc import Iterable, Mapping

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer



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
        lambda_rate: float,
        mu_rate: float,
        w_mean: float,
        wq_mean: float,
        server_ids: Iterable[str],
    ) -> None:
        self._lambda_rate = float(lambda_rate)
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
        rps = [self._lambda_rate for _ in times]
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


def _build_payload_mmc_split(
    *,
    users_mean: int = 120,
    rpm_per_user: int = 20,
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
        lambda_rps=20,
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
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="client-lb",
            source="client-1",
            target="lb-1",
            latency=0.00001,
            dropout_rate=0,
        ),
    ]

    for s in servers:
        edges.append(
            Edge(
                id=f"lb-{s.id}",
                source="lb-1",
                target=s.id,
                latency=0.00001,
                dropout_rate=0,
            ),
        )
        edges.append(
            Edge(
                id=f"{s.id}-client",
                source=s.id,
                target="client-1",
                latency=0.00001,
                dropout_rate=0,
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


def _theory_kpis(payload: SimulationPayload) -> dict[str, float]:
    """Ask MMc once for its closed-form KPIs and return a numeric snapshot."""
    mmc = MMc()
    res = mmc.evaluate(payload)
    return {
        "lambda": float(res["lambda_rate"]),
        "mu": float(res["mu_rate"]),
        "W": float(res["W"]),
        "Wq": float(res["Wq"]),
    }


def test_mmc_compare_matches_theory() -> None:
    """When Observed == Theory, compare_against_run deltas must be zero."""
    payload = _build_payload_mmc_split(c=2)

    # Build a stub RA that feeds back the theoretical values.
    k = _theory_kpis(payload)
    server_ids = [f"srv-{i+1}" for i in range(2)]
    ra = _FakeResultsAnalyzer(
        lambda_rate=k["lambda"],
        mu_rate=k["mu"],
        w_mean=k["W"],
        wq_mean=k["Wq"],
        server_ids=server_ids,
    )

    mmc = MMc()
    assert mmc.is_compatible(payload), "Payload should be MMc-compatible."

    rows = mmc.compare_against_run(payload, cast("ResultsAnalyzer", ra))
    assert len(rows) == 8, "Expected 8 KPI rows."

    # All absolute deltas should be 0.000000 (printed as strings).
    zero = pytest.approx(0.0, abs=1e-9)
    for r in rows:
        msg = f"Non-zero delta for {r['symbol']} ({r['name']})"
        assert float(r["abs_diff"]) == zero, msg

# ---------------------------------------------------------------------------
# Extra tests for MMc
# ---------------------------------------------------------------------------

def test_mmc_instability_returns_infinities() -> None:
    """If rho >= 1, closed-form KPIs must be +inf (W, Wq, L, Lq)."""
    # c=2, mu=100 rps (service=0.01 s) -> capacity = 200 rps.
    # For instability set lambda >= 200.

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
        id="srv-1", server_resources=NodesResources(cpu_cores=2), endpoints=[endpoint],
    )
    nodes = TopologyNodes(servers=[srv], client=client, load_balancer=None)
    graph = TopologyGraph(nodes=nodes, edges=[])

    # λ = 200 rps (== capacity) -> rho = 1
    arrivals = ArrivalsGenerator(id="gen", lambda_rps=200.0, model=Distribution.POISSON)

    settings = SimulationSettings(total_simulation_time=5)
    payload = SimulationPayload(
        arrivals=arrivals, topology_graph=graph, sim_settings=settings)

    mmc = MMc()
    res = mmc.evaluate(payload)

    assert res["rho"] >= 1.0
    for key in ("W", "Wq", "L", "Lq"):
        assert res[key] == float("inf")



def test_mmc_incompatible_edge_latency_too_large() -> None:
    """Latency must be deterministic and <= 1 ms."""
    gen = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=20,
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
                    "cpu_time": {"mean": 0.01, "distribution": "exponential"},
                },
            },
        ],
    )
    srv1 = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint],
    )
    srv2 = Server(
        id="srv-2",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint],
    )
    lb = LoadBalancer(
        id="lb-1",
        algorithms="random",
        server_covered={"srv-1", "srv-2"},
    )
    edges = [
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency=0.005,  # 5 ms -> too large
            dropout_rate=0,
        ),
        Edge(
            id="client-lb",
            source="client-1",
            target="lb-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="srv1-client",
            source="srv-1",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="srv2-client",
            source="srv-2",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
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
    assert any("<= 1 ms" in r for r in reasons)


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
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="client-lb",
            source="client-1",
            target="lb-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="srv1-client",
            source="srv-1",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
        ),
        Edge(
            id="srv2-client",
            source="srv-2",
            target="client-1",
            latency=0.00001,
            dropout_rate=0,
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


def test_mmc_compare_and_format_smoke() -> None:
    """compare_and_format() should return a readable ASCII table."""
    payload = _build_payload_mmc_split(c=2)
    k = _theory_kpis(payload)
    server_ids = [f"srv-{i+1}" for i in range(2)]
    ra = _FakeResultsAnalyzer(
        lambda_rate=k["lambda"],
        mu_rate=k["mu"],
        w_mean=k["W"],
        wq_mean=k["Wq"],
        server_ids=server_ids,
    )
    mmc = MMc()
    table = mmc.compare_and_format(payload, cast("ResultsAnalyzer", ra))
    assert "MMc (RR) — Theory vs Observed" in table
    assert "Arrival rate" in table
    assert "Mean waiting (s)" in table


