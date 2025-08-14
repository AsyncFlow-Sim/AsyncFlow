# AsyncFlow — Simulation Input Schema (v2)

This document describes the **complete input contract** used by AsyncFlow to run a simulation, the **design rationale** behind it, and the **validation guarantees** enforced by the Pydantic layer. At the end you’ll find an **end-to-end YAML example** you can run as-is.

The entry point is:

```python
class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""
    rqs_input: RqsGenerator
    topology_graph: TopologyGraph
    sim_settings: SimulationSettings
```

Everything the engine needs is captured by these three components:

* **`rqs_input`** — workload model (how traffic is generated).
* **`topology_graph`** — system under test as a directed graph (nodes & edges).
* **`sim_settings`** — global simulation controls and which metrics to collect.

---

## Rationale

### 1) Separation of concerns

* **Workload** (traffic intensity & arrival process) is independent from **topology** (architecture) and **simulation control** (duration & metrics).
* You can reuse the same topology with different workloads (or vice versa) without touching unrelated parts.

### 2) Validation-first, fail-fast

* Inputs are **typed** and **validated** before the engine starts.
* Validation catches type errors, dangling references, illegal step definitions, and inconsistent graphs.
* Once a payload parses, the runtime code can remain lean (no defensive checks scattered everywhere).

### 3) Small-to-large composition

* The smallest unit is a **`Step`** (one resource-bound operation).
* Steps compose into an **`Endpoint`** (ordered workflow).
* Endpoints live on a **`Server`** node with finite resources.
* Nodes and **Edges** form a **`TopologyGraph`**.
* A closed set of **Enums** eliminates magic strings.

---

## 1) Workload: `RqsGenerator`

**Purpose:** Defines the stochastic traffic generator that produces request arrivals.

```python
class RqsGenerator(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.GENERATOR
    avg_active_users: RVConfig
    avg_request_per_minute_per_user: RVConfig
    user_sampling_window: int = Field(
        default=TimeDefaults.USER_SAMPLING_WINDOW,
        ge=TimeDefaults.MIN_USER_SAMPLING_WINDOW,
        le=TimeDefaults.MAX_USER_SAMPLING_WINDOW,
    )
```

### Random variables (`RVConfig`)

```python
class RVConfig(BaseModel):
    mean: float
    distribution: Distribution = Distribution.POISSON
    variance: float | None = None
```

**Validators & guarantees**

* `mean` is **numeric** and coerced to `float`. (Non-numeric → `ValueError`.)
* If `distribution ∈ {NORMAL, LOG_NORMAL}` and `variance is None`, then `variance := mean`.
* Workload-specific constraints:

  * `avg_request_per_minute_per_user.distribution` **must be** `POISSON`.
  * `avg_active_users.distribution` **must be** `POISSON` or `NORMAL`.
* `user_sampling_window` is an **integer in seconds**, bounded to `[1, 120]`.

**Why these constraints?**
They match the currently implemented samplers (Poisson–Poisson and Normal–Poisson).

---

## 2) System Graph: `TopologyGraph`

**Purpose:** Describes the architecture as a **directed graph**. Nodes are macro-components (client, server, optional load balancer); edges are network links with latency models.

```python
class TopologyGraph(BaseModel):
    nodes: TopologyNodes
    edges: list[Edge]
```

### 2.1 Nodes

```python
class TopologyNodes(BaseModel):
    servers: list[Server]
    client: Client
    load_balancer: LoadBalancer | None = None

    # also: model_config = ConfigDict(extra="forbid")
```

#### `Client`

```python
class Client(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.CLIENT
    # validator: type must equal SystemNodes.CLIENT
```

#### `ServerResources`

```python
class ServerResources(BaseModel):
    cpu_cores: PositiveInt = Field(ServerResourcesDefaults.CPU_CORES,
                                   ge=ServerResourcesDefaults.MINIMUM_CPU_CORES)
    db_connection_pool: PositiveInt | None = Field(ServerResourcesDefaults.DB_CONNECTION_POOL)
    ram_mb: PositiveInt = Field(ServerResourcesDefaults.RAM_MB,
                                ge=ServerResourcesDefaults.MINIMUM_RAM_MB)
```

