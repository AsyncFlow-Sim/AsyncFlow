Of course. This is an excellent request. A deep dive into the "why" and the real-world analogies is what makes documentation truly valuable.

Here is the comprehensive, detailed documentation for the FastSim Runtime Layer, written in English, incorporating all your requests.

-----

# **FastSim — The Runtime Layer Documentation**

*(Version July 2025 – Aligned with `app/runtime` and `app/resources`)*

## **1. The Runtime Philosophy: From Blueprint to Living System**

If the `SimulationPayload` is the static **blueprint** of a system, the `runtime` package is the **engine** that brings that blueprint to life. It translates a validated, declarative configuration into a dynamic, interacting set of processes within a SimPy simulation environment. The entire design is guided by a few core principles to ensure robustness, testability, and a faithful reflection of real-world systems.

### **The Actor Model & Process Management**

Distributed systems are, by nature, composed of independent components that communicate with each other concurrently. To model this, we've adopted an **Actor Model**. Each major component of the architecture (`Generator`, `Server`, `Client`) is implemented as an "Actor"—a self-contained object with its own internal state and behavior that communicates with other actors by sending and receiving messages (`RequestState` objects).

SimPy's process management is a perfect fit for this model. It uses **cooperative multitasking** within a single-threaded event loop. An actor "runs" until it `yield`s control to the SimPy environment, typically to wait for a duration (`timeout`), a resource (`Container.get`), or an event (`Store.get`). This elegantly mimics modern, non-blocking I/O frameworks (like Python's `asyncio`, Node.js, or Go's goroutines) where a process performs work until it hits an I/O-bound operation, at which point it yields control, allowing the event loop to run other ready tasks.

### **The "Validation-First" Contract**

A crucial design decision is the strict separation between configuration and execution. The `runtime` layer operates under the assumption that the input `SimulationPayload` is **100% valid and logically consistent**. This "validation-first" contract means the runtime code is streamlined and free of defensive checks. It doesn't need to validate if a server ID exists or if a resource is defined; it can focus entirely on its core responsibility: accurately modeling the passage of time and contention for resources.

-----

## **2. High-Level Architecture & Data Flow**

The simulation is a choreography of Actors passing a `RequestState` object between them. Communication and resource access are mediated exclusively by the SimPy environment, ensuring all interactions are captured on the simulation timeline.

```text
               .start()        .transport(state)         .start()
┌───────────┐  Starts  ┌───────────┐   Forwards   ┌───────────┐  Processes  ┌───────────┐
│           ├─────────►│           ├─────────────►│           ├────────────►│           │
│ Generator │          │   Edge    │              │  Server   │             │   Client  │
│           ◄─────────┤           ◄─────────────┤           ◄────────────┤           │
└───────────┘          └───────────┘              └───────────┘              └───────────┘
   ▲ Creates          ▲ Delays RequestState        ▲ Consumes                  ▲ Finishes
   │ RequestState     │ (Latency & Drops)        │ Resources                 │ Request
```

  * **Actors** (`runtime/actors/`): The active, stateful processes that perform work (`RqsGeneratorRuntime`, `ServerRuntime`, `ClientRuntime`, `EdgeRuntime`).
  * **State Object** (`RequestState`): The message passed between actors. It acts as a digital passport, collecting stamps (`Hop` objects) at every stage of its journey.
  * **Resource Registry** (`resources/`): A central authority that creates and allocates finite system resources (CPU cores, RAM) to the actors that need them.

-----

## **3. The Anatomy of a Request: State & History**

At the heart of the simulation is the `RequestState` object, which represents a single user request flowing through the system.

### **3.1. `Hop` – The Immutable Breadcrumb**

A `Hop` is a `NamedTuple` that records a single, atomic event in a request's lifecycle: its arrival at a specific component at a specific time. Being an immutable `NamedTuple` makes it lightweight and safe to use in analysis.

### **3.2. `RequestState` – The Digital Passport**

