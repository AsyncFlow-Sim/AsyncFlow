"""System test: load balancer + two identical servers (seeded, reproducible).

Topology:

    generator → client → LB(round_robin) → srv-1
                                       └→ srv-2
    srv-1 → client
    srv-2 → client

Each server endpoint: CPU(2 ms) → RAM(128 MB) → IO(12 ms)
Edges: exponential latency ~2-3 ms.
We check:
- latency stats / throughput sanity vs nominal λ (~40 rps);
- balanced traffic across srv-1 / srv-2 via edge concurrency and RAM means.
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import numpy as np
import pytest
import simpy

from asyncflow import AsyncFlow
from asyncflow.components import Client, Edge, Endpoint, LoadBalancer, Server
from asyncflow.config.constants import LatencyKey
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator

if TYPE_CHECKING:
    # Imported only for type checking (ruff: TC001)
    from asyncflow.metrics.analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload

pytestmark = [
    pytest.mark.system,
    pytest.mark.skipif(
        os.getenv("ASYNCFLOW_RUN_SYSTEM_TESTS") != "1",
        reason="System tests disabled (set ASYNCFLOW_RUN_SYSTEM_TESTS=1 to run).",
    ),
]

SEED = 4242
REL_TOL = 0.30  # 30% for λ/latency
BAL_TOL = 0.25  # 25% imbalance tolerated between the two backends


def _seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)  # noqa: NPY002
    os.environ["PYTHONHASHSEED"] = str(seed)


def _build_payload() -> SimulationPayload:
    gen = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 120},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )
    client = Client(id="client-1")

    endpoint = Endpoint(
        endpoint_name="/api",
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
            {"kind": "ram", "step_operation": {"necessary_ram": 128}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.012}},
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
        algorithms="round_robin",
        server_covered={"srv-1", "srv-2"},
    )

    edges = [
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="client-lb",
            source="client-1",
            target="lb-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="srv1-client",
            source="srv-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="srv2-client",
            source="srv-2",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
    ]

    settings = SimulationSettings(
        total_simulation_time=600,
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    flow = (
        AsyncFlow()
        .add_generator(gen)
        .add_client(client)
        .add_load_balancer(lb)
        .add_servers(srv1, srv2)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    )
    return flow.build_payload()


def _rel_diff(a: float, b: float) -> float:
    denom = max(1e-9, (abs(a) + abs(b)) / 2.0)
    return abs(a - b) / denom


def test_system_lb_two_servers_balanced_and_sane() -> None:
    """End-to-end LB scenario: sanity + balance checks with seeded RNGs."""
    _seed_all()

    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=_build_payload())
    res: ResultsAnalyzer = runner.run()

    # Latency sanity
    stats = res.get_latency_stats()
    assert stats, "Expected non-empty stats."
    assert LatencyKey.TOTAL_REQUESTS in stats
    mean_lat = float(stats.get(LatencyKey.MEAN, 0.0))
    assert 0.020 <= mean_lat <= 0.060

    # Throughput sanity vs nominal λ ≈ 40 rps
    _, rps = res.get_throughput_series()
    assert rps, "No throughput series produced."
    rps_mean = float(np.mean(rps))
    lam = 120 * 20 / 60.0
    assert abs(rps_mean - lam) / lam <= REL_TOL

    # Load balance check: edge concurrency lb→srv1 vs lb→srv2 close
    sampled = res.get_sampled_metrics()
    edge_cc: dict[str, list[float]] = sampled.get(
        "edge_concurrent_connection",
        {},
    )
    assert "lb-srv1" in edge_cc
    assert "lb-srv2" in edge_cc
    m1 = float(np.mean(edge_cc["lb-srv1"]))
    m2 = float(np.mean(edge_cc["lb-srv2"]))
    assert _rel_diff(m1, m2) <= BAL_TOL

    # Server metrics present and broadly similar (RAM means close-ish)
    ram_map: dict[str, list[float]] = sampled.get("ram_in_use", {})
    assert "srv-1" in ram_map
    assert "srv-2" in ram_map
    ram1 = float(np.mean(ram_map["srv-1"]))
    ram2 = float(np.mean(ram_map["srv-2"]))
    assert _rel_diff(ram1, ram2) <= BAL_TOL

    # IDs reported by analyzer
    sids = res.list_server_ids()
    assert set(sids) == {"srv-1", "srv-2"}
