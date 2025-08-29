"""
AsyncFlow builder example — LB + 2 servers (medium load) with events.

Topology
  generator → client → LB → srv-1
                         └→ srv-2
  srv-1 → client
  srv-2 → client

Workload
  ~40 rps (120 users × 20 req/min ÷ 60).

Events
  - Edge spike on client→LB (+15 ms) @ [100s, 160s]
  - srv-1 outage @ [180s, 240s]
  - Edge spike on LB→srv-2 (+20 ms) @ [300s, 360s]
  - srv-2 outage @ [360s, 420s]
  - Edge spike on gen→client (+10 ms) @ [480s, 540s]

Outputs
  PNGs saved under `lb_two_servers_events_plots/` next to this script:
    - dashboard (latency + throughput)
    - per-server plots: ready queue, I/O queue, RAM
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import simpy

# Public builder API
from asyncflow import AsyncFlow
from asyncflow.components import Client, Server, Edge, Endpoint, LoadBalancer
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator

# Runner + Analyzer
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner


def build_and_run() -> ResultsAnalyzer:
    """Build the scenario via the builder and run the simulation."""
    # ── Workload (generator) ───────────────────────────────────────────────
    generator = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 120},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )

    # ── Client ────────────────────────────────────────────────────────────
    client = Client(id="client-1")

    # ── Servers (identical endpoint: CPU 2ms → RAM 128MB → IO 12ms) ───────
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

    # ── Load Balancer ─────────────────────────────────────────────────────
    lb = LoadBalancer(
        id="lb-1",
        algorithms="round_robin",
        server_covered=["srv-1", "srv-2"],
    )

    # ── Edges (exponential latency) ───────────────────────────────────────
    e_gen_client = Edge(
        id="gen-client",
        source="rqs-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_client_lb = Edge(
        id="client-lb",
        source="client-1",
        target="lb-1",
        latency={"mean": 0.002, "distribution": "exponential"},
    )
    e_lb_srv1 = Edge(
        id="lb-srv1",
        source="lb-1",
        target="srv-1",
        latency={"mean": 0.002, "distribution": "exponential"},
    )
    e_lb_srv2 = Edge(
        id="lb-srv2",
        source="lb-1",
        target="srv-2",
        latency={"mean": 0.002, "distribution": "exponential"},
    )
    e_srv1_client = Edge(
        id="srv1-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_srv2_client = Edge(
        id="srv2-client",
        source="srv-2",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )

    # ── Simulation settings ───────────────────────────────────────────────
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

    # ── Assemble payload + events via builder ─────────────────────────────
    payload = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(srv1, srv2)
        .add_load_balancer(lb)
        .add_edges(
            e_gen_client,
            e_client_lb,
            e_lb_srv1,
            e_lb_srv2,
            e_srv1_client,
            e_srv2_client,
        )
        .add_simulation_settings(settings)
        # Events
        .add_network_spike(
            event_id="ev-spike-1",
            edge_id="client-lb",
            t_start=100.0,
            t_end=160.0,
            spike_s=0.015,  # +15 ms
        )
        .add_server_outage(
            event_id="ev-srv1-down",
            server_id="srv-1",
            t_start=180.0,
            t_end=240.0,
        )
        .add_network_spike(
            event_id="ev-spike-2",
            edge_id="lb-srv2",
            t_start=300.0,
            t_end=360.0,
            spike_s=0.020,  # +20 ms
        )
        .add_server_outage(
            event_id="ev-srv2-down",
            server_id="srv-2",
            t_start=360.0,
            t_end=420.0,
        )
        .add_network_spike(
            event_id="ev-spike-3",
            edge_id="gen-client",
            t_start=480.0,
            t_end=540.0,
            spike_s=0.010,  # +10 ms
        )
        .build_payload()
    )

    # ── Run ───────────────────────────────────────────────────────────────
    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()
    return results


def main() -> None:
    res = build_and_run()
    print(res.format_latency_stats())

    # Output directory next to this script
    script_dir = Path(__file__).parent
    out_dir = script_dir / "lb_two_servers_events_plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dashboard (latency + throughput)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    res.plot_base_dashboard(axes[0], axes[1])
    fig.tight_layout()
    dash_path = out_dir / "lb_two_servers_events_dashboard.png"
    fig.savefig(dash_path)
    print(f"Saved: {dash_path}")

    # Per-server plots
    for sid in res.list_server_ids():
        # Ready queue
        f1, a1 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_ready_queue(a1, sid)
        f1.tight_layout()
        p1 = out_dir / f"lb_two_servers_events_ready_queue_{sid}.png"
        f1.savefig(p1)
        print(f"Saved: {p1}")

        # I/O queue
        f2, a2 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_io_queue(a2, sid)
        f2.tight_layout()
        p2 = out_dir / f"lb_two_servers_events_io_queue_{sid}.png"
        f2.savefig(p2)
        print(f"Saved: {p2}")

        # RAM usage
        f3, a3 = plt.subplots(figsize=(10, 5))
        res.plot_single_server_ram(a3, sid)
        f3.tight_layout()
        p3 = out_dir / f"lb_two_servers_events_ram_{sid}.png"
        f3.savefig(p3)
        print(f"Saved: {p3}")


if __name__ == "__main__":
    main()
