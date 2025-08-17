# AsyncFlow — Public API Reference: `ResultsAnalyzer`

`ResultsAnalyzer` is the public object you use **after** a run to compute
latency statistics, derive throughput time-series, and visualize sampled
metrics collected from servers and edges.

* **Input:** created and returned by `SimulationRunner.run()`
* **Output:** dictionaries and time-series you can print, log, chart, or export

> **Import (public):**
>
> ```python
> from asyncflow.analysis import ResultsAnalyzer
> ```


---

## TL;DR (minimal usage)

```python
results = SimulationRunner(env=env, simulation_input=payload).run()

# Aggregates
lat = results.get_latency_stats()          # dict of p50, p95, p99, ...
ts, rps = results.get_throughput_series()  # per-second timestamps & RPS
series = results.get_sampled_metrics()     # nested dict of time-series

# Plotting (matplotlib)
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
results.plot_latency_distribution(axes[0, 0])
results.plot_throughput(axes[0, 1])
results.plot_server_queues(axes[1, 0])
results.plot_ram_usage(axes[1, 1])
fig.tight_layout()
```

---

## What the analyzer computes

### Event-level aggregates (from `RQS_CLOCK`)

* **Latency stats** from per-request `(start_time, finish_time)` tuples:

  * keys: `total_requests, mean, median, std_dev, p95, p99, min, max`
* **Throughput (RPS)** as a time-series:

  * 1-second windows by default (see “Advanced: throughput window”)

### Sampled time-series (from runtime collectors)

* Per-entity (server/edge) series for the **baseline mandatory** metrics:

  * `ready_queue_len` (server)
  * `event_loop_io_sleep` (server)
  * `ram_in_use` (server)
  * `edge_concurrent_connection` (edge)

> These are sampled every `sample_period_s` defined in `SimulationSettings`.

---

## Public API

### Aggregates

```python
get_latency_stats() -> dict[LatencyKey, float]
```

Returns latency summary statistics. If no requests completed, returns `{}`.

```python
get_throughput_series() -> tuple[list[float], list[float]]
```

Returns `(timestamps_in_seconds, rps_values)`. If no traffic, returns `([], [])`.

### Sampled metrics

```python
get_sampled_metrics() -> dict[str, dict[str, list[float]]]
```

Returns a nested dictionary:

```python
{
  "<metric_name>": { "<entity_id>": [v0, v1, ...] }
}
```

* Metric names are strings matching the public enums (e.g. `"ready_queue_len"`).
* `entity_id` is a **server id** (for server metrics) or an **edge id** (for edge metrics).

### Plotting helpers

All plotting helpers draw on a provided `matplotlib.axes.Axes`:

```python
plot_latency_distribution(ax: Axes) -> None
plot_throughput(ax: Axes) -> None
plot_server_queues(ax: Axes) -> None
plot_ram_usage(ax: Axes) -> None
```

Behavior:

* If data is missing/empty, the plot shows a “no data” message.
* With a load balancer (multiple servers), per-server lines are labeled by server id automatically.

---

## Return contracts (shapes & keys)

### `get_latency_stats()`

Example:

```python
{
  'total_requests': 1200.0,
  'mean': 0.0123,
  'median': 0.0108,
  'std_dev': 0.0041,
  'p95': 0.0217,
  'p99': 0.0302,
  'min': 0.0048,
  'max': 0.0625
}
```

### `get_throughput_series()`

Example:

```python
timestamps = [1.0, 2.0, 3.0, ...]   # seconds from t=0
rps        = [  36,   41,   38, ...] # requests per second
```

### `get_sampled_metrics()`

Example subset:

```python
{
  "ready_queue_len": {
    "srv-1": [0, 1, 2, 1, ...],
    "srv-2": [0, 0, 1, 0, ...],
  },
  "event_loop_io_sleep": {
    "srv-1": [3, 5, 4, 6, ...],
  },
  "ram_in_use": {
    "srv-1": [128.0, 160.0, 192.0, ...],
  },
  "edge_concurrent_connection": {
    "lb-1->srv-1": [0, 1, 1, 2, ...],  # your edge ids
  }
}
```

Time base for these lists is implicit: index `i` corresponds to time `i * sample_period_s`.

---

## Plotting recipes

### Multi-panel overview

```python
import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
results.plot_latency_distribution(axes[0, 0])
results.plot_throughput(axes[0, 1])
results.plot_server_queues(axes[1, 0])
results.plot_ram_usage(axes[1, 1])

fig.suptitle("AsyncFlow – Simulation Overview", y=1.02)
fig.tight_layout()
```

## Edge cases & guarantees

* **No traffic:** all getters are safe:

  * `get_latency_stats()` → `{}`
  * `get_throughput_series()` → `([], [])`
  * Plots show “no data”.
* **Multiple servers / LB:** queue and RAM plots include **one line per server id**.
* **Metric availability:** the analyzer only exposes the **baseline mandatory** sampled metrics; if a metric wasn’t enabled/recorded, it won’t appear in the nested dict.
* **Units:** times are in **seconds**; RAM is in **MB**; RPS is **requests/second**.

---

## Performance characteristics

* Aggregations (percentiles, std) are **vectorized** via NumPy.
* Memory footprint of sampled series ≈
  `total_simulation_time / sample_period_s × (#metrics × #entities)`.
* Prefer a coarser `sample_period_s` for very long runs.

---




