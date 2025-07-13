### **FastSim — Request-Generator Input Configuration**

A **single, self-consistent contract** links three layers of the codebase:

1.  **Global Constants** – `TimeDefaults`, `Distribution`
2.  **Random Variable Schema** – `RVConfig`
3.  **Traffic-Generator Payload** – `RqsGeneratorInput`

Understanding how these layers interact is key to crafting valid and predictable traffic profiles, preventing common configuration errors before the simulation begins.

---

### 1. Global Constants

| Constant Set | Purpose | Key Values |
| :--- | :--- | :--- |
| **`TimeDefaults`** (`IntEnum`) | Defines default values and validation bounds for time-based fields. | `SIMULATION_TIME = 3600 s`, `MIN_SIMULATION_TIME = 1800 s`, `USER_SAMPLING_WINDOW = 60 s`, `MIN_USER_SAMPLING_WINDOW = 1 s`, `MAX_USER_SAMPLING_WINDOW = 120 s` |
| **`Distribution`** (`StrEnum`) | Defines the canonical names of probability distributions supported by the generator. | `"poisson"`, `"normal"`, `"log_normal"`, `"exponential"` |

***Why use constants?***

*   **Consistency:** They are referenced by validators; changing a value in one place updates the entire validation tree.
*   **Safety:** They guarantee that a typo, such as `"Poisson"`, raises an error instead of silently failing or switching to an unintended default.

---

### 2. Random Variable Schema (`RVConfig`)

```python
class RVConfig(BaseModel):
    """class to configure random variables"""

    mean: float
    distribution: Distribution = Distribution.POISSON
    variance: float | None = None

    @field_validator("mean", mode="before")
    def ensure_mean_is_numeric(
        cls, # noqa: N805
        v: object,
        ) -> float:
        """Ensure `mean` is numeric, then coerce to float."""
        err_msg = "mean must be a number (int or float)"
        if not isinstance(v, (float, int)):
            raise ValueError(err_msg)  # noqa: TRY004
        return float(v)

    @model_validator(mode="after")  # type: ignore[arg-type]
    def default_variance(cls, model: "RVConfig") -> "RVConfig":  # noqa: N805
        """Set variance = mean when distribution == 'normal' and variance is missing."""
        if model.variance is None and model.distribution == Distribution.NORMAL:
            model.variance = model.mean
        return model

```

#### Validation Logic

| Check | Pydantic Hook | Rule |
| :--- | :--- | :--- |
| *Mean must be numeric* | `@field_validator("mean", before)` | Rejects strings and nulls; coerces `int` to `float`. |
| *Autofill variance* | `@model_validator(after)` | If `distribution == "normal"` **and** `variance` is not provided, sets `variance = mean`. |
| *Positivity enforcement* | `PositiveFloat` / `PositiveInt` | Pydantic's constrained types are used on fields like `mean` where negative values are invalid, rejecting them before business logic runs. |

> **Self-Consistency:** Every random draw in the simulation engine relies on a validated `RVConfig` instance. This avoids redundant checks and defensive code downstream.

---

### 3. Traffic-Generator Payload (`RqsGeneratorInput`)

| Field | Type | Validation Tied to Constants |
| :--- | :--- | :--- |
| `avg_active_users` | `RVConfig` | No extra constraints needed; the inner schema guarantees correctness. |
| `avg_request_per_minute_per_user` | `RVConfig` | Same as above. |
| `total_simulation_time` | `int` | `ge=TimeDefaults.MIN_SIMULATION_TIME`<br>default=`TimeDefaults.SIMULATION_TIME` |
| `user_sampling_window` | `int` | `ge=TimeDefaults.MIN_USER_SAMPLING_WINDOW`<br>`le=TimeDefaults.MAX_USER_SAMPLING_WINDOW`<br>default=`TimeDefaults.USER_SAMPLING_WINDOW` |

#### How the Generator Uses Each Field

The simulation evolves based on a simple, powerful loop:

1.  **Timeline Partitioning** (`user_sampling_window`): The simulation timeline is divided into fixed-length windows. For each window:
2.  **Active User Sampling** (`avg_active_users`): A single value is drawn to determine the concurrent user population, `U(t)`, for that window.
3.  **Request Rate Calculation** (`avg_request_per_minute_per_user`): Each of the `U(t)` users contributes to the total request rate, yielding an aggregate load for the window.
4.  **Termination** (`total_simulation_time`): The loop stops once the cumulative simulated time reaches this value.

Because every numeric input is range-checked upfront, **the runtime engine never needs to defend itself** against invalid data like zero-length windows or negative rates, making the event-loop lean and predictable.

