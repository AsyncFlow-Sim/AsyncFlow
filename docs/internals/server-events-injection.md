# Server Event Injection — End-to-End Design & Rationale

This document explains how **server-level events** (planned outages) are modeled and executed across all layers of the simulation stack. It complements the Edge Event Injection design.

---

## 1) Goals

* Hide outage semantics from the load balancer algorithms: **they see only the current set of edges**.
* Keep **runtime cost O(1)** per transition (down/up).
* Preserve determinism and fairness when servers rejoin.
* Centralize event logic; avoid per-server coroutines and ad-hoc flags.

---

## 2) Participants (layers)

* **Schema / Validation (Pydantic)**: validates `EventInjection` objects (pairing, order, target existence).
* **SimulationRunner**: builds runtimes; owns the **single shared** `OrderedDict[str, EdgeRuntime]` used by the LB (`_lb_out_edges`).
* **EventInjectionRuntime**: central event engine; builds the **server timeline** and a **reverse index** `server_id → (edge_id, EdgeRuntime)`; mutates `_lb_out_edges` at runtime.
* **LoadBalancerRuntime**: reads `_lb_out_edges` to select the next edge (RR / least-connections). **No outage logic inside.**
* **EdgeRuntime (LB→Server edges)**: unaffected by server outages; disappears from the LB’s choice set while the server is down.
* **ServerRuntime**: unaffected structurally; no extra checks for “am I down?”.
* **SimPy Environment**: schedules the central outage coroutine.
* **Metric Collector**: optional; observes effects but is not part of the mechanism.

---

## 3) Data & Structures

* **`_lb_out_edges: OrderedDict[str, EdgeRuntime]`**
  Single shared map of **currently routable** LB→server edges.

  * Removal/Insertion/Move are **O(1)**.
  * Aliased into both `LoadBalancerRuntime` and `EventInjectionRuntime`.

* **`_servers_timeline: list[tuple[time, event_id, server_id, mark]]`**
  Absolute timestamps, sorted by `(time, mark == start, event_id, server_id)` so **END precedes START** when equal.

* **`_edge_by_server: dict[str, tuple[str, EdgeRuntime]]`**
  Reverse index built from `_lb_out_edges` at initialization.

---

## 4) Build-time Responsibilities

* **SimulationRunner**

  1. Build LB and pass it `_lb_out_edges` (empty at first).
  2. Build edges; when wiring LB→Server, insert that edge into `_lb_out_edges`.
  3. Build `EventInjectionRuntime`, passing:

     * validated `events`
     * `servers` and `edges` (IDs for sanity checks)
     * aliased `_lb_out_edges`

* **EventInjectionRuntime.**init****

  * Partition events; construct ` _servers_timeline`.
  * Sort timeline (END before START at equal `time`).
  * Build ` _edge_by_server` by scanning `_lb_out_edges` (edge target → server\_id).

---

## 5) Run-time Responsibilities

* **EventInjectionRuntime.\_assign\_server\_state()**

  * Iterate the server timeline with absolute→relative waits: `dt = t_event − last_t`, then `yield env.timeout(dt)`.
  * On `SERVER_DOWN` (START):
    `lb_out_edges.pop(edge_id, None)`
  * On `SERVER_UP` (END):

    ```
    lb_out_edges[edge_id] = edge_runtime
    lb_out_edges.move_to_end(edge_id)  # fairness on rejoin
    ```

* **LoadBalancerRuntime**

  * For each request, read `_lb_out_edges` and apply the chosen algorithm. If a server is down, its edge simply **isn’t there**.

* **EdgeRuntime & ServerRuntime**

  * No additional work: outage is reflected entirely by presence/absence of the LB→server edge.

---

## 6) Sequence Overview (all layers)

