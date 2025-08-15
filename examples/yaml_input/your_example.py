from pathlib import Path

import simpy
import matplotlib.pyplot as plt

from asyncflow.config.constants import LatencyKey
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer

def print_latency_stats(res: ResultsAnalyzer) -> None:
    """Print latency statistics returned by the analyzer."""
    stats = res.get_latency_stats()
    print("\n=== LATENCY STATS ===")
    if not stats:
        print("(empty)")
        return

    order: list[LatencyKey] = [
        LatencyKey.TOTAL_REQUESTS,
        LatencyKey.MEAN,
        LatencyKey.MEDIAN,
        LatencyKey.STD_DEV,
        LatencyKey.P95,
        LatencyKey.P99,
        LatencyKey.MIN,
        LatencyKey.MAX,
    ]
    for key in order:
        if key in stats:
            print(f"{key.name:<20} = {stats[key]:.6f}")

def save_all_plots(res: ResultsAnalyzer, out_path: Path) -> None:
    """Generate the 2x2 plot figure and save it to `out_path`."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    res.plot_latency_distribution(axes[0, 0])
    res.plot_throughput(axes[0, 1])
    res.plot_server_queues(axes[1, 0])
    res.plot_ram_usage(axes[1, 1])
    fig.tight_layout()
    fig.savefig(out_path)
    print(f"Plots saved to: {out_path}")

# Paths
yaml_path = Path(__file__).parent / "data" / "<your_file_name>.yml"
out_path = Path(__file__).parent / "<your_file_name>_plots.png"

# Simulation
env = simpy.Environment()
runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
results: ResultsAnalyzer = runner.run()

# Output
print_latency_stats(results)
save_all_plots(results, out_path)
