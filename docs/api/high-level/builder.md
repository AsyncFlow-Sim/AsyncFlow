# AsyncFlow — Public API Reference: `AsyncFlow` Builder

`AsyncFlow` is the **fluent builder** that assembles a complete, validated
`SimulationPayload`. It lets you compose workload, topology, edges, and global
settings with clear types and fail-fast validation. The resulting payload can be
run with `SimulationRunner`.

* **You write:** small, typed building blocks (workload + components + settings)
* **Builder does:** composition & Pydantic validation (graph integrity, rules)
* **Runner does:** execution & metrics collection

---

## Imports

```python
# Builder + Runner
from asyncflow import AsyncFlow, SimulationRunner

# Public leaf schemas
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.components import Client, Server, Endpoint, Edge, LoadBalancer
from asyncflow.settings import SimulationSettings
```

---

## Quick start

```python
import simpy
from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.components import Client, Server, Endpoint, Edge
from asyncflow.settings import SimulationSettings

# 1) Workload
rqs = RqsGenerator(
    id="rqs-1",
    avg_active_users=RVConfig(mean=50),                  # Poisson by default
    avg_request_per_minute_per_user=RVConfig(mean=30),   # MUST be Poisson
)

# 2) Components
client = Client(id="client-1")
server = Server(
    id="srv-1",
    server_resources={"cpu_cores": 1, "ram_mb": 1024},
    endpoints=[
        Endpoint(
            endpoint_name="/hello",
            steps=[
                {"kind": "ram", "step_operation": {"necessary_ram": 32}},
                {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
                {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
            ],
        )
    ],
)

edges = [
    Edge(id="gen-client",  source="rqs-1",   target="client-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
    Edge(id="client-srv1", source="client-1", target="srv-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
    Edge(id="srv1-client", source="srv-1",    target="client-1",
         latency={"mean": 0.003, "distribution": "exponential"}),
]

# 3) Settings (baseline sampled metrics are mandatory by design)
settings = SimulationSettings(total_simulation_time=300, sample_period_s=0.01)

# 4) Build (validates everything)
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
```

---

## API

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

### Method details

* **`add_generator(rqs_generator)`**
  Adds the stochastic workload model.
  Errors: `TypeError` if not a `RqsGenerator`.

* **`add_client(client)`**
  Adds the single client node.
  Errors: `TypeError` if not a `Client`.

* **`add_servers(*servers)`**
  Adds one or more servers (varargs).
  Errors: `TypeError` if any arg is not a `Server`.

* **`add_edges(*edges)`**
  Adds one or more directed edges (varargs).
  Errors: `TypeError` if any arg is not an `Edge`.
  Notes: *Targets must be declared nodes; sources may be external (e.g. `"rqs-1"`).*

* **`add_load_balancer(load_balancer)`** *(optional)*
  Adds a load balancer node.
  Errors: `TypeError` if not a `LoadBalancer`.

* **`add_simulation_settings(sim_settings)`**
  Adds global settings (duration, sampling period, metric selection).
  Errors: `TypeError` if not a `SimulationSettings`.

* **`build_payload()` → `SimulationPayload`**
  Finalize composition and run full validation.
  Errors: `ValueError` on missing parts or invalid graph.

---

## Validation performed by `build_payload()`

(Implemented via Pydantic model validation across the payload’s schemas.)

1. **Presence**

   * Requires: generator, client, **≥ 1 server**, **≥ 1 edge**, settings.

2. **Unique IDs**

   * Duplicate server IDs or edge IDs are rejected.

3. **Node types**

   * `client`, `server`, and `load_balancer` are fixed enums; enforced per node.

4. **Edge integrity**

   * Every **target** must be a declared node ID.
   * **External IDs** (e.g. the generator id) are allowed **only** as **sources**.
   * **No self-loops** (`source != target`).

5. **Load balancer sanity** (if present)

   * `server_covered ⊆ declared servers`.
   * There is an **outgoing edge from the LB to every covered server**.

