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


Of course. Here is the detailed documentation in English for the input schema of the request handler and system topology. This document explains the hierarchical structure, from the foundational constants to the complete topology graph, with code snippets and a full example.

---

### **Modeling the System: The Topology Schema**

This document details the input schema required to define the system topology for the FastSim simulator. The goal is to create a "digital twin" of your infrastructure, specifying its components, their connections, and the work they perform when handling a request.

The design is built on a **hierarchical validation contract**. Each layer of the configuration relies on the correctness of the layer below it, ensuring that only a valid, logically consistent system model reaches the simulation engine.

The structure is built from the bottom up:
1.  **Constants**: The single source of truth for all literal values.
2.  **Steps**: The atomic units of work (e.g., a CPU operation, a database call).
3.  **Endpoints**: A sequence of steps that defines a specific API behavior (e.g., `/predict`).
4.  **Nodes & Resources**: The system components (`Server`, `Client`) and their capabilities.
5.  **Edges**: The connections between nodes, with associated latencies.
6.  **Topology Graph**: The top-level object that combines all nodes and edges into a complete system.

---

### 1. The Foundation: Global Constants

We use Python's `Enum` and standard classes to define all static values. This prevents typos, centralizes configuration, and makes the code self-documenting.

| Constant Group | Purpose | Examples |
| :--- | :--- | :--- |
| **`Endpoint...`** | Defines the types of operations a step can perform (`EndpointIO`, `EndpointCPU`, `EndpointRAM`). | `"io_db"`, `"cpu_bound_operation"`, `"ram"` |
| **`MetricKeys`** | Defines the valid keys within a step's `metrics` dictionary. | `"cpu_time"`, `"necessary_ram"` |
| **`SystemNodes`** | Defines the valid types for a component in the topology graph. | `"server"`, `"client"`, `"database"` |
| **`SystemEdges`** | Defines the types of connections between nodes. | `"network_connection"` |
| **`ServerResourceDefaults`** | Provides default values and validation limits for server resources. | `CPU_CORES = 1`, `MINIMUM_RAM_MB = 256` |

Using these constants ensures that a configuration like `"kind": "io_database"` would fail validation because `"io_database"` is not a member of `EndpointIO`, preventing silent errors.

---

### 2. The Atomic Unit of Work: The `Step` Schema

A "step" is the smallest, indivisible operation that occurs within an endpoint. It represents a single action, like consuming CPU, waiting for a database, or allocating memory.

```python
class Step(BaseModel):
    """Full step structure for an endpoint operation."""
    kind: EndpointIO | EndpointCPU | EndpointRAM
    metrics: dict[MetricKeys, PositiveFloat | PositiveInt]
```

*   **`kind`**: A string that *must* be a valid member of one of the `Endpoint...` enums. It defines the *nature* of the operation.
*   **`metrics`**: A dictionary specifying the *magnitude* of the operation. The keys *must* be valid members of the `MetricKeys` enum.

**Example of a single step:** This JSON object represents a database call that consumes 0.05 seconds of CPU time.

```json
{
  "kind": "io_db",
  "metrics": {
    "cpu_time": 0.05
  }
}
```

> **Note:** #TODO A future enhancement, as noted in the source code, will add a validator to ensure the `metrics` provided are logically consistent with the `kind` (e.g., a `ram` step must provide a `necessary_ram` metric).

---

### 3. Service Behavior: The `Endpoint` Schema

An endpoint is a collection of steps, executed sequentially, that models a complete API call.

```python
class Endpoint(BaseModel):
    """A full endpoint composed of a sequence of steps."""
    endpoint_name: str
    steps: list[Step]
```

*   **`endpoint_name`**: The identifier for the endpoint, such as `/predict` or `/users`.
*   **`steps`**: An ordered list of `Step` objects.

**Example of an endpoint:** This endpoint first performs some initial CPU-bound parsing, then makes a database call.

```json
{
  "endpoint_name": "/predict",
  "steps": [
    {
      "kind": "initial_parsing",
      "metrics": {
        "cpu_time": 0.015
      }
    },
    {
      "kind": "io_db",
      "metrics": {
        "cpu_time": 0.05
      }
    }
  ]
}
```

---

### 4. System Components: Nodes and Resources

Nodes are the macro-components of your system architecture. The configuration currently supports two primary types: `Client` and `Server`.