```python
@dataclass
class RequestState:
    id: int
    initial_time: float
    finish_time: float | None = None
    history: list[Hop] = field(default_factory=list)
```

This mutable dataclass is the sole carrier of a request's identity and history.

  * `id`: A unique identifier for the request, assigned by the generator.
  * `initial_time`: The simulation timestamp (`env.now`) when the request was created.
  * `finish_time`: The timestamp when the request completes its lifecycle. It remains `None` until then.
  * `history`: A chronologically ordered list of `Hop` objects, creating a complete, traceable path of the request's journey.

#### **Real-World Analogy**

Think of `RequestState` as a request context in a modern microservices architecture. The `id` is analogous to a **Trace ID** (like from OpenTelemetry or Jaeger). The `history` of `Hop` objects is the collection of **spans** associated with that trace, providing a detailed, end-to-end view of where the request spent its time, which is invaluable for performance analysis and debugging.

-----

## **4  The Resource Layer — Modelling Contention ⚙️**

In real infrastructures every machine has a hard ceiling: only *N* CPU cores, only *M* MB of RAM.
FastSim mirrors that physical constraint through the **Resource layer**, which exposes pre-filled SimPy containers that actors must draw from. If a token is not available the coroutine simply blocks — giving you back-pressure “for free”.

---

### **4.1  `ResourcesRuntime` — The Central Bank of Resources**

| Responsibility        | Implementation detail                                                                                                                                                                                            |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Discover capacity** | Walks the *validated* `TopologyGraph.nodes.servers`, reading `cpu_cores` and `ram_mb` from each `ServerResources` spec.                                                                                          |
| **Mint containers**   | Calls `build_containers(env, spec)` which returns<br>`{"CPU": simpy.Container(init=cpu_cores), "RAM": simpy.Container(init=ram_mb)}` — the containers start **full** so a server can immediately consume tokens. |
| **Registry map**      | Stores them in a private dict `_by_server: dict[str, ServerContainers]`.                                                                                                                                         |
| **Public API**        | `registry[server_id] → ServerContainers` (raises `KeyError` if the ID is unknown).                                                                                                                               |

```python
registry = ResourcesRuntime(env, topology)
cpu_bucket = registry["srv-1"]["CPU"]     # simpy.Container, level == capacity at t=0
ram_bucket = registry["srv-1"]["RAM"]
```

Because the schema guarantees that every `server_id` is unique and every
server referenced in an edge actually exists, `ResourcesRuntime` never needs
defensive checks beyond the simple dictionary lookup.

---

### **4.2  How Contention Emerges**

* **CPU** – Each `yield CPU.get(1)` represents “claiming one core”.
  When all tokens are gone the coroutine waits, modelling a thread-pool or worker saturation.
* **RAM** – `yield RAM.get(amount)` blocks until enough memory is free.
  Large requests can starve, reproducing OOM throttling or JVM heap pressure.
* **Automatic fairness** – SimPy’s event loop resumes whichever coroutine became ready first, giving a natural first-come, first-served order.

> **No bespoke semaphore or queueing code is required** — the SimPy
> containers *are* the semaphore.

---

### **Real-World Analogy**

| Runtime Component    | Real Infrastructure Counterpart                                                                           |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| `ResourcesRuntime`   | A **cloud provider control plane** or **Kubernetes scheduler**: single source of truth for node capacity. |
| CPU container tokens | **Worker threads / processes** in Gunicorn, uWSGI, or an OS CPU-quota.                                    |
| RAM container tokens | **cgroup memory limit** or a pod’s allocatable memory; once exhausted new workloads must wait.            |

Just like a Kubernetes scheduler won’t place a pod if a node lacks free CPU/RAM,
FastSim won’t let an actor proceed until it obtains the necessary tokens.

## **5. The Actors: Bringing the System to Life**

Actors are the core drivers of the simulation. Each represents a key component of the system architecture. They all expose a consistent `.start()` method, which registers their primary behavior as a process with the SimPy environment, allowing for clean and uniform orchestration.

