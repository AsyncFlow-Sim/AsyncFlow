"""
Didactic example: AsyncFlow with a Load Balancer and two **identical** servers.

Goal
----
Show a realistic, symmetric backend behind a load balancer, and export plots
that match the public `ResultsAnalyzer` API (no YAML needed).

Topology
--------
    generator ──edge──> client ──edge──> LB ──edge──> srv-1
                                         └──edge──> srv-2
    srv-1 ──edge──> client
    srv-2 ──edge──> client

Load model
----------
~120 active users, 20 requests/min each (Poisson-like aggregate by default).

Server model (both srv-1 and srv-2)
-----------------------------------
• 1 CPU cores, 2 GB RAM
• Endpoint pipeline: CPU(2 ms) → RAM(128 MB) → I/O wait (15 ms)
  - CPU step blocks the event loop
  - RAM step holds a working set until the request completes
  - I/O step is non-blocking (event-loop friendly)

Network model
-------------
Every edge uses an exponential latency with mean 3 ms.

Outputs
-------
• Prints latency statistics to stdout
• Saves, in the same folder as this script:
  - `lb_dashboard.png`  (Latency histogram + Throughput)
  - `lb_server_<id>_metrics.png` for each server (Ready / I/O / RAM)
"""

from __future__ import annotations

from pathlib import Path

import simpy
import matplotlib.pyplot as plt

# Public AsyncFlow API (builder-style)
from asyncflow import AsyncFlow
from asyncflow.components import Client, Server, Edge, Endpoint, LoadBalancer
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator

# Runner + Analyzer
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer


def main() -> None:
    # ── 1) Build the scenario programmatically (no YAML) ────────────────────
    # Workload (traffic generator)
    generator = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 120},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )

    # Client
    client = Client(id="client-1")

    # Two identical servers: CPU(2ms) → RAM(128MB) → IO(15ms)
    endpoint = Endpoint(
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
            {"kind": "ram", "step_operation": {"necessary_ram": 128}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.015}},
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

    # Load balancer (round-robin)
    lb = LoadBalancer(
        id="lb-1",
        algorithms="round_robin",
        server_covered={"srv-1", "srv-2"},
    )

    # Network edges (3 ms mean, exponential)
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
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
            latency={"mean": 0.003, "distribution": "exponential"},
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

    # Simulation settings
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

    # Assemble the payload with the builder
    payload = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(srv1, srv2)
        .add_load_balancer(lb)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    ).build_payload()

    # ── 2) Run the simulation ───────────────────────────────────────────────
    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    # ── 3) Print a concise latency summary ──────────────────────────────────
    print(results.format_latency_stats())

    # ── 4) Save plots (same directory as this script) ───────────────────────
    out_dir = Path(__file__).parent

    # 4a) Dashboard: latency + throughput (single figure)
    fig_dash, axes = plt.subplots(
        1, 2, figsize=(14, 5), dpi=160, constrained_layout=True
    )
    results.plot_latency_distribution(axes[0])
    results.plot_throughput(axes[1])
    dash_path = out_dir / "lb_dashboard.png"
    fig_dash.savefig(dash_path, bbox_inches="tight")
    print(f"🖼️  Dashboard saved to: {dash_path}")

    # 4b) Per-server figures: Ready | I/O | RAM (one row per server)
    for sid in results.list_server_ids():
        fig_srv, axs = plt.subplots(
            1, 3, figsize=(18, 4.2), dpi=160, constrained_layout=True
        )
        results.plot_single_server_ready_queue(axs[0], sid)
        results.plot_single_server_io_queue(axs[1], sid)
        results.plot_single_server_ram(axs[2], sid)
        fig_srv.suptitle(f"Server metrics — {sid}", fontsize=16)
        srv_path = out_dir / f"lb_server_{sid}_metrics.png"
        fig_srv.savefig(srv_path, bbox_inches="tight")
        print(f"🖼️  Per-server plots saved to: {srv_path}")


if __name__ == "__main__":
    main()