6. **Engine rule: no fan-out except LB**

   * Among declared nodes, only the LB may have multiple outgoing edges.

7. **Latency RV constraints (edges)**

   * `latency.mean > 0`; if `variance` provided, `variance ≥ 0`.

If any rule fails, a **descriptive `ValueError`** points to the offending field/entity.

---

## Typical errors & how to fix

* **Missing parts**
  `ValueError: The generator input must be instantiated before the simulation`
  → Call the missing `add_*` method before `build_payload()`.

* **Wrong type passed**
  `TypeError: All the instances must be of the type Server`
  → Ensure you pass `Server` objects to `add_servers(...)` (not dicts).

* **Unknown edge target**
  `ValueError: Edge client-1->srv-X references unknown target node 'srv-X'`
  → Add a `Server(id="srv-X", ...)` or fix the edge target.

* **LB coverage without edges**
  `ValueError: Servers ['srv-2'] are covered by LB 'lb-1' but have no outgoing edge from it.`
  → Add `Edge(source="lb-1", target="srv-2", ...)`.

* **Illegal fan-out**
  `ValueError: Only the load balancer can have multiple outgoing edges. Offending sources: ['client-1']`
  → Route fan-out through a `LoadBalancer`.

---

## Extended example — with Load Balancer

```python
from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.workload import RqsGenerator, RVConfig
from asyncflow.components import Client, Server, Endpoint, Edge, LoadBalancer
from asyncflow.settings import SimulationSettings
import simpy

client = Client(id="client-1")

srv1 = Server(
    id="srv-1",
    server_resources={"cpu_cores": 1, "ram_mb": 1024},
    endpoints=[Endpoint(endpoint_name="/api",
                        steps=[{"kind":"ram","step_operation":{"necessary_ram":64}}])],
)
srv2 = Server(
    id="srv-2",
    server_resources={"cpu_cores": 2, "ram_mb": 2048},
    endpoints=[Endpoint(endpoint_name="/api",
                        steps=[{"kind":"io_db","step_operation":{"io_waiting_time":0.012}}])],
)

lb = LoadBalancer(id="lb-1", algorithms="round_robin", server_covered={"srv-1","srv-2"})

edges = [
    Edge(id="gen-client",  source="rqs-1",   target="client-1",
         latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="client-lb",   source="client-1", target="lb-1",
         latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="lb-srv1",     source="lb-1",    target="srv-1",
         latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="lb-srv2",     source="lb-1",    target="srv-2",
         latency={"mean":0.002,"distribution":"exponential"}),
    Edge(id="srv1-client", source="srv-1",   target="client-1",
         latency={"mean":0.003,"distribution":"exponential"}),
    Edge(id="srv2-client", source="srv-2",   target="client-1",
         latency={"mean":0.003,"distribution":"exponential"}),
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

## Tips & pitfalls

* **IDs are case-sensitive** and must be unique per category (servers, edges, LB).
* **Edge targets must be declared nodes.** External IDs (like the generator) can only appear as **sources**.
* **LB fan-out only.** If you need branching, introduce a `LoadBalancer`.
* **RqsGenerator constraints:**
  `avg_request_per_minute_per_user` **must** be Poisson;
  `avg_active_users` must be **Poisson** or **Normal** (variance auto-filled if missing).
* **Step coherence:**
  CPU step → `cpu_time`; RAM step → `necessary_ram`; I/O step → `io_waiting_time`. Exactly **one** per step.

---

## Interop: YAML ↔ Python

You can build the same payload from YAML and then use `SimulationRunner.from_yaml(...)`. Field names mirror the Python model names and the enum values (strings) are identical.

---

## Versioning & stability

* Exceptions: `TypeError` for wrong types passed to builder; `ValueError` for invalid or incomplete payloads.
* Validation rules and enum names are part of the public contract (semantic versioning applies).
* The builder does not mutate your objects; it assembles and validates them into a `SimulationPayload`.