### **5.1. RqsGeneratorRuntime: The Source of Load**

This actor's sole purpose is to create `RequestState` objects according to a specified stochastic model, initiating all traffic in the system.

| Key Parameter (`__init__`) | Meaning |
| :--- | :--- |
| `env` | The SimPy simulation environment. |
| `out_edge` | The `EdgeRuntime` instance to which newly created requests are immediately sent. |
| `rqs_generator_data` | The validated Pydantic schema containing the statistical model for traffic (e.g., user count, request rate). |
| `rng` | A NumPy random number generator instance for deterministic, reproducible randomness. |

**Core Logic (`.start()`):**
The generator's main process uses a statistical sampler (e.g., `poisson_poisson_sampling`) to yield a series of inter-arrival time gaps. It waits for each gap (`yield self.env.timeout(gap)`), then creates a new `RequestState`, records its first `Hop`, and immediately forwards it to the outbound edge via `out_edge.transport()`.

**Real-World Analogy:**
The `RqsGeneratorRuntime` represents the collective behavior of your entire user base or the output of an upstream service. It's equivalent to a **load-testing tool** like **k6, Locust, or JMeter**, configured to simulate a specific traffic pattern (e.g., 500 users with an average of 30 requests per minute).

-----

### **5.2. EdgeRuntime: The Network Fabric 🚚**

This actor models the connection *between* two nodes. It simulates the two most important factors of network transit: latency and unreliability.

| Key Parameter (`__init__`) | Meaning |
| :--- | :--- |
| `env` | The SimPy simulation environment. |
| `edge_config` | The Pydantic `Edge` model containing this link's configuration (latency distribution, dropout rate). |
| `target_box` | A `simpy.Store` that acts as the "inbox" for the destination node. |
| `rng` | The random number generator for sampling latency and dropout. |

**Core Logic (`.transport()`):**
Unlike other actors, `EdgeRuntime`'s primary method is `.transport(state)`. When called, it doesn't block the caller. Instead, it spawns a new, temporary SimPy process (`_deliver`) for that specific `RequestState`. This process:

1.  Checks for a **dropout** (packet loss) based on `dropout_rate`. If dropped, the request's `finish_time` is set, and its journey ends.
2.  If not dropped, it samples a **latency** value from the configured probability distribution.
3.  It `yield`s a `timeout` for the sampled latency, simulating network travel time.
4.  After the wait, it records a successful `Hop` and places the `RequestState` into the `target_box` of the destination node.

**Real-World Analogy:**
An `EdgeRuntime` is a direct analog for a **physical or virtual network link**. This could be the public **internet** between a user and your server, a **LAN connection** between two services in a data center, or a **VPC link** between two cloud resources. `latency` represents round-trip time (RTT), and `dropout_rate` models packet loss.

-----

### **5.3  `ServerRuntime` — The Workhorse 📦 (2025 edition)**

`ServerRuntime` emulates an application server that owns **finite CPU / RAM containers** and executes an ordered chain of **Step** objects for every incoming request.
The 2025 refactor keeps the classic **dispatcher / handler** pattern, adds **live metric counters** (ready‑queue length, I/O‑queue length, RAM‑in‑use) and implements the **lazy‑CPU lock** algorithm described earlier.

| `__init__` parameter   | Meaning                                                                                                                                                               |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`env`**              | Shared `simpy.Environment`. Every timeout or resource operation is scheduled here.                                                                                    |
| **`server_resources`** | A `ServerContainers` mapping `{"CPU": Container, "RAM": Container}` created by `ResourcesRuntime`. Containers start **full** so a server can immediately pull tokens. |
| **`server_config`**    | Validated Pydantic `Server` model: ID, resource spec, list `endpoints: list[Endpoint]`.                                                                               |
| **`out_edge`**         | `EdgeRuntime` (or stub) that receives the `RequestState` once processing finishes.                                                                                    |
| **`server_box`**       | `simpy.Store` acting as the server’s inbox. Up‑stream actors drop `RequestState`s here.                                                                               |
| **`rng`**              | `numpy.random.Generator`; defaults to `default_rng()`. Used to pick a random endpoint.                                                                                |

