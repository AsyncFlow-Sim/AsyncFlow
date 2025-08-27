#!/usr/bin/env python3
"""
AsyncFlow builder example — build, run, and visualize a single-server async system
with event injections (latency spike on edge + server outage).

Topology (single server)
    generator ──edge──> client ──edge──> server ──edge──> client

Load model
    ~100 active users, 20 requests/min each (Poisson-like aggregate).

Server model
    1 CPU core, 2 GB RAM
    Endpoint pipeline: CPU(1 ms) → RAM(100 MB) → I/O wait (100 ms)
    Semantics:
      - CPU step blocks the event loop
      - RAM step holds a working set until request completion
      - I/O step is non-blocking (event-loop friendly)

Network model
    Each edge has exponential latency with mean 3 ms.

Events
    - ev-spike-1: deterministic latency spike (+20 ms) on client→server edge,
      active from t=120s to t=240s
    - ev-outage-1: server outage for srv-1 from t=300s to t=360s

Outputs
    - Prints latency statistics to stdout
    - Saves PNGs in `single_server_plot/` next to this script:
        * dashboard (latency + throughput)
        * per-server plots (ready queue, I/O queue, RAM)
"""

from __future__ import annotations

from pathlib import Path
import simpy
import matplotlib.pyplot as plt

# Public AsyncFlow API (builder)
from asyncflow import AsyncFlow
from asyncflow.components import Client, Server, Edge, Endpoint
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator

# Runner + Analyzer
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer


def build_and_run() -> ResultsAnalyzer:
    """Build the scenario via the Pythonic builder and run the simulation."""
    # Workload (generator)
    generator = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 100},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )

    # Client
    client = Client(id="client-1")

    # Server + endpoint (CPU → RAM → I/O)
    endpoint = Endpoint(
        endpoint_name="ep-1",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},  # 1 ms
            {"kind": "ram", "step_operation": {"necessary_ram": 100}},           # 100 MB
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.100}},   # 100 ms
        ],
    )
    server = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint],
    )

    # Network edges (3 ms mean, exponential)
    e_gen_client = Edge(
        id="gen-client",
        source="rqs-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_client_srv = Edge(
        id="client-srv",
        source="client-1",
        target="srv-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_srv_client = Edge(
        id="srv-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )

    # Simulation settings
    settings = SimulationSettings(
        total_simulation_time=500,
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    # Assemble payload with events
    payload = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(server)
        .add_edges(e_gen_client, e_client_srv, e_srv_client)
        .add_simulation_settings(settings)
        # Events
        .add_network_spike(
            event_id="ev-spike-1",
            edge_id="client-srv",
            t_start=120.0,
            t_end=240.0,
            spike_s=0.020,  # 20 ms spike
        )
    ).build_payload()

    # Run
    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()
    return results


def main() -> None:
    # Build & run
    res = build_and_run()

    # Print concise latency summary
    print(res.format_latency_stats())

    # Prepare output dir
    script_dir = Path(__file__).parent
    out_dir = script_dir / "single_server_plot"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dashboard (latency + throughput)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    res.plot_base_dashboard(axes[0], axes[1])
    fig.tight_layout()
    dash_path = out_dir / "event_inj_single_server_dashboard.png"
    fig.savefig(dash_path)
    print(f"Saved: {dash_path}")

    # Per-server plots
    for sid in res.list_server_ids():
        # Ready queue
        f1, a1 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_ready_queue(a1, sid)
        f1.tight_layout()
        p1 = out_dir / f"event_inj_single_server_ready_queue_{sid}.png"
        f1.savefig(p1)
        print(f"Saved: {p1}")

        # I/O queue
        f2, a2 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_io_queue(a2, sid)
        f2.tight_layout()
        p2 = out_dir / f"event_inj_single_server_io_queue_{sid}.png"
        f2.savefig(p2)
        print(f"Saved: {p2}")

        # RAM usage
        f3, a3 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_ram(a3, sid)
        f3.tight_layout()
        p3 = out_dir / f"event_inj_single_server_ram_{sid}.png"
        f3.savefig(p3)
        print(f"Saved: {p3}")


if __name__ == "__main__":
    main()
