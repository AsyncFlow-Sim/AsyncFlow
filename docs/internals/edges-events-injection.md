# Edge Event Injection: Architecture & Operations

This document explains how **edge-level events** (e.g., deterministic latency spikes) are modeled, centralized, and injected into the simulation. It covers:

* Data model (start/end markers & validation)
* The **central event runtime** (timeline, cumulative offsets, live adapters)
* How **SimulationRunner** wires everything
* How **EdgeRuntime** consumes the adapters during delivery
* Ordering, correctness guarantees, and trade-offs
* Extension points and maintenance tips

---

## 1) Conceptual Model

### What’s an “edge event”?

An edge event is a **time-bounded effect** applied to a specific network edge (link). Today we support **latency spikes**: while the event is active, the edge’s transit time is increased by a fixed offset (`spike_s`) in seconds.

### Event markers

Events are defined with two **markers**:

* `Start` (`kind` in `{NETWORK_SPIKE_START, SERVER_DOWN}`)
* `End` (`kind` in `{NETWORK_SPIKE_END, SERVER_UP}`)

Validation guarantees:

* **Kind pairing** is coherent (e.g., `NETWORK_SPIKE_START` ↔ `NETWORK_SPIKE_END`).
* **Time ordering**: `t_start < t_end`.
* For network spike events, **`spike_s` is required** and positive.

> These guarantees are enforced by the Pydantic models and their `model_validator`s in the schema layer, *before* runtime.

---

## 2) Centralized Event Registry: `EventInjectionRuntime`

`EventInjectionRuntime` centralizes all event logic and exposes **live read-only views** (adapters) to edge actors.

### Responsibilities & Data

* **Input**:

  * `events: list[EventInjection] | None`
  * `edges: list[Edge]`, `servers: list[Server]`, `env: simpy.Environment`
* **Internal state**:

  * `self._edges_events: dict[event_id, dict[edge_id, float]]`
    Mapping from event → edge → spike amplitude (`spike_s`).
    This allows multiple events per edge and distinguishes overlapping events.
  * `self._edges_spike: dict[edge_id, float]`
    **Cumulative** spike currently active per edge (updated at runtime).
  * `self._edges_affected: set[edge_id]`
    All edges that are ever impacted by at least one event.
  * `self._edges_timeline: list[tuple[time, event_id, edge_id, mark]]`
    Absolute timestamps (`time`) with `mark ∈ {start, end}` for **edges**.
  * (We also construct a server timeline, reserved for future server-side effects.)

> If `events` is `None` or empty, the runtime initializes to empty sets/maps and **does nothing** when started.

### Build step (performed in `__init__`)

1. Early return if there are no events (keeps empty adapters).
2. Partition events by **target type** (edge vs server).
3. For each **edge** event:

   * Record `spike_s` in `self._edges_events[event_id][edge_id]`.
   * Append `(t_start, event_id, edge_id, start)` and `(t_end, event_id, edge_id, end)` to the **edge timeline**.
   * Add `edge_id` to `self._edges_affected`.
4. **Sort** timelines by `(time, mark == start, event_id, edge_id)` so that at equal time, **end** is processed **before start**.
   (Because `False < True`, `end` precedes `start`.)

### Runtime step (SimPy process)

The coroutine `self._assign_edges_spike()`:

* Iterates the ordered timeline of **absolute** timestamps.
* Converts absolute `t_event` to relative waits via `dt = t_event - last_t`.
* After waiting `dt`, applies the state change:

  * On **start**: `edges_spike[edge_id] += delta`
  * On **end**:   `edges_spike[edge_id] -= delta`

This gives a continuously updated, **cumulative** spike per edge, enabling **overlapping events** to stack linearly.

### Public adapters (read-only views)

* `edges_spike: dict[str, float]` — current cumulative spike per edge.
* `edges_affected: set[str]` — edges that may ever be affected.

These are **shared** with `EdgeRuntime` instances, so updates made by the central process are immediately visible to the edges **without any signaling or copying**.

---

## 3) Wiring & Lifecycle: `SimulationRunner`

`SimulationRunner` orchestrates creation, wiring, and startup order.

### Build phase

1. Build node runtimes (request generator, client, servers, optional load-balancer).
2. Build **edge runtimes** (`EdgeRuntime`) with their target boxes (stores).
3. **Build events**:

   * If `simulation_input.events` is empty/None → **skip** (no process, no adapters).
   * Else:

     * Construct **one** `EventInjectionRuntime`.
     * Extract adapters: `edges_affected`, `edges_spike`.
     * Attach these **same objects** to **every** `EdgeRuntime`.
       (EdgeRuntime performs a membership check; harmless for unaffected edges.)

> We deliberately attach adapters to all edges for simplicity. This is O(1) memory for references, and O(1) runtime per delivery (one membership + dict lookup). If desired, the runner could pass adapters **only** to affected edges—this would save a branch per delivery at the cost of more conditional wiring logic.

### Start phase (order matters)

* `EventInjectionRuntime.start()` — **first**
  Ensures that the spike timeline is active before edges start delivering; the first edge transport will see the correct offset when due.
* Start all other actors.
* Start the metric collector (RAM / queues / connections snapshots).
* `env.run(until=total_simulation_time)` to advance the clock.

### Why this order?

* Prevents race conditions where the first edge message observes stale (`0.0`) spike at time ≈ `t_start`.
* Keeps the architecture deterministic and easy to reason about.

