"""System test: single-server scenario (deterministic-seeded, reproducible).

Runs a compact but realistic topology:

    generator → client → srv-1 → client

Endpoint on srv-1: CPU(1.5 ms) → RAM(96 MB) → IO(10 ms)
Edges: exponential latency ~3 ms each way.

Assertions (with sensible tolerances):
- non-empty latency stats; mean latency in a plausible band;
- mean throughput close to the nominal λ (±30%);
- sampled metrics exist for srv-1 and are non-empty.
"""

from __future__ import annotations

import os
import random
from typing import Dict, List

import numpy as np
import pytest
import simpy

from asyncflow import AsyncFlow
from asyncflow.components import Client, Edge, Endpoint, Server
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator
from asyncflow.config.constants import LatencyKey

# Mark as system and skip unless explicitly enabled in CI (or locally)
pytestmark = [
    pytest.mark.system,
    pytest.mark.skipif(
        os.getenv("ASYNCFLOW_RUN_SYSTEM_TESTS") != "1",
        reason="System tests disabled (set ASYNCFLOW_RUN_SYSTEM_TESTS=1 to run).",
    ),
]

SEED = 1337
REL_TOL = 0.30  # 30% tolerance for stochastic expectations


def _seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def _build_payload():
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
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.0015}},
            {"kind": "ram", "step_operation": {"necessary_ram": 96}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
        ],
    )
    srv = Server(id="srv-1", server_resources={"cpu_cores": 1, "ram_mb": 2048}, endpoints=[ep])

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
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="srv-client",
            source="srv-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
    ]

    settings = SimulationSettings(
        total_simulation_time=180,  # virtual time; keeps wall time fast
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    flow = AsyncFlow().add_generator(gen).add_client(client).add_servers(srv).add_edges(*edges)
    flow = flow.add_simulation_settings(settings)
    return flow.build_payload()


def test_system_single_server_end_to_end() -> None:
    """End-to-end single-server check with tolerances and seeded RNGs."""
    _seed_all()

    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=_build_payload())
    res: ResultsAnalyzer = runner.run()

    # Latency stats present and plausible
    stats = res.get_latency_stats()
    assert stats and LatencyKey.TOTAL_REQUESTS in stats
    mean_lat = float(stats.get(LatencyKey.MEAN, 0.0))
    assert 0.015 <= mean_lat <= 0.060

    # Throughput close to nominal lambda
    timestamps, rps = res.get_throughput_series()
    assert timestamps, "No throughput series produced."
    rps_mean = float(np.mean(rps))
    lam = 80 * 20 / 60.0
    assert abs(rps_mean - lam) / lam <= REL_TOL

    # Sampled metrics exist for srv-1
    sampled: Dict[str, Dict[str, List[float]]] = res.get_sampled_metrics()
    for key in ("ready_queue_len", "event_loop_io_sleep", "ram_in_use"):
        assert key in sampled and "srv-1" in sampled[key]
        assert len(sampled[key]["srv-1"]) > 0
