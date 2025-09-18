"""System test: single server (seeded, reproducible).

Topology:
    generator → client → srv-1 → client

Endpoint:
    CPU(1 ms) → RAM(64 MB) → IO(10 ms)
Edges: exponential latency ~2-3 ms.

Checks:
- latency stats present and plausible (broad bounds);
- throughput roughly consistent with nominal λ;
- basic sampled metrics present for srv-1.
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import numpy as np
import pytest
import simpy

from asyncflow import AsyncFlow
from asyncflow.components import Client, Edge, Endpoint, Server
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

SEED = 1337
REL_TOL = 0.35  # generous bound for simple sanity


def _seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)  # noqa: NPY002
    os.environ["PYTHONHASHSEED"] = str(seed)


def _build_payload() -> SimulationPayload:
    # Workload: ~26.7 rps (80 users * 20 rpm / 60)
    gen = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 80},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )
    client = Client(id="client-1")

    ep = Endpoint(
        endpoint_name="/api",
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "ram", "step_operation": {"necessary_ram": 64}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
        ],
    )
    srv = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[ep],
    )

    edges = [
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="client-srv",
            source="client-1",
            target="srv-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="srv-client",
            source="srv-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
    ]

    settings = SimulationSettings(
        total_simulation_time=400,
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
        .add_servers(srv)
        .add_edges(*edges)
    )
    flow = flow.add_simulation_settings(settings)
    return flow.build_payload()


def test_system_single_server_sane() -> None:
    """End-to-end single-server scenario: sanity checks with seeded RNGs."""
    _seed_all()

    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=_build_payload())
    res: ResultsAnalyzer = runner.run()

    # Latency stats present and plausible
    stats = res.get_latency_stats()
    assert stats, "Expected non-empty stats."
    assert LatencyKey.TOTAL_REQUESTS in stats
    mean_lat = float(stats.get(LatencyKey.MEAN, 0.0))
    assert 0.015 <= mean_lat <= 0.060

    # Throughput sanity vs nominal λ
    _, rps = res.get_throughput_series()
    assert rps, "No throughput series produced."
    rps_mean = float(np.mean(rps))
    lam = 80 * 20 / 60.0
    assert abs(rps_mean - lam) / lam <= REL_TOL

    # Sampled metrics present for srv-1
    sampled: dict[str, dict[str, list[float]]] = res.get_sampled_metrics()
    for key in ("ready_queue_len", "event_loop_io_sleep", "ram_in_use"):
        assert key in sampled
        assert "srv-1" in sampled[key]
        assert len(sampled[key]["srv-1"]) > 0
