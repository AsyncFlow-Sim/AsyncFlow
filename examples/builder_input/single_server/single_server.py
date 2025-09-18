"""
AsyncFlow builder example — build, run, and visualize a single-server async system.

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

Outputs
    - Prints latency statistics to stdout
    - Saves a 2×2 PNG in the same directory as this script:
        [0,0] Latency histogram (with mean/P50/P95/P99)
        [0,1] Throughput (with mean/P95/max overlays)
        [1,0] Ready queue for the first server
        [1,1] RAM usage for the first server
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
        endpoint_name="/api",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},  # 1 ms
            {"kind": "ram", "step_operation": {"necessary_ram": 100}},           # 100 MB
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.100}},   # 100 ms
        ],
    )
    server = Server(
        id="app-1",
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
    e_client_app = Edge(
        id="client-app",
        source="client-1",
        target="app-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_app_client = Edge(
        id="app-client",
        source="app-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )

    # Simulation settings
    settings = SimulationSettings(
        total_simulation_time=300,
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    # Assemble payload with the builder
    payload = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(server)
        .add_edges(e_gen_client, e_client_app, e_app_client)
        .add_simulation_settings(settings)
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

    # Prepare figure in the same folder as this script
    script_dir = Path(__file__).parent
    out_path = script_dir / "builder_service_plots.png"

    # 2×2: Latency | Throughput | Ready (first server) | RAM (first server)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=160)

    # Top row
    res.plot_latency_distribution(axes[0, 0])
    res.plot_throughput(axes[0, 1])

    # Bottom row — first server, if present
    sids = res.list_server_ids()
    if sids:
        sid = sids[0]
        res.plot_single_server_ready_queue(axes[1, 0], sid)
        res.plot_single_server_ram(axes[1, 1], sid)
    else:
        for ax in (axes[1, 0], axes[1, 1]):
            ax.text(0.5, 0.5, "No servers", ha="center", va="center")
            ax.axis("off")

    fig.tight_layout()
    fig.savefig(out_path)
    print(f"Plots saved to: {out_path}")


if __name__ == "__main__":
    main()