#### Server Resources
First, we define a strict schema for a server's capabilities, using our `ServerResourceDefaults` for validation and defaults.

```python
class ServerResources(BaseModel):
    """Defines the quantifiable resources available on a server node."""
    cpu_cores: PositiveInt = Field(
        default=ServerResourceDefaults.CPU_CORES,
        ge=ServerResourceDefaults.MINIMUM_CPU_CORES,
        description="Number of CPU cores available for processing."
    )
    ram_mb: PositiveInt = Field(
        default=ServerResourceDefaults.RAM_MB,
        ge=ServerResourceDefaults.MINIMUM_RAM_MB, 
        description="Total available RAM in Megabytes."
    )
    db_connection_pool: PositiveInt | None = Field(
        default=ServerResourceDefaults.DB_CONNECTION_POOL,
        description="Size of the database connection pool, if applicable."
    )
```

#### Server
A `Server` node is a component that has resources and can service requests via its endpoints.

```python
class Server(BaseModel):
    """A server node in the system topology."""
    id: str
    type: SystemNodes = SystemNodes.SERVER
    server_resources: ServerResources
    endpoints: list[Endpoint]
```

*   **`id`**: A unique string identifier for the node (e.g., `"service-auth-v1"`).
*   **`type`**: Must be `"server"`, validated by the `SystemNodes` enum.
*   **`server_resources`**: An object conforming to the `ServerResources` schema.
*   **`endpoints`**: A list of `Endpoint` objects that this server exposes.

#### Client
The `Client` is a special, simplified node that represents the origin of all requests.

```python
class Client(BaseModel):
    """The client node, representing the origin of requests."""
    id: str
    type: SystemNodes = SystemNodes.CLIENT
```

---

### 5. System Connections: The `Edge` Schema

Edges define the directed connections between nodes, representing network paths, queues, or other links.

```python
class Edge(BaseModel):
    """A directed connection in the topology graph."""
    source: str
    target: str
    latency: RVConfig  # From the request-generator schema
    probability: float = Field(1.0, ge=0.0, le=1.0)
    edge_type: SystemEdges = SystemEdges.NETWORK_CONNECTION
```

*   **`source` / `target`**: The `id` strings of the two nodes being connected.
*   **`latency`**: A `RVConfig` object defining the network latency for this hop as a random variable. This allows for realistic modeling of network conditions.
*   **`probability`**: The chance (from 0.0 to 1.0) of a request taking this path when multiple edges leave the same `source`. This is key for modeling load balancing.

---

### 6. The Complete Picture: The `TopologyGraph`

This is the top-level object that assembles the entire system definition from the building blocks above.

```python
class TopologyGraph(BaseModel):
    """The complete system graph, containing all nodes and edges."""
    nodes: TopologyNodes
    edges: list[Edge]
```

This schema has powerful built-in validators that ensure:
1.  **Unique IDs**: Every node (`Server` or `Client`) in `nodes` has a unique `id`.
2.  **Referential Integrity**: Every `source` and `target` in the `edges` list corresponds to a valid node `id` defined in the `nodes` section. This prevents "dangling edges" that point to non-existent components.

---

### 7. Full Configuration Example

Here is a simple but complete and valid JSON configuration for a system with one client and one server.

```json
{
  "nodes": {
    "client": {
      "id": "web-browser-client",
      "type": "client"
    },
    "servers": [
      {
        "id": "main-api-server",
        "type": "server",
        "server_resources": {
          "cpu_cores": 4,
          "ram_mb": 2048
        },
        "endpoints": [
          {
            "endpoint_name": "/process_data",
            "steps": [
              {
                "kind": "initial_parsing",
                "metrics": {
                  "cpu_time": 0.02
                }
              },
              {
                "kind": "cpu_bound_operation",
                "metrics": {
                  "cpu_time": 0.150,
                  "necessary_ram": 128
                }
              }
            ]
          }
        ]
      }
    ]
  },
  "edges": [
    {
      "source": "web-browser-client",
      "target": "main-api-server",
      "latency": {
        "mean": 0.050,
        "distribution": "log_normal",
        "variance": 0.01
      },
      "probability": 1.0,
      "edge_type": "network_connection"
    }
  ]
}
```

This hierarchical, validated schema design guarantees that any configuration that passes validation is a sound and complete model, ready to be reliably used by the FastSim simulation engine.