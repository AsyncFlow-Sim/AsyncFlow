# AsyncFlow — Simulation Input Schema (v2)

This document describes the **complete input contract** used by AsyncFlow to run a simulation, the **design rationale** behind it, and the **guarantees** provided by the validation layer. It closes with an **end-to-end example** (YAML) you can drop into the project and run as-is.

The entry point is the Pydantic model:

```python
class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""
    rqs_input: RqsGeneratorInput
    topology_graph: TopologyGraph
    sim_settings: SimulationSettings
```

Everything the engine needs is captured by these three components:

* **`rqs_input`** — the workload model (how traffic is generated).
* **`topology_graph`** — the system under test, described as a directed graph (nodes & edges).
* **`sim_settings`** — global simulation controls and which metrics to collect.

---

## Why this shape? (Rationale)

### 1) **Separation of concerns**

* **Workload** (traffic intensity & arrival process) is independent from the **topology** (architecture under test) and from **simulation control** (duration & metrics).
* This lets you reuse the same topology with different workloads, or vice versa, without touching unrelated parts.

### 2) **Validation-first, fail-fast**

* All inputs are **typed** and **validated** with Pydantic before the engine starts.
* Validation catches type errors, inconsistent references, and illegal combinations (e.g., an I/O step with a CPU metric).
* When a payload parses successfully, the engine can run without defensive checks scattered in runtime code.

### 3) **Small-to-large composition**

* The smallest unit is a **`Step`** (one resource-bound operation).
* Steps compose into an **`Endpoint`** (an ordered workflow).
* Endpoints live on a **`Server`** node with finite resources.
* Nodes and **Edges** form a **`TopologyGraph`**.
* A disciplined set of **Enums** (no magic strings) ensure a closed vocabulary.

---

## 1. Workload: `RqsGeneratorInput`

### Purpose

Defines the traffic generator that produces request arrivals.

```python
class RqsGeneratorInput(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.GENERATOR
    avg_active_users: RVConfig
    avg_request_per_minute_per_user: RVConfig
    user_sampling_window: int = Field( ... )  # seconds
```

### Random variables (`RVConfig`)

```python
class RVConfig(BaseModel):
    mean: float
    distribution: Distribution = Distribution.POISSON
    variance: float | None = None
```

#### Validation & guarantees

* **`mean` is numeric**
  `@field_validator("mean", mode="before")` coerces to `float` and rejects non-numeric values.
* **Auto variance** for Normal/LogNormal
  `@model_validator(mode="after")` sets `variance = mean` if missing and the distribution is `NORMAL` or `LOG_NORMAL`.
* **Distribution constraints** on workload:

  * `avg_request_per_minute_per_user` **must be Poisson** (engine currently optimised for Poisson arrivals).
  * `avg_active_users` **must be Poisson or Normal**.
  * Enforced via `@field_validator(..., mode="after")` with clear error messages.

#### Why these constraints?

* They reflect the current joint-sampling logic in the generator: **Poisson–Poisson** and **Normal–Poisson** are implemented and tested. Additional combos can be enabled later without changing the public contract.

---

## 2. System Graph: `TopologyGraph`

### Purpose

Defines the architecture under test as a **directed graph**: nodes are components (client, server, optional load balancer), edges are network links with latency models.

```python
class TopologyGraph(BaseModel):
    nodes: TopologyNodes
    edges: list[Edge]
```

### Nodes

```python
class TopologyNodes(BaseModel):
    servers: list[Server]
    client: Client
    load_balancer: LoadBalancer | None = None
```

#### `Client`

```python
class Client(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.CLIENT
```

* **Validator**: `type` must equal `SystemNodes.CLIENT`.

#### `ServerResources`

```python
class ServerResources(BaseModel):
    cpu_cores: PositiveInt = Field(...)
    db_connection_pool: PositiveInt | None = Field(...)
    ram_mb: PositiveInt = Field(...)
```

* Maps directly to SimPy containers (CPU tokens, RAM capacity, etc.).
* Bounds enforced via `Field(ge=..., ...)`.

#### `Step` (the atomic unit)

```python
class Step(BaseModel):
    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_operation: dict[StepOperation, PositiveFloat | PositiveInt]
```

**Key validator (coherence):**

```python
@model_validator(mode="after")
def ensure_coherence_type_operation(cls, model: "Step") -> "Step":
    # exactly one operation key, and it must match the step kind
```

* If `kind` is CPU → the only key must be `CPU_TIME`.
* If `kind` is RAM → only `NECESSARY_RAM`.
* If `kind` is I/O → only `IO_WAITING_TIME`.
* Values must be positive (`PositiveFloat/PositiveInt`).

This guarantees every step is **unambiguous** and **physically meaningful**.

#### `Endpoint`

```python
class Endpoint(BaseModel):
    endpoint_name: str
    steps: list[Step]

    @field_validator("endpoint_name", mode="before")
    def name_to_lower(cls, v: str) -> str:
        return v.lower()
```

* Canonical lowercase naming avoids duplicates differing only by case.

#### `Server`

```python
class Server(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.SERVER
    server_resources: ServerResources
    endpoints: list[Endpoint]
```

* **Validator**: `type` must equal `SystemNodes.SERVER`.

#### `LoadBalancer` (optional)

```python
class LoadBalancer(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.LOAD_BALANCER
    algorithms: LbAlgorithmsName = LbAlgorithmsName.ROUND_ROBIN
    server_covered: set[str] = Field(default_factory=set)
```

