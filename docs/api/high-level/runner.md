# AsyncFlow — Public API Reference: `SimulationRunner`

`SimulationRunner` is the **orchestrator** of a simulation run. It takes a fully
validated `SimulationPayload`, instantiates the runtime actors, wires their
connections, starts the processes inside a `simpy.Environment`, collects sampled
metrics, advances the virtual clock, and returns a `ResultsAnalyzer` for
post-run querying and plotting.

Use it together with the `AsyncFlow` builder (Python) or a YAML payload.

---

## Imports

```python
from asyncflow import SimulationRunner, AsyncFlow        # high-level API
from asyncflow.settings import SimulationSettings
from asyncflow.components import Client, Server, Endpoint, Edge, LoadBalancer
from asyncflow.workload import RqsGenerator, RVConfig
import simpy
```

---

## Quick start

```python
# 1) Build a validated payload (see the builder docs for details)
payload = (
    AsyncFlow()
    .add_generator(RqsGenerator(
        id="rqs-1",
        avg_active_users=RVConfig(mean=50),
        avg_request_per_minute_per_user=RVConfig(mean=30),
    ))
    .add_client(Client(id="client-1"))
    .add_servers(
        Server(
            id="srv-1",
            server_resources={"cpu_cores": 1, "ram_mb": 1024},
            endpoints=[Endpoint(endpoint_name="/hello", steps=[
                {"kind": "ram", "step_operation": {"necessary_ram": 32}},
                {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
                {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
            ])],
        )
    )
    .add_edges(
        Edge(id="gen-client",  source="rqs-1",   target="client-1",
             latency={"mean": 0.003, "distribution": "exponential"}),
        Edge(id="client-srv1", source="client-1", target="srv-1",
             latency={"mean": 0.003, "distribution": "exponential"}),
        Edge(id="srv1-client", source="srv-1",    target="client-1",
             latency={"mean": 0.003, "distribution": "exponential"}),
    )
    .add_simulation_settings(SimulationSettings(total_simulation_time=300, sample_period_s=0.01))
    .build_payload()
)

# 2) Run
env = simpy.Environment()
results = SimulationRunner(env=env, simulation_input=payload).run()

# 3) Analyze
print(results.get_latency_stats())
ts, rps = results.get_throughput_series()
sampled = results.get_sampled_metrics()
```

---

## Class reference

```python
class SimulationRunner:
    def __init__(self, *, env: simpy.Environment, simulation_input: SimulationPayload) -> None: ...
    def run(self) -> ResultsAnalyzer: ...
    @classmethod
    def from_yaml(cls, *, env: simpy.Environment, yaml_path: str | Path) -> "SimulationRunner": ...
```

### Parameters

* **`env: simpy.Environment`**
  The SimPy environment that controls virtual time. You own its lifetime.

* **`simulation_input: SimulationPayload`**
  A fully validated payload (typically created with `AsyncFlow.build_payload()` or
  parsed from YAML). It contains workload, topology graph, and settings.

### Returns

* **`run() -> ResultsAnalyzer`**
  A results façade exposing:

  * `get_latency_stats() -> dict` (mean, median, p95, p99, …)
  * `get_throughput_series() -> (timestamps, rps)`
  * `get_sampled_metrics() -> dict[str, dict[str, list[float]]]`
  * plotting helpers: `plot_latency_distribution(ax)`, `plot_throughput(ax)`,
    `plot_server_queues(ax)`, `plot_ram_usage(ax)`

### Convenience: YAML entry point

```python
env = simpy.Environment()
runner = SimulationRunner.from_yaml(env=env, yaml_path="scenario.yml")
results = runner.run()
```

`from_yaml` uses `yaml.safe_load` and validates with the same Pydantic schemas,
so it enforces the exact same contract as the builder.

---

## Lifecycle & internal phases

`run()` performs the following steps:

1. **Build runtimes**

   * `RqsGeneratorRuntime` (workload)
   * `ClientRuntime`
   * `ServerRuntime` for each server (CPU/RAM resources bound)
   * `LoadBalancerRuntime` (optional)