```
User YAML ──► Schema/Validation
                 │  (pairing, ordering, target checks)
                 ▼
           SimulationRunner
                 │  _lb_out_edges: OrderedDict[...]  (shared object)
                 │  build LB, edges (LB→S inserted into _lb_out_edges)
                 │  build EventInjectionRuntime(..., lb_out_edges=alias)
                 │
                 ├─ _start_events()
                 │     └─ EventInjectionRuntime.start()
                 │           └─ start _assign_server_state()  (SimPy proc)
                 │
                 ├─ _start_all_processes()
                 │     ├─ LoadBalancerRuntime.start()
                 │     ├─ EdgeRuntime.start()     (if any process)
                 │     └─ ServerRuntime.start()
                 │
                 └─ env.run(until=T)

Runtime progression (example):
t=5s   EventInjectionRuntime: SERVER_DOWN(S1)
       └─ _edge_by_server[S1] -> (edge-S1, edge_rt)
       └─ _lb_out_edges.pop("edge-S1")           # O(1)

t=7s   LoadBalancerRuntime picks next edge
       └─ "edge-S1" not present → never selected

t=10s  EventInjectionRuntime: SERVER_UP(S1)
       └─ _lb_out_edges["edge-S1"] = edge_rt     # O(1)
       └─ _lb_out_edges.move_to_end("edge-S1")   # fairness

t>10s  LoadBalancerRuntime now sees edge-S1 again
       └─ RR/LC proceeds as usual
```

---

## 7) Correctness & Determinism

* **Exact timing**: absolute→relative conversion ensures transitions happen at precise timestamps.
* **END before START** at identical times prevents spuriously “stuck down” outcomes for back-to-back events.
* **Fair rejoin**: `move_to_end` reintroduces the server in a predictable RR position (least recently used).
  (Least-connections remains deterministic because the edge reappears with its current connection count.)
* **Availability constraint**: schema can enforce “at least one server up,” avoiding degenerate LB states.

---

## 8) Design Choices & Rationale

* **Mutate the edge set, not the algorithm**
  Removing/adding the LB→server edge keeps LB code **pure** and reusable; no conditional branches for “down servers”.
* **Single shared `OrderedDict`**

  * O(1) for remove/insert/rotate.
  * Aliasing between LB and injector removes the need for signaling or copies.
* **Centralized coroutine**
  One SimPy process for server outages scales better than per-server processes; simpler mental model.
* **Reverse index `server_id → edge`**
  Constant-time resolution; avoids coupling servers to LB or vice-versa.

---

## 9) Performance

* **Build**:

  * Timeline construction: O(#server-events)
  * Sort: O(#server-events · log #server-events)
* **Run**:

  * Each transition: O(1) (pop/set/move)
  * LB pick: unchanged (RR O(1), LC O(n))
* **Space**:

  * Reverse index: O(#servers with LB edges)
  * Timeline: O(#server-events)

---

## 10) Failure Modes & Guards

* Unknown server in an event → rejected by schema (or ignored with a log if you prefer leniency).
* Concurrent DOWN/UP at same timestamp → resolved by timeline ordering (END first).
* All servers down → disallowed by schema (or handled by LB guard if you opt in later).
* Missing reverse mapping (no LB) → injector safely no-ops.

---

## 11) Extensibility

* **Multiple LB instances**: make the reverse index `(lb_id, server_id) → edge_id`, or pass per-LB `lb_out_edges`.
* **Partial capacity**: instead of removing edges, attach capacity/weight and have the LB respect it (requires extending LB policy).
* **Dynamic scale-out**: adding new servers at runtime is the same operation as “UP” with a previously unseen edge.

---

## 12) Operational Notes

* Start the **event coroutine** before LB to avoid off-by-one delivery at `t_start`.
* Keep `_lb_out_edges` the **only source of truth** for routable edges.
* If you also use edge-level spikes, both coroutines can run concurrently; they are independent.

---

## 13) Summary

We model server outages by **mutating the LB’s live edge set** via a centralized event runtime:

* **O(1)** down/up transitions by `pop`/`set` on a shared `OrderedDict`.
* LB algorithms remain untouched and deterministic.
* A single SimPy coroutine drives the timeline; a reverse index resolves targets in constant time.
* The design is minimal, performant, and easy to extend to richer failure models.