---

#### **Live metric fields**

| Field                 | Unit     | Updated when…                                    | Used for…                                                                |
| --------------------- | -------- | ------------------------------------------------ | ------------------------------------------------------------------------ |
| `_el_ready_queue_len` | requests | a CPU step acquires / releases a core            | **Ready queue length** (how many coroutines wait for the GIL / a worker) |
| `_el_io_queue_len`    | requests | an I/O step enters / leaves the socket wait list | **I/O queue length** (awaits in progress)                                |
| `_ram_in_use`         | MB       | RAM `get` / `put`                                | Instant **RAM usage** per server                                         |

Accessor properties expose them read‑only:

```python
@property
def ready_queue_len(self) -> int: return self._el_ready_queue_len

@property
def io_queue_len(self) -> int: return self._el_io_queue_len

@property
def ram_in_use(self) -> int: return self._ram_in_use
```

---

#### **Public API**

```python
def start(self) -> simpy.Process
```

Registers the **dispatcher** coroutine in the environment and returns the created `Process`.

---

#### **Internal Workflow**

```text
┌───────────┐   server_box.get()     ┌──────────────┐
│ dispatcher │ ────────────────────► │ handle_req N │
└───────────┘   spawn new process    └──────────────┘
                        │
                        ▼
            RAM get → CPU/IO steps → RAM put → out_edge.transport()
                      ▲        │
                      │        └── metric counters updated here
                      └── lazy CPU lock (get once, put on first I/O)
```

1. **Dispatcher loop**

```python
while True:
    raw_state = yield self.server_box.get()           # blocks until a request arrives
    state = cast(RequestState, raw_state)
    self.env.process(self._handle_request(state))     # fire‑and‑forget
```

2. **Handler coroutine (`_handle_request`)**

| Stage                           | Implementation detail                                                                     |
| ------------------------------- | ----------------------------------------------------------------------------------------- |
| **Record arrival**              | `state.record_hop(SystemNodes.SERVER, self.server_config.id, env.now)`                    |
| **Endpoint selection**          | Uniform random index `rng.integers(0, len(endpoints))` (plug‑in point for custom routing) |
| **Reserve RAM (back‑pressure)** | compute `total_ram` → `yield RAM.get(total_ram)` → `_ram_in_use += total_ram`             |
| **Execute steps**               | handled in a loop with *lazy CPU lock* and metric updates (see edge‑case notes below)     |
| **Release RAM**                 | `_ram_in_use -= total_ram` → `yield RAM.put(total_ram)`                                   |
| **Forward**                     | `out_edge.transport(state)` — send to next hop without awaiting latency                   |

---

#### **CPU / I‑O loop details**

* **Lazy‑CPU lock** – first CPU step acquires one core; all following contiguous CPU steps reuse it.
* **Release on I/O** – on the first I/O step the core is released; it remains free until the next CPU step.
* **Metric updates** – counters are modified only on the **state transition** (CPU→I/O, I/O→CPU) so there is never double‑counting.

```python
if isinstance(step.kind, EndpointStepCPU):
    if not core_locked:
        yield CPU.get(1)
        core_locked = True
        self._el_ready_queue_len += 1        # entered ready queue
        if is_in_io_queue:
            self._el_io_queue_len -= 1
            is_in_io_queue = False
    yield env.timeout(cpu_time)

elif isinstance(step.kind, EndpointStepIO):
    if core_locked:
        yield CPU.put(1)
        core_locked = False
        self._el_ready_queue_len -= 1
    if not is_in_io_queue:
        self._el_io_queue_len += 1
        is_in_io_queue = True
    yield env.timeout(io_time)
```

**Handler epilogue**

