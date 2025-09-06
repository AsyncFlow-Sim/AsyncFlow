"""
AsyncFlow builder example — build, run, and visualize a single-server async system.

Topology (single server)
    generator ──edge──> client ──edge──> server ──edge──> client

Load model
    ~100 active users, 20 requests/min each (Poisson-like aggregate).

Server model
    1 CPU core, 2 GB RAM
    Endpoint pipeline:
        CPU(exp; mean ~3 ms) → RAM(100 MB) → I/O wait (exp; mean ~20 ms)
    Semantics:
      - CPU step blocks the event loop (service time for M/M/1)
      - RAM step holds a working set until request completion
      - I/O step is non-blocking (event-loop friendly)

Network model
    Each edge has deterministic latency of 1 ms to keep M/M/1-style behavior
    (exponential service from CPU, Poisson arrivals from the generator).

Outputs
    - Prints latency statistics to stdout
    - Saves three PNGs in the same directory as this script:
        1) system_dashboard.png
           [0,0] Latency histogram (with mean/P50/P95/P99)
           [0,1] Throughput (with mean/P95/max overlays)
        2) server_timeseries_dashboard.png  (for the first server)
           [0,0] Ready queue (series + mean/min/max)
           [0,1] I/O queue (series + mean/min/max)
           [1,0] RAM usage (series + mean/min/max)
        3) server_event_metrics_dashboard.png (for the first server)
           [0,0] Server-side latency histogram (mean/P50/P95/P99)
           [0,1] CPU service time histogram (mean/P95/P99)
           [1,0] I/O time histogram (mean/P95/P99)
           [1,1] CPU waiting time histogram (mean/P95/P99)
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

    # Server + endpoint:
    # CPU = exponential (~3 ms), RAM = 100 MB, IO = exponential (~20 ms)
    # Note: using RVConfig-like dicts for step durations.
    endpoint = Endpoint(
    endpoint_name="/api",
    probability=1.0,
    steps=[
       
        # New CPU step after I/O: mean >= 40ms
        {
            "kind": "initial_parsing",  # CPU-bound step (same kind mapping as sopra)
            "step_operation": {
                "cpu_time": {"mean": 0.015, "distribution": "exponential"},
            },
        },
    ],
)

    server = Server(
        id="app-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint],
    )

    # Network edges: deterministic ~1 ms to approximate M/M/1 behavior
    e_gen_client = Edge(id="gen-client", source="rqs-1", target="client-1", latency=0.001)
    e_client_app = Edge(id="client-app", source="client-1", target="app-1", latency=0.001)
    e_app_client = Edge(id="app-client", source="app-1", target="client-1", latency=0.001)
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

    # Prepare output paths in the same folder as this script
    script_dir = Path(__file__).parent
    p_system = script_dir / "system_dashboard.png"
    p_srv_ts = script_dir / "server_timeseries_dashboard.png"
    p_srv_ev = script_dir / "server_event_metrics_dashboard.png"

    # 1) System dashboard: latency + throughput
    fig_sys, axes_sys = plt.subplots(1, 2, figsize=(12, 4.5), dpi=160)
    res.plot_latency_distribution(axes_sys[0])
    res.plot_throughput(axes_sys[1])
    fig_sys.tight_layout()
    fig_sys.savefig(p_system)

    # If there is at least one server, render the per-server dashboards
    sids = res.list_server_ids()
    if sids:
        sid = sids[0]

        # 2) Server time-series dashboard: Ready | I/O | RAM
        fig_ts, axes_ts = plt.subplots(2, 2, figsize=(12, 8), dpi=160)
        # We only need three panes; hide the unused bottom-right
        axes_ts[1, 1].axis("off")
        res.plot_server_timeseries_dashboard(
            ax_ready=axes_ts[0, 0],
            ax_io=axes_ts[0, 1],
            ax_ram=axes_ts[1, 0],
            server_id=sid,
        )
        fig_ts.tight_layout()
        fig_ts.savefig(p_srv_ts)

        # 3) Server event metrics dashboard: latency | service | I/O | waiting
        fig_ev, axes_ev = plt.subplots(2, 2, figsize=(12, 8), dpi=160)
        res.plot_server_event_metrics_dashboard(
            ax_latency_hist=axes_ev[0, 0],
            ax_service_hist=axes_ev[0, 1],
            ax_io_hist=axes_ev[1, 0],
            ax_wait_hist=axes_ev[1, 1],
            server_id=sid,
        )
        fig_ev.tight_layout()
        fig_ev.savefig(p_srv_ev)
    else:
        print("No servers available in the topology. Skipping server dashboards.")

    print(f"Saved:")
    print(f"  - {p_system}")
    if sids:
        print(f"  - {p_srv_ts}")
        print(f"  - {p_srv_ev}")


if __name__ == "__main__":
    main()
