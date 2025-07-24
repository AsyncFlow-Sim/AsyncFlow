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

### **5.3  `ServerRuntime` — The Workhorse 📦**

`ServerRuntime` models an application server that owns finite CPU/RAM resources and executes a chain of steps for every incoming request.
With the 2025 refactor it now uses a **dispatcher / handler** pattern: the dispatcher sits in an infinite loop, and each request is handled in its own SimPy subprocess. This enables many concurrent in-flight requests while keeping the code easy to reason about.

| `__init__` parameter   | Meaning                                                                                                                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`env`**              | The shared `simpy.Environment`. Every timeout and resource operation is scheduled here.                                                                                                                 |
| **`server_resources`** | A `ServerContainers` mapping (`{"CPU": Container, "RAM": Container}`) created by `ResourcesRuntime`. The containers are **pre-filled** (`level == capacity`) so the server can immediately pull tokens. |
| **`server_config`**    | The validated Pydantic `Server` model: server-wide ID, resource spec, and a list of `Endpoint` objects (each endpoint is an ordered list of `Step`s).                                                   |
| **`out_edge`**         | The `EdgeRuntime` (or stub) that receives the `RequestState` once processing finishes.                                                                                                                  |
| **`server_box`**       | A `simpy.Store` acting as the server’s inbox. Up-stream actors drop `RequestState`s here.                                                                                                               |
| **`rng`**              | Instance of `numpy.random.Generator`; defaults to `default_rng()`. Used to pick a random endpoint.                                                                                                      |

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
```

1. **Dispatcher loop**

   ```python
   while True:
       raw_state = yield self.server_box.get()          # blocks until a request arrives
       state = cast(RequestState, raw_state)
       self.env.process(self._handle_request(state))    # fire-and-forget
   ```

   *Spawning a new process per request mimics worker thread concurrency.*

2. **Handler coroutine (`_handle_request`)**

   | Stage                           | Implementation detail                                                                                                                                                          |
   | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
   | **Record arrival**              | `state.record_hop(SystemNodes.SERVER, self.server_config.id, env.now)` – leaves a breadcrumb for tracing.                                                                      |
   | **Endpoint selection**          | Uniform random index `rng.integers(0, len(endpoints))`. (Hook point for custom routing later.)                                                                                 |
   | **Reserve RAM (back-pressure)** | Compute `total_ram` (sum of all `StepOperation.NECESSARY_RAM`). `yield RAM.get(total_ram)`. If not enough RAM is free, the coroutine blocks, creating natural memory pressure. |
   | **Execute steps in order**      |                                                                                                                                                                                |
   | – CPU-bound step                | `yield CPU.get(1)` → `yield env.timeout(cpu_time)` → `yield CPU.put(1)` – exactly one core is busy for the duration.                                                           |
   | – I/O-bound step                | `yield env.timeout(io_wait)` – no core is held, modelling non-blocking I/O.                                                                                                    |
   | **Release RAM**                 | `yield RAM.put(total_ram)`.                                                                                                                                                    |
   | **Forward**                     | `out_edge.transport(state)` – hands the request to the next hop without waiting for network latency.                                                                           |

---

#### **Concurrency Guarantees**

* **CPU contention** – because CPU is a token bucket (`simpy.Container`) the maximum number of concurrent CPU-bound steps equals `cpu_cores`.
* **RAM contention** – large requests can stall entirely until enough RAM frees up, accurately modelling out-of-memory throttling.
* **Non-blocking I/O** – while a handler waits on an I/O step it releases the core, allowing other handlers to run; this mirrors an async framework where the event loop can service other sockets.

---

#### **Real-World Analogy**

| Runtime concept                       | Real server analogue                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| `server_box`                          | A web server’s accept queue.                                                               |
| `CPU.get(1)`                          | Obtaining one worker thread/process in Gunicorn, uWSGI, or a Node.js “JS thread”.          |
| `env.timeout(io_wait)` without a core | An `await` on a database or HTTP call; the worker is idle while the OS handles the socket. |
| RAM token bucket                      | Process resident set or container memory limit; requests block when heap is exhausted.     |

Thus a **CPU-bound step** is a tight Python loop holding the GIL, while an **I/O-bound step** is `await cursor.execute(...)` that frees the event loop.

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