Each attribute maps directly to a SimPy primitive (core tokens, RAM container, optional DB pool).

#### `Step` (atomic unit)

```python
class Step(BaseModel):
    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_operation: dict[StepOperation, PositiveFloat | PositiveInt]
```

**Coherence validator**

* `step_operation` must contain **exactly one** key.
* Valid pairings:

  * CPU step → `{ cpu_time: PositiveFloat }`
  * RAM step → `{ necessary_ram: PositiveInt | PositiveFloat }`
  * I/O step → `{ io_waiting_time: PositiveFloat }`
* Any mismatch (e.g., RAM step with `cpu_time`) → `ValueError`.

#### `Endpoint`

```python
class Endpoint(BaseModel):
    endpoint_name: str
    steps: list[Step]

    @field_validator("endpoint_name", mode="before")
    def name_to_lower(cls, v): return v.lower()
```

Canonical lowercase names avoid accidental duplicates by case.

#### `Server`

```python
class Server(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.SERVER
    server_resources: ServerResources
    endpoints: list[Endpoint]
    # validator: type must equal SystemNodes.SERVER
```

#### `LoadBalancer` (optional)

```python
class LoadBalancer(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.LOAD_BALANCER
    algorithms: LbAlgorithmsName = LbAlgorithmsName.ROUND_ROBIN
    server_covered: set[str] = Field(default_factory=set)
    # validator: type must equal SystemNodes.LOAD_BALANCER
```

### 2.2 Edges

```python
class Edge(BaseModel):
    id: str
    source: str          # may be an external entrypoint (e.g., generator id)
    target: str          # MUST be a declared node id
    latency: RVConfig
    edge_type: SystemEdges = SystemEdges.NETWORK_CONNECTION
    dropout_rate: float = Field(NetworkParameters.DROPOUT_RATE,
                                ge=NetworkParameters.MIN_DROPOUT_RATE,
                                le=NetworkParameters.MAX_DROPOUT_RATE)
    # validator: source != target
    # validator on latency: mean > 0, variance >= 0 if provided
```

> **Note:** The former `probability` field has been **removed**. Fan-out is controlled at the **load balancer** via `algorithms` (e.g., round-robin, least-connections). Non-LB nodes are not allowed to have multiple outgoing edges (see graph-level validators below).

### 2.3 Graph-level validators

The `TopologyGraph` class performs several global checks:

1. **Unique edge IDs**

   * Duplicate edge ids → `ValueError`.

2. **Referential integrity**

   * Every **`target`** must be a declared node (`client`, any `server`, optional `load_balancer`).
   * **External IDs** (e.g., generator id) are **allowed only as sources** and **must never appear as a target** anywhere.

3. **Load balancer integrity (if present)**

   * `server_covered ⊆ declared server ids`.
   * There must be **an outgoing edge from the LB to every covered server**; missing links → `ValueError`.

4. **Fan-out restriction**

   * Among **declared nodes**, **only the load balancer** may have **multiple outgoing edges**.
   * Edges originating from non-declared external sources (e.g., generator) are ignored by this check.
   * Violations list the offending source ids.

---

## 3) Simulation Control: `SimulationSettings`

```python
class SimulationSettings(BaseModel):
    total_simulation_time: int = Field(
        default=TimeDefaults.SIMULATION_TIME,
        ge=TimeDefaults.MIN_SIMULATION_TIME,
    )
    enabled_sample_metrics: set[SampledMetricName] = Field(default_factory=...)
    enabled_event_metrics: set[EventMetricName] = Field(default_factory=...)
    sample_period_s: float = Field(
        default=SamplePeriods.STANDARD_TIME,
        ge=SamplePeriods.MINIMUM_TIME,
        le=SamplePeriods.MAXIMUM_TIME,
    )
```