---

## 4) Edge Consumption: `EdgeRuntime`

Each edge has:

* `edges_affected: Container[str] | None`
* `edges_spike: Mapping[str, float] | None`

During `_deliver(state)`:

1. Sample base latency from the configured RV.
2. If adapters are present **and** `edge_id ∈ edges_affected`:

   * Read `spike = edges_spike.get(edge_id, 0.0)`
   * `effective = base_latency + spike`
3. `yield env.timeout(effective)`

No further coordination required: the **central** process updates `edges_spike` as time advances, so each delivery observes the **current** spike.

---

## 5) Correctness & Guarantees

* **Temporal correctness**: Absolute → relative time conversion (`dt = t_event - last_t`) ensures the process applies changes at the exact timestamps. Sorting ensures **END** is processed before **START** when times coincide, so zero-length events won’t “leak” positive offset.
* **Coherence**: Pydantic validators enforce event pairing and time ordering.
* **Immutability**: Marker models are frozen; unknown fields are forbidden.
* **Overlap**: Multiple events on the same edge stack linearly (`+=`/`-=`).

---

## 6) Performance & Trade-offs

### Centralized vs Distributed

* **Chosen**: one central `EventInjectionRuntime` with live adapters.

  * **Pros**: simple mental model; single source of truth; O(1) read for edges; no per-edge coroutines; minimal memory traffic.
  * **Cons**: single process to maintain (but it’s lightweight); edges branch on membership.

* **Alternative A**: deliver the **full** event runtime object to each edge.

  * **Cons**: wider API surface; tighter coupling; harder to evolve; edges would get capabilities they don’t need (SRP violation).

* **Alternative B**: per-edge local event processes.

  * **Cons**: one coroutine per edge (N processes), more scheduler overhead, duplicated logic & sorting.

### Passing adapters to *all* edges vs only affected edges

* **Chosen**: pass to all edges.

  * **Pros**: wiring stays uniform; negligible memory; O(1) branch in `_deliver`.
  * **Cons**: trivial per-delivery branch even for unaffected edges.
* **Alternative**: only affected edges receive adapters.

  * **Pros**: removes one branch at delivery.
  * **Cons**: more conditional wiring, more moving parts for little gain.

---

## 7) Sequence Overview

```
SimulationRunner.run()
 ├─ _build_rqs_generator()
 ├─ _build_client()
 ├─ _build_servers()
 ├─ _build_load_balancer()
 ├─ _build_edges()
 ├─ _build_events()
 │    └─ EventInjectionRuntime(...):
 │         - build _edges_events, _edges_affected
 │         - build & sort _edges_timeline
 │
 ├─ _start_events()
 │    └─ start _assign_edges_spike()  (central timeline process)
 │
 ├─ _start_all_processes()  (edges, client, servers, etc.)
 ├─ _start_metric_collector()
 └─ env.run(until = T)
```

During `EdgeRuntime._deliver()`:

```
base = sample(latency_rv)
if adapters_present and edge_id in edges_affected:
    spike = edges_spike.get(edge_id, 0.0)
    effective = base + spike
else:
    effective = base
yield env.timeout(effective)
```

---

## 8) Extensibility

* **Other edge effects**: add new event kinds and store per-edge state (e.g., drop-rate bumps) in `_edges_events` and update logic in `_assign_edges_spike()`.
* **Server outages**: server timeline is already scaffolded; add a server process to open/close resources (e.g., capacity=0 during downtime).
* **Non-deterministic spikes**: swap `float` `spike_s` for a small sampler (callable) and apply the sampled value at each **start**, or at each **delivery** (define semantics).
* **Per-edge filtering in runner** (micro-optimization): only wire adapters to affected edges.

---

## 9) Operational Notes & Best Practices

* **Start order** matters: always start `EventInjectionRuntime` *before* edges.
* **Adapters must be shared** (not copied) to preserve live updates.
* **Keep `edges_spike` additive** (no negative values unless you introduce “negative spikes” intentionally).
* **Time units**: seconds everywhere; keep it consistent with sampling.
* **Validation first**: reject malformed events early (schema layer), *not* in runtime.

---

## 10) Glossary

* **Adapter**: a minimal, read-only view (e.g., `Mapping[str, float]`, `Container[str]`) handed to edges to observe central state without owning it.
* **Timeline**: sorted list of `(time, event_id, edge_id, mark)` where `mark ∈ {start, end}`.
* **Spike**: deterministic latency offset to be added to the sampled base latency.

---

## 11) Example (end-to-end)

**YAML (conceptual)**

```yaml
events:
  - event_id: ev-spike-1
    target_id: edge-42
    start: { kind: NETWORK_SPIKE_START, t_start: 12.0, spike_s: 0.050 }
    end:   { kind: NETWORK_SPIKE_END,   t_end:   18.0 }
```

**Runtime effect**

* From `t ∈ [12, 18)`, `edge-42` adds **+50 ms** to its sampled latency.
* Overlapping events stack: `edges_spike["edge-42"]` is the **sum** of active spikes.

---

## 12) Summary

* We centralize event logic in **`EventInjectionRuntime`** and expose **live adapters** to edges.
* Edges read **current cumulative spikes** at delivery time—**no coupling** and **no extra processes per edge**.
* The runner keeps the flow simple and deterministic: **build → wire → start events → start actors → run**.
* The architecture is **extensible**, **testable**, and **performant** for realistic workloads.