---

### 4. End-to-End Example (Fully Explicit)

```json
{
  "avg_active_users": {
    "mean": 100,
    "distribution": "poisson"
  },
  "avg_request_per_minute_per_user": {
    "mean": 4.0,
    "distribution": "normal",
    "variance": null
  },
  "total_simulation_time": 5400,
  "user_sampling_window": 45
}```

#### What the Validators Do

1. `mean` is numeric ✔️
2. `distribution` string matches an enum member ✔️
3. `total_simulation_time` ≥ 1800 ✔️
4. `user_sampling_window` is in the range ✔️
5. `variance` is `null` with a `normal` distribution ⇒ **auto-set to 4.0** ✔️

The payload is accepted. The simulator will run for $5400 / 45 = 120$ simulation windows.

---

### 5. Common Error Example

```json
{
  "avg_active_users": { "mean": "many" },
  "avg_request_per_minute_per_user": { "mean": -2 },
  "total_simulation_time": 600,
  "user_sampling_window": 400
}
```

| # | Fails On | Error Message (Abridged) |
| :- | :--- | :--- |
| 1 | Numeric check | `Input should be a valid number` |
| 2 | Positivity check | `Input should be greater than 0` |
| 3 | Minimum time check | `Input should be at least 1800` |
| 4 | Maximum window check | `Input should be at most 120` |

---

### Takeaways

*   **Single Source of Truth:** Enums centralize all literal values, eliminating magic strings.
*   **Layered Validation:** The `Constants → RVConfig → Request Payload` hierarchy ensures that only well-formed traffic profiles reach the simulation engine.
*   **Safe Defaults:** Omitting optional fields never leads to undefined behavior; defaults are sourced directly from the `TimeDefaults` constants.

This robust, layered approach allows you to configure the generator with confidence, knowing that any malformed scenario will be rejected early with explicit, actionable error messages.


### **FastSim Topology Input Schema**

The topology schema is the blueprint of the digital twin, defining the structure, resources, behavior, and network connections of the system you wish to simulate. It describes:

1.  **What work** each request performs (`Endpoint` → `Step`).
2.  **What components** exist in the system (`Server`, `Client`).
3.  **Which resources** each component possesses (`ServerResources`).
4.  **How** components are interconnected (`Edge`).

To ensure simulation integrity and prevent runtime errors, FastSim uses Pydantic to rigorously validate the entire topology upfront. Every inconsistency is rejected at load-time. The following sections detail the schema's layered design, from the most granular operation to the complete system graph.

---
### **A Controlled Vocabulary: The Role of Constants**

To ensure that input configurations are unambiguous and robust, the topology schema is built upon a controlled vocabulary defined by a series of Python `Enum` classes. Instead of relying on raw strings or "magic values" (e.g., `"cpu_bound_operation"`), which are prone to typos and inconsistencies, the schema uses these enumerations to define the finite set of legal values for categories like operation kinds, metrics, and node types.

This design choice provides three critical benefits:

1.  **Strong Type-Safety:** By using `StrEnum` and `IntEnum`, Pydantic models can validate input payloads with absolute certainty. Any value not explicitly defined in the corresponding `Enum` is immediately rejected. This prevents subtle configuration errors that would be difficult to debug at simulation time.
2.  **Developer Experience and Error Prevention:** This approach provides powerful auto-completion and static analysis. IDEs, `mypy`, and linters can catch invalid values during development, providing immediate feedback long before the code is executed.
3.  **Single Source of Truth:** All valid categories are centralized in the `app.config.constants` module. This makes the system easier to maintain and extend. To add a new resource type or metric, a developer only needs to update the `Enum` definition, and the change propagates consistently to validation logic, the simulation engine, and any other component that uses it.

The key enumerations that govern the topology schema include:

| Constant Enum | Purpose |
| :--- | :--- |
| **`EndpointStepIO`, `EndpointStepCPU`, `EndpointStepRAM`** | Define the exhaustive list of valid `kind` values for a `Step`. |
| **`Metrics`** | Specify the legal dictionary keys within a `Step`'s `step_metrics`, enforcing the one-to-one link between a `kind` and its metric. |
| **`SystemNodes` and `SystemEdges`** | Enumerate the allowed categories for nodes and their connections in the high-level `TopologyGraph`. |

### **Design Philosophy: A "Micro-to-Macro" Approach**

The schema is built on a compositional, "micro-to-macro" principle. We start by defining the smallest indivisible units of work (`Step`) and progressively assemble them into larger, more complex structures (`Endpoint`, `Server`, and finally the `TopologyGraph`).

