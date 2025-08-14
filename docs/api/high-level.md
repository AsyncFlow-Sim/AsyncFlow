# AsyncFlow — High-Level API (`AsyncFlow`, `SimulationRunner`)

This page explains how to programmatically **assemble a validated simulation payload** and **run** it, returning metrics and plots through the analyzer.

* **Builder**: `AsyncFlow` – compose workload, topology, and settings into a single `SimulationPayload`.
* **Runner**: `SimulationRunner` – wire actors, start processes, collect metrics, and return a `ResultsAnalyzer`.

---

## Imports

```python
# High-level API
from asyncflow import AsyncFlow, SimulationRunner

# Public leaf schemas (components & workload)
from asyncflow.components import Client, Server, Endpoint, Edge
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.settings import SimulationSettings
```

> These are the **only** imports end users need. Internals (actors, registries, etc.) remain private.

---

## Quick start

A minimal end-to-end example:

```python
from __future__ import annotations
import simpy

from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.components import Client, Server, Endpoint, Edge
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.settings import SimulationSettings

# 1) Workload
rqs = RqsGenerator(
    id="rqs-1",
    avg_active_users=RVConfig(mean=50,       # Poisson by default
                              # or Distribution.NORMAL with variance auto=mean
                              ),
    avg_request_per_minute_per_user=RVConfig(mean=30),  # MUST be Poisson
    user_sampling_window=60,  # seconds
)

# 2) Topology components
client = Client(id="client-1")

endpoint = Endpoint(
    endpoint_name="/hello",
    steps=[
        {"kind": "ram",               "step_operation": {"necessary_ram": 32}},
        {"kind": "initial_parsing",   "step_operation": {"cpu_time": 0.002}},
        {"kind": "io_wait",           "step_operation": {"io_waiting_time": 0.010}},
    ],
)

server = Server(
    id="srv-1",
    server_resources={"cpu_cores": 1, "ram_mb": 1024},
    endpoints=[endpoint],
)

edges = [
    Edge(id="gen-client",   source="rqs-1",   target="client-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
    Edge(id="client-srv1",  source="client-1", target="srv-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
    Edge(id="srv1-client",  source="srv-1",    target="client-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
]

# 3) Settings (baseline sampled metrics are mandatory)
settings = SimulationSettings(
    total_simulation_time=300,  # seconds (≥ 5)
    sample_period_s=0.01,       # 0.001 ≤ value ≤ 0.1
    # enabled_sample_metrics and enabled_event_metrics: safe defaults already set
)

# 4) Build (validates everything with Pydantic)
payload = (
    AsyncFlow()
    .add_generator(rqs)
    .add_client(client)
    .add_servers(server)
    .add_edges(*edges)
    .add_simulation_settings(settings)
    .build_payload()
)

# 5) Run
env = simpy.Environment()
results = SimulationRunner(env=env, simulation_input=payload).run()

# 6) Use the analyzer (examples)
print(results.get_latency_stats())
ts, rps = results.get_throughput_series()
sampled = results.get_sampled_metrics()
```

---

## `AsyncFlow` — builder (public)

`AsyncFlow` helps you construct a **self-consistent** `SimulationPayload` with fluent, chainable calls. Every piece you add is type-checked; the final `build_payload()` validates the full graph and settings.

### API

```python
class AsyncFlow:
    def add_generator(self, rqs_generator: RqsGenerator) -> Self: ...
    def add_client(self, client: Client) -> Self: ...
    def add_servers(self, *servers: Server) -> Self: ...
    def add_edges(self, *edges: Edge) -> Self: ...
    def add_simulation_settings(self, sim_settings: SimulationSettings) -> Self: ...
    def add_load_balancer(self, load_balancer: LoadBalancer) -> Self: ...
    def build_payload(self) -> SimulationPayload: ...
```

### Validation performed by `build_payload()`

On build, the composed payload is validated by the Pydantic schemas:

1. **Presence**

   * Generator, client, **≥ 1 server**, **≥ 1 edge**, settings are required.

2. **Unique IDs**

   * Duplicate server IDs or edge IDs are rejected.

3. **Node types**

   * Fixed enums: `client`, `server`, `load_balancer`; validated on each node.

4. **Edge integrity**

   * Every edge **target** must be a declared node ID.
   * **External IDs** (e.g., the generator id) are allowed **only as sources**.
   * **No self-loops** (`source != target`).

5. **Load balancer sanity** (if present)

   * `server_covered ⊆ declared servers`.
   * There must be an **edge from the LB to every covered server**.

6. **(Engine rule)** “No fan-out except LB”

   * Only the LB may have multiple outgoing edges among declared nodes.

7. **Latency RV constraints (edges)**

   * `latency.mean > 0`, and if `variance` exists, `variance ≥ 0`.

If a rule fails, a **descriptive `ValueError`** points at the offending entity/field.

### Typical errors you might see

* Missing parts:
  `ValueError: The generator input must be instantiated before the simulation`
* Type mis-match:
  `TypeError: All the instances must be of the type Server`