```python
# at exit, remove ourselves from whichever queue we are in
if core_locked:           # we are still in ready queue
    self._el_ready_queue_len -= 1
    yield CPU.put(1)
elif is_in_io_queue:      # finished while awaiting I/O
    self._el_io_queue_len -= 1
```

> This guarantees both queues always balance back to 0 after the last request completes.

---

#### **Concurrency Guarantees**

* **CPU contention** – the `CPU` container is a token bucket; max concurrent CPU‑bound steps = `cpu_cores`.
* **RAM contention** – requests block at `RAM.get()` until memory is free (models cgroup / OOM throttling).
* **Non‑blocking I/O** – while in `env.timeout(io_wait)` no core token is held, so other handlers can run; mirrors an async server where workers return to the event‑loop on each `await`.

---

#### **Edge‑case handling (metrics)**

* **First‑step I/O** – counted only in I/O queue (`+1`), never touches ready queue.
* **Consecutive I/O steps** – second I/O sees `is_in_io_queue == True`, so no extra increment (no double count).
* **CPU → I/O → CPU** –
   – CPU step: `core_locked=True`, `+1` ready queue
   – I/O step: core released, `‑1` ready queue, `+1` I/O queue
   – next CPU: core reacquired, `‑1` I/O queue, `+1` ready queue
* **Endpoint finishes** – epilogue removes the request from whichever queue it still occupies, avoiding “ghost” entries.

---

#### **Real‑World Analogy**

| Runtime concept                         | Real server analogue                                                                    |
| --------------------------------------- | --------------------------------------------------------------------------------------- |
| `server_box`                            | Web server accept queue (e.g., `accept()` backlog).                                     |
| `CPU.get(1)` / `CPU.put(1)`             | Claiming / releasing a worker thread or GIL slot (Gunicorn, uWSGI, Node.js event‑loop). |
| `env.timeout(io_wait)` (without a core) | `await redis.get()` – coroutine parked while the kernel handles the socket.             |
| RAM token bucket                        | cgroup memory limit / container hard‑RSS; requests block when heap is exhausted.        |

Thus a **CPU‑bound step** models tight Python code holding the GIL, while an **I/O‑bound step** models an `await` that yields control back to the event loop, freeing the core.

---



### **5.4. ClientRuntime: The Destination**

This actor typically represents the end-user or system that initiated the request, serving as the final destination.

| Key Parameter (`__init__`) | Meaning |
| :--- | :--- |
| `env` | The SimPy simulation environment. |
| `out_edge` | The `EdgeRuntime` to use if the client needs to forward the request (acting as a relay). |
| `client_box` | This client's "inbox". |
| `completed_box` | A global `simpy.Store` where all finished requests are placed for final collection and analysis. |

**Core Logic (`.start()`):**
The client pulls requests from its `client_box`. It then makes a critical decision:

  * **If the request is new** (coming directly from the `RqsGeneratorRuntime`), it acts as a **relay**, immediately forwarding the request to its `out_edge`.
  * **If the request is returning** (coming from a `ServerRuntime`), it acts as the **terminus**. It sets the request's `finish_time`, completing its lifecycle, and puts it into the global `completed_box`.

**Design Note & Real-World Analogy:**
The current logic for this decision—`if state.history[-2].component_type != SystemNodes.GENERATOR`—is **fragile**. While it works, it's not robust. A future improvement would be to add a more explicit routing mechanism.
In the real world, the `ClientRuntime` could be a user's **web browser**, a **mobile application**, or even a **Backend-For-Frontend (BFF)** service that both initiates requests and receives the final aggregated responses.

## **5.5  `LoadBalancerRuntime` — The Traffic Cop 🚦**

The **Load Balancer** actor lives in `app/runtime/actors/load_balancer_runtime.py`.
It receives a `RequestState` from the client side, decides **which outbound
edge** should carry it to a server, and immediately forwards the request.