### Edges

```python
class Edge(BaseModel):
    id: str
    source: str
    target: str
    latency: RVConfig
    probability: float = Field(1.0, ge=0.0, le=1.0)
    edge_type: SystemEdges = SystemEdges.NETWORK_CONNECTION
    dropout_rate: float = Field(...)
```

#### Validation & guarantees

* **Latency sanity**
  `@field_validator("latency", mode="after")` ensures `mean > 0` and `variance >= 0` (if provided). Error messages mention the **edge id** for clarity.
* **No self-loops**
  `@model_validator(mode="after")` rejects `source == target`.
* **Unique edge IDs**
  `TopologyGraph.unique_ids` enforces uniqueness across `edges`.
* **Referential integrity**
  `TopologyGraph.edge_refs_valid` ensures:

  * Every `target` is a declared node ID.
  * **External sources** (e.g., the generator id) are allowed, but **may not** appear as a `target` anywhere.
* **Load balancer integrity** (if present)
  `TopologyGraph.valid_load_balancer` enforces:

  * `server_covered ⊆ {server ids}`.
  * For every covered server there exists an **outgoing edge from the LB** to that server.

These checks make the graph **closed**, **consistent**, and **wirable** without surprises at runtime.

---

## 3. Simulation Control: `SimulationSettings`

```python
class SimulationSettings(BaseModel):
    total_simulation_time: int = Field(..., ge=TimeDefaults.MIN_SIMULATION_TIME)
    enabled_sample_metrics: set[SampledMetricName] = Field(default_factory=...)
    enabled_event_metrics: set[EventMetricName] = Field(default_factory=...)
    sample_period_s: float = Field(..., ge=SamplePeriods.MINIMUM_TIME, le=SamplePeriods.MAXIMUM_TIME)
```

### What it controls

* **Clock** — `total_simulation_time` (seconds).
* **Sampling cadence** — `sample_period_s` for time-series metrics.
* **What to collect** — two sets of enums:

  * `enabled_sample_metrics`: time-series KPIs (e.g., ready queue length, RAM in use, edge concurrency).
  * `enabled_event_metrics`: per-event KPIs (e.g., request clocks/latency).

### Why Enums matter here

Letting users pass strings like `"ram_in_use"` is error-prone. By using **`SampledMetricName`** and **`EventMetricName`** enums, the settings are **validated upfront**, so the runtime collector knows exactly which lists to allocate and fill. No hidden `KeyError`s halfway through a run.

---

## What these validations buy you

* **Type safety** (no accidental strings where enums are expected).
* **Physical realism** (no zero/negative times or RAM).
* **Graph integrity** (no dangling edges or self-loops).
* **Operational clarity** (every step has exactly one effect).
* **Better errors** (validators point to the exact field/entity at fault).

Together, they make the model **predictable** for the simulation engine and **pleasant** to debug.

---

## End-to-End Example (YAML)

This is a complete, valid payload you can load with `SimulationRunner.from_yaml(...)`.

```yaml
# ───────────────────────────────────────────────────────────────
# AsyncFlow scenario: generator → client → server → client
# ───────────────────────────────────────────────────────────────

rqs_input:
  id: rqs-1
  # avg_active_users can be POISSON or NORMAL; mean is required.
  avg_active_users:
    mean: 100
    distribution: poisson
  # must be POISSON (engine constraint)
  avg_request_per_minute_per_user:
    mean: 20
    distribution: poisson
  user_sampling_window: 60  # seconds

topology_graph:
  nodes:
    client:
      id: client-1
      type: client
    servers:
      - id: srv-1
        type: server
        server_resources:
          cpu_cores: 1
          ram_mb: 2048
          # db_connection_pool: 50     # optional
        endpoints:
          - endpoint_name: /predict
            steps:
              - kind: ram
                step_operation: { necessary_ram: 100 }
              - kind: initial_parsing        # CPU step (enum in your code)
                step_operation: { cpu_time: 0.001 }
              - kind: io_wait                # I/O step
                step_operation: { io_waiting_time: 0.100 }

  edges:
    - id: gen-to-client
      source: rqs-1          # external source OK
      target: client-1
      latency: { mean: 0.003, distribution: exponential }

    - id: client-to-server
      source: client-1
      target: srv-1
      latency: { mean: 0.003, distribution: exponential }

    - id: server-to-client
      source: srv-1
      target: client-1
      latency: { mean: 0.003, distribution: exponential }

sim_settings:
  total_simulation_time: 500
  sample_period_s: 0.05
  enabled_sample_metrics:
    - ready_queue_len
    - event_loop_io_sleep
    - ram_in_use
    - edge_concurrent_connection
  enabled_event_metrics:
    - rqs_clock
```

 Notes:
>
 * `kind` uses the **EndpointStep** enums you’ve defined (e.g., `ram`, `initial_parsing`, `io_wait`).
 * The coherence validator ensures that each `kind` uses the correct `step_operation` key and **exactly one** entry.
 * The **edge** constraints guarantee a clean, connected, and sensible graph.

---

## Summary

* The **payload** is small but expressive: workload, topology, and settings.
* The **validators** are doing real work: they make illegal states unrepresentable.
* The **enums** keep the contract tight and maintainable.
* Together, they let you move fast **without** breaking the simulation engine.

If you extend the engine (new distributions, step kinds, metrics), you can **keep the same contract** and enrich the enums & validators to preserve the same guarantees.
