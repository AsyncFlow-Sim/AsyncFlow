# ResultsAnalyzer — Public API Documentation

Analyze and visualize the outcome of an AsyncFlow simulation.
`ResultsAnalyzer` consumes raw runtime objects (client, servers, edges, settings),
computes latency and throughput aggregates, exposes sampled series, and offers
compact plotting helpers built on Matplotlib.

---

## Quick start

```python
import simpy
from matplotlib import pyplot as plt
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer, SampledMetricName

# 1) Run a simulation and get an analyzer
env = simpy.Environment()
runner = SimulationRunner.from_yaml(env=env, yaml_path="data/single_server.yml")
res: ResultsAnalyzer = runner.run()

# 2) Text summary
print(res.format_latency_stats())

# 3) Plot the dashboard (latency histogram + throughput)
fig, (ax_lat, ax_rps) = plt.subplots(1, 2, figsize=(12, 4), dpi=160)
res.plot_base_dashboard(ax_lat, ax_rps)
fig.tight_layout()
fig.savefig("dashboard.png")

# 4) Single-server plots
server_id = res.list_server_ids()[0]
fig_rdy, ax_rdy = plt.subplots(figsize=(8, 4), dpi=160)
res.plot_single_server_ready_queue(ax_rdy, server_id)
fig_rdy.tight_layout()
fig_rdy.savefig(f"ready_{server_id}.png")
```

---

## Data model & units

* **Latency**: seconds (s).
* **Throughput**: requests per second (RPS).
* **Sampled metrics** (per server/edge): series captured at a fixed sampling
  period `settings.sample_period_s` (e.g., queue length, RAM usage).
  Units depend on the metric (RAM is typically MB).

---

## Computed metrics

* **Latency statistics** (global):
  `TOTAL_REQUESTS, MEAN, MEDIAN, STD_DEV, P95, P99, MIN, MAX`.
* **Throughput time series**: per-window RPS (default cached at 1 s buckets).
* **Sampled metrics**: raw, per-entity series keyed by
  `SampledMetricName` (or its string value).

---

## Class reference

### Constructor

```python
ResultsAnalyzer(
    *,
    client: ClientRuntime,
    servers: list[ServerRuntime],
    edges: list[EdgeRuntime],
    settings: SimulationSettings,
)
```

The analyzer is **lazy**: metrics are computed on first access.

### Core methods

* `process_all_metrics() -> None`
  Forces computation of latency stats, throughput cache (1 s), and sampled metrics.

* `get_latency_stats() -> dict[LatencyKey, float]`
  Returns the global latency stats. Computes them if needed.

* `format_latency_stats() -> str`
  Returns a ready-to-print block with latency statistics.

* `get_throughput_series(window_s: float | None = None) -> tuple[list[float], list[float]]`
  Returns `(timestamps, rps)`. If `window_s` is `None` or `1.0`, the cached
  1-second series is returned; otherwise a fresh series is computed.

* `get_sampled_metrics() -> dict[str, dict[str, list[float]]]`
  Returns sampled metrics as `{metric_key: {entity_id: [values...]}}`.

* `get_metric_map(key: SampledMetricName | str) -> dict[str, list[float]]`
  Gets the per-entity series map for a metric. Accepts either the enum value or
  the raw string key.

* `get_series(key: SampledMetricName | str, entity_id: str) -> tuple[list[float], list[float]]`
  Returns time/value series for a given metric and entity.
  Time coordinates are `i * settings.sample_period_s`.

* `list_server_ids() -> list[str]`
  Returns server IDs in a stable, topology order.

---

## Plotting helpers

All plotting methods draw on a **Matplotlib `Axes`** provided by the caller and
do **not** manage figure lifecycles.

> When there is no data for the requested plot, the axis is annotated with the
> corresponding `no_data` message from `plot_constants`.

### Dashboard

* `plot_base_dashboard(ax_latency: Axes, ax_throughput: Axes) -> None`
  Convenience: calls the two methods below.

* `plot_latency_distribution(ax: Axes) -> None`
  Latency histogram with **vertical overlays** (mean, P50, P95, P99) and a
  **single legend box** (top-right) that shows each statistic with its matching
  colored handle.

* `plot_throughput(ax: Axes, *, window_s: float | None = None) -> None`
  Throughput line with **horizontal overlays** (mean, P95, max) and a
  **single legend box** (top-right) that shows values and colors for each line.

### Single-server plots

Each single-server plot:

* draws the main series,

* overlays **mean / min / max** as horizontal lines (distinct styles/colors),

* shows a **single legend box** with values for mean/min/max,

* **does not** include a legend entry for the main series (title suffices).

* `plot_single_server_ready_queue(ax: Axes, server_id: str) -> None`
  Ready queue length over time (per server).

* `plot_single_server_io_queue(ax: Axes, server_id: str) -> None`
  I/O queue/sleep metric over time (per server).

* `plot_single_server_ram(ax: Axes, server_id: str) -> None`
  RAM usage over time (per server).

## Behavior & design notes

* **Laziness & caching**

  * Latency stats and the 1 s throughput series are cached on first use.
  * Calling `get_throughput_series(window_s=...)` with a custom window computes
    a fresh series (not cached).

* **Stability**

  * `list_server_ids()` follows the topology order for readability across runs.

* **Error handling**

  * Multi-server plotting methods validate the number of axes and raise
    `ValueError` with a descriptive message.

* **Matplotlib integration**

  * The analyzer **does not** close figures or call `plt.show()`.
  * Titles, axes labels, and “no data” messages are taken from
    `asyncflow.config.plot_constants`.

* **Thread-safety**

  * The analyzer is not designed for concurrent mutation. Use from a single
    thread after the simulation completes.

---

## Examples

### Custom throughput window

```python
fig, ax = plt.subplots(figsize=(8, 3), dpi=160)
res.plot_throughput(ax, window_s=2.0)  # 2-second buckets
fig.tight_layout()
fig.savefig("throughput_2s.png")
```

### Access a sampled metric series

```python
from asyncflow.metrics.analyzer import SampledMetricName

server_id = res.list_server_ids()[0]
t, qlen = res.get_series(SampledMetricName.READY_QUEUE_LEN, server_id)
# t: [0.0, 0.1, 0.2, ...] (scaled by sample_period_s)
# qlen: [.. values ..]
```

---

If you need additional KPIs (e.g., tail latency over time, backlog, or
utilization), the current structure makes it straightforward to add new helpers
alongside the existing plotting methods.