This layered approach provides several key advantages:
*   **Modularity and Reusability:** An `Endpoint` is just a sequence of `Steps`. You can reorder, add, or remove steps without redefining the core operations themselves.
*   **Local Reasoning, Global Safety:** Each model is responsible for its own internal consistency (e.g., a `Step` ensures its metric is valid for its kind). Parent models then enforce the integrity of the connections *between* these components (e.g., the `TopologyGraph` ensures all `Edges` connect to valid `Nodes`).
*   **Clarity and Maintainability:** The hierarchy makes the system description intuitive to read and write. It’s clear how atomic operations roll up into endpoints, which are hosted on servers connected by a network.
*   **Robustness:** All structural and referential errors are caught before the simulation begins, guaranteeing that the SimPy engine operates on a valid, self-consistent model.

---

### **1. The Atomic Unit: `Step`**

A `Step` represents a single, indivisible operation executed by an asynchronous coroutine within an endpoint. It is the fundamental building block of all work in the simulation.

Each `Step` has a `kind` (the category of work) and `step_metrics` (the resources it consumes).

```python
class Step(BaseModel):
    """
    A single, indivisible operation.
    It must be quantified by exactly ONE metric.
    """
    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_metrics: dict[Metrics, PositiveFloat | PositiveInt]

    @model_validator(mode="after")
    def ensure_coherence_kind_metrics(cls, model: "Step") -> "Step":
        metrics_keys = set(model.step_metrics)

        # Enforce that a step performs one and only one type of work.
        if len(metrics_keys) != 1:
            raise ValueError("step_metrics must contain exactly one entry")

        # Enforce that the metric is appropriate for the kind of work.
        if isinstance(model.kind, EndpointStepCPU):
            if metrics_keys != {Metrics.CPU_TIME}:
                raise ValueError(f"CPU step requires metric '{Metrics.CPU_TIME}'")

        elif isinstance(model.kind, EndpointStepRAM):
            if metrics_keys != {Metrics.NECESSARY_RAM}:
                raise ValueError(f"RAM step requires metric '{Metrics.NECESSARY_RAM}'")

        elif isinstance(model.kind, EndpointStepIO):
            if metrics_keys != {Metrics.IO_WAITING_TIME}:
                raise ValueError(f"I/O step requires metric '{Metrics.IO_WAITING_TIME}'")

        return model
```

> **Design Rationale:** The strict one-to-one mapping between a `Step` and a single metric is a core design choice. It simplifies the simulation engine immensely, as each `Step` can be deterministically routed to a request on a single SimPy resource (a CPU queue, a RAM container, or an I/O event). This avoids the complexity of modeling operations that simultaneously consume multiple resource types.

---

### **2. Composing Workflows: `Endpoint`**

An `Endpoint` defines a complete, user-facing operation (e.g., an API call like `/predict`) as an ordered sequence of `Steps`.

```python
class Endpoint(BaseModel):
    """A higher-level API call, executed as a strict sequence of steps."""
    endpoint_name: str
    steps: list[Step]

    @field_validator("endpoint_name", mode="before")
    def name_to_lower(cls, v: str) -> str:
        """Standardize endpoint name to be lowercase for consistency."""
        return v.lower()
```

> **Design Rationale:** The simulation processes the `steps` list in the exact order provided. The total latency and resource consumption of an endpoint call is the sequential sum of its individual `Step` delays. This directly models the execution flow of a typical web request handler.

---

### **3. Defining Components: System Nodes**

Nodes are the macro-components of your architecture where work is performed and resources are located.

#### **`ServerResources` and `Server`**
A `Server` node hosts endpoints and owns a set of physical resources. These resources are mapped directly to specific SimPy primitives, which govern how requests queue and contend for service.

```python
class ServerResources(BaseModel):
    """Quantifiable resources available on a server node."""
    cpu_cores: PositiveInt = Field(ge=ServerResourcesDefaults.MINIMUM_CPU_CORES)
    ram_mb: PositiveInt = Field(ge=ServerResourcesDefaults.MINIMUM_RAM_MB)
    db_connection_pool: PositiveInt | None = None

class Server(BaseModel):
    """A node that hosts endpoints and owns resources."""
    id: str
    type: SystemNodes = SystemNodes.SERVER
    server_resources: ServerResources
    endpoints: list[Endpoint]
```