* Graph violations:
  `ValueError: Edge client-1->srv-X references unknown target node 'srv-X'`
* LB coverage:
  `ValueError: Servers ['srv-2'] are covered by LB 'lb-1' but have no outgoing edge from it.`

---

## `SimulationRunner` — orchestrator (public)

`SimulationRunner` takes a validated `SimulationPayload`, **instantiates all runtimes**, **wires** edges to their target mailboxes, **starts** every actor, **collects** sampled metrics, and advances the SimPy clock.

### API

```python
class SimulationRunner:
    def __init__(self, *, env: simpy.Environment, simulation_input: SimulationPayload) -> None: ...
    def run(self) -> ResultsAnalyzer: ...
    @classmethod
    def from_yaml(cls, *, env: simpy.Environment, yaml_path: str | Path) -> "SimulationRunner": ...
```

* **`env`**: your SimPy environment (you control its lifetime).

* **`simulation_input`**: the payload returned by `AsyncFlow.build_payload()` (or parsed from YAML).

* **`run()`**:

  * Builds and wires all runtime actors (`RqsGeneratorRuntime`, `ClientRuntime`, `ServerRuntime`, `LoadBalancerRuntime`, `EdgeRuntime`).
  * Starts the **SampledMetricCollector** (baseline sampled metrics are mandatory and collected automatically).
  * Runs until `SimulationSettings.total_simulation_time`.
  * Returns a **`ResultsAnalyzer`** with helpers like:

    * `get_latency_stats()`
    * `get_throughput_series()`
    * `get_sampled_metrics()`
    * plotting helpers (`plot_latency_distribution`, `plot_throughput`, …).

* **`from_yaml`**: convenience constructor for loading a full payload from a YAML file and running it immediately.

### Determinism & RNG

* The runner uses `numpy.random.default_rng()` internally.
  Seeding is not yet exposed as a public parameter; exact reproducibility across runs is **not guaranteed** in this version.

---

## Extended example: with Load Balancer

```python
from asyncflow.components import Client, Server, Endpoint, Edge
from asyncflow.components import LoadBalancer
from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.settings import SimulationSettings
import simpy

client = Client(id="client-1")

srv1 = Server(
    id="srv-1",
    server_resources={"cpu_cores": 1, "ram_mb": 1024},
    endpoints=[Endpoint(endpoint_name="/api", steps=[{"kind":"ram","step_operation":{"necessary_ram":64}}])]
)
srv2 = Server(
    id="srv-2",
    server_resources={"cpu_cores": 2, "ram_mb": 2048},
    endpoints=[Endpoint(endpoint_name="/api", steps=[{"kind":"io_db","step_operation":{"io_waiting_time":0.012}}])]
)

lb = LoadBalancer(id="lb-1", algorithms="round_robin", server_covered={"srv-1","srv-2"})

edges = [
    Edge(id="gen-client",  source="rqs-1",   target="client-1", latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="client-lb",   source="client-1", target="lb-1",    latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="lb-srv1",     source="lb-1",    target="srv-1",    latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="lb-srv2",     source="lb-1",    target="srv-2",    latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="srv1-client", source="srv-1",   target="client-1", latency={"mean":0.003,"distribution":"exponential"}),
    Edge(id="srv2-client", source="srv-2",   target="client-1", latency={"mean":0.003,"distribution":"exponential"}),
]

payload = (
    AsyncFlow()
    .add_generator(RqsGenerator(
        id="rqs-1",
        avg_active_users=RVConfig(mean=120),
        avg_request_per_minute_per_user=RVConfig(mean=20),
        user_sampling_window=60,
    ))
    .add_client(client)
    .add_servers(srv1, srv2)
    .add_load_balancer(lb)
    .add_edges(*edges)
    .add_simulation_settings(SimulationSettings(total_simulation_time=600, sample_period_s=0.02))
    .build_payload()
)

env = simpy.Environment()
results = SimulationRunner(env=env, simulation_input=payload).run()
```

---

## Performance tips

* **Sampling cost** grows with `total_simulation_time / sample_period_s × (#sampled metrics × entities)`.
  For long runs, consider a larger `sample_period_s` (e.g., `0.02–0.05`) to reduce memory while keeping the baseline metrics intact.

* **Validation first**: prefer failing early by letting `build_payload()` validate everything before the runner starts.

---

## Error handling (what throws)

* **Type errors** on builder inputs (`TypeError`) when passing the wrong class to `add_*`.
* **Validation errors** (`ValueError`) on `build_payload()` if the graph is inconsistent (unknown targets, duplicates, LB edges missing, self-loops, illegal fan-out, latency rules, etc.).
* **Runtime wiring errors** (`TypeError`) if an unknown runtime target/source type appears while wiring edges (should not occur with a validated payload).

---

## YAML path (alternative)

You can construct the payload in YAML (see “YAML Input Guide”), then:

```python
import simpy
from asyncflow import SimulationRunner

env = simpy.Environment()
runner = SimulationRunner.from_yaml(env=env, yaml_path="scenario.yml")
results = runner.run()
```

---