```text
lb_box.get()            choose edge                transport(state)
┌───────────────┐  ───────────────────────────►  ┌────────────────┐
│ LoadBalancer  │                                │ EdgeRuntime n  │
└───────────────┘  ◄───────────────────────────┘ └────────────────┘
```

### **Constructor Parameters**

| Parameter     | Meaning                                                                 |
| ------------- | ----------------------------------------------------------------------- |
| `env`         | Shared `simpy.Environment`                                              |
| `lb_config`   | Validated `LoadBalancer` schema (ID, chosen algorithm enum)             |
| `outer_edges` | Immutable list `list[EdgeRuntime]`, one per target server               |
| `lb_box`      | `simpy.Store` acting as the inbox for requests arriving from the client |

```python
self._round_robin_index: int = 0   # round-robin pointer (private state)
```

### **Supported Algorithms**

| Enum value (`LbAlgorithmsName`) | Function used                                 | Signature |
| ------------------------------- | --------------------------------------------- | --------- |
| `ROUND_ROBIN`                   | `round_robin(edges, idx)` → `(edge, new_idx)` | O(1)      |
| `LEAST_CONNECTIONS`             | `least_connections(edges)` → `edge`           | O(N) scan |

*Both helpers live in* `app/runtime/actors/helpers/lb_algorithms.py`.

#### **Why an index and not list rotation?**

`outer_edges` is **shared** with other components (e.g. metrics collector,
tests). Rotating it in-place would mutate a shared object and create
hard-to-trace bugs (aliasing).
Keeping `_round_robin_index` inside the LB runtime preserves immutability while
still advancing the pointer on every request.

### **Process Workflow**

```python
def _forwarder(self) -> Generator[simpy.Event, None, None]:
    while True:
        state: RequestState = yield self.lb_box.get()     # ① wait for a request

        state.record_hop(SystemNodes.LOAD_BALANCER,
                         self.lb_config.id,
                         self.env.now)                    # ② trace

        if self.lb_config.algorithms is LbAlgorithmsName.ROUND_ROBIN:
            edge, self._round_robin_index = round_robin(
                self.outer_edges,
                self._round_robin_index,
            )                                             # ③a choose RR edge
        else:                                             # LEAST_CONNECTIONS
            edge = least_connections(self.outer_edges)    # ③b choose LC edge

        edge.transport(state)                             # ④ forward
```

| Step | What happens                                                             | Real-world analogue                      |
| ---- | ------------------------------------------------------------------------ | ---------------------------------------- |
| ①    | Pull next `RequestState` out of `lb_box`.                                | Socket `accept()` on the LB front-end.   |
| ②    | Add a `Hop` stamped `LOAD_BALANCER`.                                     | Trace span in NGINX/Envoy access log.    |
| ③a   | **Round-Robin** – pick `outer_edges[_round_robin_index]`, advance index. | Classic DNS-RR or NGINX default.         |
| ③b   | **Least-Connections** – `min(edges, key=concurrent_connections)`.        | HAProxy `leastconn`, NGINX `least_conn`. |
| ④    | Spawn network transit via `EdgeRuntime.transport()`.                     | LB writes request to backend socket.     |

### **Edge-Case Safety**

* **Empty `outer_edges`** → impossible by schema validation (LB must cover >1 server).
* **Single server** → RR degenerates to index 0; LC always returns that edge.
* **Concurrency metric** (`edge.concurrent_connections`) is updated inside
  `EdgeRuntime` in real time, so `least_connections` adapts instantly to load spikes.

### **Key Takeaways**

1. **Stateful but side-effect-free** – `_round_robin_index` keeps per-LB state without mutating the shared edge list.
2. **Uniform API** – both algorithms integrate through a simple `if/else`; additional strategies can be added with negligible changes.
3. **Deterministic & reproducible** – no randomness inside the LB, ensuring repeatable simulations.

With these mechanics the `LoadBalancerRuntime` faithfully emulates behaviour of
production LBs (NGINX, HAProxy, AWS ALB) while remaining lightweight and
fully deterministic inside the FastSim event loop.