> **Design Rationale: Mapping to SimPy Primitives**
> *   `cpu_cores` maps to a `simpy.Resource`. This models a classic semaphore where only `N` processes can execute concurrently, and others must wait in a queue. It perfectly represents CPU-bound tasks competing for a limited number of cores.
> *   `ram_mb` maps to a `simpy.Container`. A container models a divisible resource where processes can request and return variable amounts. This is ideal for memory, as multiple requests can simultaneously hold different amounts of RAM without exclusively locking the entire memory pool.

#### **`Client`**
The `Client` is a special, resource-less node that serves as the origin point for all requests generated during the simulation.

#### **Node Aggregation and Validation (`TopologyNodes`)**
All `Server` and `Client` nodes are collected in the `TopologyNodes` model, which performs a critical validation check: ensuring all component IDs are unique across the entire system.

---

### **4. Connecting the Components: `Edge`**

An `Edge` represents a directed network link between two nodes, defining how requests flow through the system.

```python
class Edge(BaseModel):
    """A directed connection in the topology graph."""
    source: str
    target: str
    latency: RVConfig
    probability: float = Field(1.0, ge=0.0, le=1.0)
    edge_type: SystemEdges = SystemEdges.NETWORK_CONNECTION
```

> **Design Rationale:**
> *   **Stochastic Latency:** Latency is not a fixed number but an `RVConfig` object. This allows you to model realistic network conditions using various probability distributions (e.g., log-normal for internet RTTs, exponential for failure retries), making the simulation far more accurate.
> *   **Probabilistic Routing:** The `probability` field enables modeling of simple load balancing or A/B testing scenarios where traffic from a single `source` can be split across multiple `target` nodes.

---

### **5. The Complete System: `TopologyGraph`**

The `TopologyGraph` is the root of the configuration. It aggregates all `nodes` and `edges` and performs the final, most critical validation: ensuring referential integrity.

```python
class TopologyGraph(BaseModel):
    """The complete system definition, uniting all nodes and edges."""
    nodes: TopologyNodes
    edges: list[Edge]

    @model_validator(mode="after")
    def edge_refs_valid(cls, model: "TopologyGraph") -> "TopologyGraph":
        """Ensure every edge connects two valid, existing nodes."""
        valid_ids = {s.id for s in model.nodes.servers} | {model.nodes.client.id}
        for e in model.edges:
            if e.source not in valid_ids or e.target not in valid_ids:
                raise ValueError(f"Edge '{e.source}->{e.target}' references an unknown node.")
        return model
```
> **Design Rationale:** This final check guarantees that the topology is a valid, connected graph. By confirming that every `edge.source` and `edge.target` corresponds to a defined node `id`, it prevents the simulation from starting with a broken or nonsensical configuration, embodying the "fail-fast" principle.

---

### **End-to-End Example**

Here is a minimal, complete JSON configuration that defines a single client and a single API server.

```jsonc
{
  "nodes": {
    // The client node is the source of all generated requests.
    "client": {
      "id": "user_browser",
      "type": "client"
    },
    // A list of all server nodes in the system.
    "servers": [
      {
        "id": "api_server_node",
        "type": "server",
        "server_resources": {
          "cpu_cores": 2,
          "ram_mb": 2048
        },
        "endpoints": [
          {
            "endpoint_name": "/predict",
            "steps": [
              {
                "kind": "initial_parsing",
                "step_metrics": { "cpu_time": 0.005 }
              },
              {
                "kind": "io_db",
                "step_metrics": { "io_waiting_time": 0.050 }
              },
              {
                "kind": "cpu_bound_operation",
                "step_metrics": { "cpu_time": 0.015 }
              }
            ]
          }
        ]
      }
    ]
  },
  "edges": [
    // A network link from the client to the API server.
    {
      "source": "user_browser",
      "target": "api_server_node",
      "latency": {
        "distribution": "log_normal",
        "mean": 0.05,
        "std_dev": 0.01
      },
      "probability": 1.0
    }
  ]
}```




> **YAML friendly:**  
> The topology schema is 100 % agnostic to the wire format.  
> You can encode the same structure in **YAML** with identical field
> names and value types—Pydantic will parse either JSON or YAML as long
> as the keys and data types respect the schema.  
> No additional changes or converters are required.
```



### **Key Takeaway**

This rigorously validated, compositional schema is the foundation of FastSim's reliability. By defining a clear vocabulary of constants (`Metrics`, `SystemNodes`) and enforcing relationships with Pydantic validators, the schema guarantees that every simulation run starts from a **complete and self-consistent** system description. This allows you to refactor simulation logic or extend the model with new resources (e.g., GPU memory) with full confidence that existing configurations remain valid and robust.