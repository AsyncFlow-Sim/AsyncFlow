#!/usr/bin/env python3
"""
Esempio “single server” con stampa di tutte le stats e salvataggio grafici.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import simpy

from app.config.constants import (
    Distribution,
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    StepOperation,
    SystemEdges,
)
from app.metrics.analyzer import ResultsAnalyzer
from app.runtime.simulation_runner import SimulationRunner
from app.schemas.full_simulation_input import SimulationPayload
from app.schemas.random_variables_config import RVConfig
from app.schemas.rqs_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology.endpoint import Endpoint, Step
from app.schemas.system_topology.full_system_topology import (
    Client,
    Edge,
    Server,
    TopologyGraph,
    TopologyNodes,
)


def main() -> None:
    # ───── 1. SETTINGS ─────
    settings = SimulationSettings(
        total_simulation_time = 50,      # 5 s
        sample_period_s       = 0.002,  # campiono ogni 2 ms
    )

    # ───── 2. WORKLOAD ─────
    workload = RqsGeneratorInput(
        id   = "generator-1",
        avg_active_users = RVConfig(mean=5,  distribution=Distribution.POISSON),
        avg_request_per_minute_per_user = RVConfig(mean=60, distribution=Distribution.POISSON),
    )

    # ───── 3. TOPOLOGY ─────
    client = Client(id="client-1")

    server = Server(
        id="srv-1",
        server_resources = {"cpu_cores": 1, "ram_mb": 256},
        endpoints = [
            Endpoint(
                endpoint_name = "/hello",
                steps = [
                    Step(
                        kind = EndpointStepRAM.RAM,
                        step_operation = {StepOperation.NECESSARY_RAM: 4},
                    ),
                    Step(
                        kind = EndpointStepCPU.CPU_BOUND_OPERATION,
                        step_operation = {StepOperation.CPU_TIME: 0.005},
                    ),
                    Step(
                        kind = EndpointStepIO.WAIT,
                        step_operation = {StepOperation.IO_WAITING_TIME: 0.05},
                    ),
                ],
            ),
        ],
    )

    # generator → client
    edge_g2c = Edge(
        id       = "edge-g2c",
        source   = "generator-1",
        target   = "client-1",
        latency  = RVConfig(mean=1e-3, distribution=Distribution.NORMAL, variance=1e-6),
        edge_type = SystemEdges.NETWORK_CONNECTION,
    )
    # client → server
    edge_c2s = Edge(
        id       = "edge-c2s",
        source   = "client-1",
        target   = "srv-1",
        latency  = RVConfig(mean=2e-3, distribution=Distribution.NORMAL, variance=1e-6),
        edge_type = SystemEdges.NETWORK_CONNECTION,
    )
    # server → client
    edge_s2c = Edge(
        id       = "edge-s2c",
        source   = "srv-1",
        target   = "client-1",
        latency  = RVConfig(mean=2e-3, distribution=Distribution.NORMAL, variance=1e-6),
        edge_type = SystemEdges.NETWORK_CONNECTION,
    )

    nodes = TopologyNodes(
        servers = [server],
        client  = client,
    )
    graph = TopologyGraph(
        nodes  = nodes,
        edges  = [edge_g2c, edge_c2s, edge_s2c],
    )

    # ───── 4. PAYLOAD ─────
    payload = SimulationPayload(
        sim_settings   = settings,
        rqs_input      = workload,
        topology_graph = graph,
    )

    # ───── 5. RUN ─────
    env    = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    # ───── 6. STAMPE ─────
    stats = results.get_latency_stats()
    print("\n════════ LATENCY STATS ════════")
    for k,v in stats.items():
        print(f"{k.name:<20} = {v:.6f}")

    ts, rps = results.get_throughput_series()
    print("\n════════ THROUGHOUT (req/sec) ════════")
    for t,rate in zip(ts, rps, strict=False):
        print(f"t={t:4.1f}s → {rate:5.2f} rps")

    sampled = results.get_sampled_metrics()
    print("\n════════ SAMPLED METRICS ════════")
    for metric, series in sampled.items():
        print(f"\n📈 {metric}:")
        for entity, vals in series.items():
            print(f"  - {entity}: len={len(vals)}, first={vals[:5]}")

    # ───── 7. GRAFICI ─────
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    results.plot_latency_distribution(axes[0, 0])
    results.plot_throughput         (axes[0, 1])
    results.plot_server_queues     (axes[1, 0])
    results.plot_ram_usage          (axes[1, 1])
    fig.tight_layout()

    out_path = Path(__file__).parent / "output_plots.png"
    fig.savefig(out_path)
    print(f"\n🖼️  Grafici salvati in: {out_path}")

if __name__ == "__main__":
    main()