**What it controls**

* **Clock** — `total_simulation_time` in seconds (default 3600, min 5).
* **Sampling cadence** — `sample_period_s` in seconds (default 0.01; bounds `[0.001, 0.1]`).
* **Metric selection** — default sets include:

  * Sampled (time-series): `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`.
  * Event (per-request): `rqs_clock`.

---

## 4) Enums & Units (Quick Reference)

**Distributions:** `poisson`, `normal`, `log_normal`, `exponential`, `uniform`
**Node types:** `generator`, `server`, `client`, `load_balancer` (fixed by models)
**Edge types:** `network_connection`
**LB algorithms:** `round_robin`, `least_connection`
**Step kinds:**

* CPU: `initial_parsing`, `cpu_bound_operation`
* RAM: `ram`
* I/O: `io_task_spawn`, `io_llm`, `io_wait`, `io_db`, `io_cache`
  **Step operation keys:** `cpu_time`, `io_waiting_time`, `necessary_ram`
  **Sampled metrics:** `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`
  **Event metrics:** `rqs_clock` (and `llm_cost` reserved)

**Units & conventions**

* **Time:** seconds (`cpu_time`, `io_waiting_time`, latencies, `total_simulation_time`, `sample_period_s`, `user_sampling_window`)
* **RAM:** megabytes (`ram_mb`, `necessary_ram`)
* **Rates:** requests/minute (`avg_request_per_minute_per_user.mean`)
* **Probabilities:** `[0.0, 1.0]` (`dropout_rate`)
* **IDs:** strings; must be **unique** within their category

---

## 5) Validation Checklist (What is guaranteed if the payload parses)

### Workload (`RqsGenerator`, `RVConfig`)

* `mean` is numeric (`int|float`) and coerced to `float`.
* If `distribution ∈ {NORMAL, LOG_NORMAL}` and `variance is None` → `variance := mean`.
* `avg_request_per_minute_per_user.distribution == POISSON`.
* `avg_active_users.distribution ∈ {POISSON, NORMAL}`.
* `user_sampling_window ∈ [1, 120]` seconds.
* `type` fields default to the correct enum (`generator`) and are strongly typed.

### Steps & Endpoints

* `endpoint_name` is normalized to lowercase.
* Each `Step` has **exactly one** `step_operation` key.
* `Step.kind` and `step_operation` key **must match**:

  * CPU ↔ `cpu_time`
  * RAM ↔ `necessary_ram`
  * I/O ↔ `io_waiting_time`
* All step operation values are strictly **positive**.

### Nodes

* `Client.type == client`, `Server.type == server`, `LoadBalancer.type == load_balancer` (enforced).
* `ServerResources` obey lower bounds: `cpu_cores ≥ 1`, `ram_mb ≥ 256`.
* `TopologyNodes` contains **unique ids** across `client`, `servers[]`, and (optional) `load_balancer`. Duplicates → `ValueError`.
* `TopologyNodes` forbids unknown fields (`extra="forbid"`).

### Edges

* **No self-loops:** `source != target`.
* **Latency sanity:** `latency.mean > 0`; if `variance` is provided, `variance ≥ 0`. Error messages reference the **edge id**.
* `dropout_rate ∈ [0, 1]`.

### Graph (`TopologyGraph`)

* **Edge ids are unique.**
* **Targets** are always **declared node ids**.
* **External ids** (e.g., generator) are allowed only as **sources**; they must **never** appear as **targets**.
* **Load balancer integrity:**

  * `server_covered` is a subset of declared servers.
  * Every covered server has a **corresponding edge from the LB** (LB → srv). Missing links → `ValueError`.
* **Fan-out restriction:** among **declared nodes**, only the **LB** can have **multiple outgoing edges**. Offenders are listed.

If your payload passes validation, the engine can wire and run the simulation deterministically with consistent semantics.