2. **Wire edges**
   Creates an `EdgeRuntime` for each edge and assigns the appropriate *inbox*
   (`simpy.Store`) of the target actor. Sets the `out_edge` (or `out_edges` for
   the load balancer) on the source actor.

3. **Start processes**
   Registers every actor’s `.start()` coroutine in the environment and starts the
   **SampledMetricCollector** that snapshots:

   * server **ready queue length**, **I/O queue length**, **RAM in use**
   * edge **concurrent connections**
     at the configured `sample_period_s`. These sampled metrics are **mandatory**
     in this version.

4. **Advance the clock**
   `env.run(until=SimulationSettings.total_simulation_time)`

5. **Return analyzer**
   Wraps the collected state into `ResultsAnalyzer` for stats & plots.

---

## Input contract (what the runner expects)

The runner assumes `simulation_input` has already passed full validation:

* All edge targets are declared nodes; external IDs appear only as sources.
* Load balancer coverage and edges are coherent.
* No self-loops; only the LB fans out among declared nodes.
* Edge latency RVs have `mean > 0` (and `variance ≥ 0` if provided).
* Server resources meet minimums (≥ 1 core, ≥ 256 MB RAM), etc.

> Build with `AsyncFlow` or load from YAML — both paths enforce the same rules.

---

## Error handling

* **Type errors (builder misuse)** should not reach the runner; they’re raised by the builder (`TypeError`) before `build_payload()`.
* **Validation errors** (`ValueError`) are raised during payload construction/validation, not by the runner.
* **Wiring errors** (`TypeError`) are guarded by validation and indicate an unexpected mismatch between payload and runtime types. With a validated payload, you shouldn’t see them.

---

## Determinism & RNG

The runner uses `numpy.random.default_rng()` internally. Seeding is not yet a
public parameter; exact reproducibility across runs is **not guaranteed** in
this version. If you need strict reproducibility, pin your environment and keep
payloads identical; a dedicated seeding hook may be added in a future release.

---

## Performance characteristics

* **Runtime cost** scales with the number of requests and the complexity of
  endpoint steps (CPU vs I/O waits).
* **Sampling memory** roughly scales as
  `(#entities × #enabled sampled metrics) × (total_simulation_time / sample_period_s)`.
  For long runs, consider a larger `sample_period_s` (e.g., `0.02–0.05`) to
  reduce the size of time series.
* The collector is a single coroutine that performs `O(entities)` appends on
  each tick; the hot path inside actors remains `O(1)` per event.

---

## Usage with Load Balancers

Topologies **with a LB** are first-class:

* Only the LB may have multiple outgoing edges (fan-out).
* The analyzer operates on **lists** of servers and edges; plots will naturally
  show one line per server/edge where appropriate.
* Validation ensures every `server_covered` by the LB has a corresponding LB→server edge.

---

## One-shot runner (recommended)

A `SimulationRunner` instance is designed to **run once**. For a new scenario
(or new settings), create a **new** `simpy.Environment` and a **new**
`SimulationRunner`. Reusing a runner after `run()` is not supported.

---

## Best practices

* **Let the builder fail fast.** Always construct payloads via `AsyncFlow` (or YAML + validation) before running.
* **Keep steps coherent.** CPU step → `cpu_time`, RAM step → `necessary_ram`, I/O step → `io_waiting_time`. Exactly one key per step.
* **Model the network realistically.** Put latency RVs on **every** hop that matters (client↔LB, LB↔server, server↔client).
* **Tune sampling.** High-frequency sampling is useful for short diagnostic runs; increase `sample_period_s` for long capacity sweeps.

---

## See also

* **Builder:** `AsyncFlow` — compose and validate the payload (workload, topology, settings).
* **Analyzer:** `ResultsAnalyzer` — query KPIs and plot latency/throughput/queues/RAM.
* **Workload:** `RqsGenerator`, `RVConfig` — define traffic models (Poisson or Gaussian–Poisson).
* **Components:** `Client`, `Server`, `Endpoint`, `Edge`, `LoadBalancer`.

This API keeps **assembly** and **execution** separate: you design and validate
your system with `AsyncFlow`, then hand it to `SimulationRunner` to execute and
measure — a clean workflow that scales from minimal examples to complex,
load-balanced topologies.
