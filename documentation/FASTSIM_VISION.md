## 1 Why FastSim?

FastAPI + Uvicorn gives Python teams a lightning-fast async stack, yet sizing it for production still means guess-work, costly cloud load-tests or late surprises. **FastSim** fills that gap by becoming a **digital twin** of your actual service:

* It **replays** your FastAPI + Uvicorn event-loop behavior in SimPy, generating exactly the same kinds of asynchronous steps (parsing, CPU work, I/O, LLM calls) that happen in real code.
* It **models** your infrastructure primitives—CPU cores (via a SimPy `Resource`), database pools, rate-limiters, even GPU inference quotas—so you can see queue lengths, scheduling delays, resource utilization, and end-to-end latency.
* It **outputs** the very metrics you’d scrape in production (p50/p95/p99 latency, ready-queue lag, current & max concurrency, throughput, cost per LLM call), but entirely offline, in seconds.

With FastSim you can ask *“What happens if traffic doubles on Black Friday?”*, *“How many cores to keep p95 < 100 ms?”* or *“Is our LLM-driven endpoint ready for prime time?”*—and get quantitative answers **before** you deploy.

**Outcome:** data-driven capacity planning, early performance tuning, and far fewer “surprises” once you hit production.

---

## 2 Project Goals

| # | Goal                      | Practical Outcome                                                        |
| - | ------------------------- | ------------------------------------------------------------------------ |
| 1 | **Pre-production sizing** | Know core-count, pool-size, replica-count to hit SLA.                    |
| 2 | **Scenario lab**          | Explore traffic models, endpoint mixes, latency distributions, RTT, etc. |
| 3 | **Twin metrics**          | Produce the same metrics you’ll scrape in prod (latency, queue, CPU).    |
| 4 | **Rapid iteration**       | One YAML/JSON config or REST call → full report.                         |
| 5 | **Educational value**     | Visualise how GIL lag, queue length, concurrency react to load.          |

---

## 3 Who benefits & why (detailed)

| Audience                       | Pain-point solved                                         | FastSim value                                                                                                                                                |
| ------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Backend engineers**          | Unsure if 4 vCPU container survives a marketing spike     | Run *what-if* load, tweak CPU cores / pool size, get p95 & max-concurrency before merging.                                                                   |
| **DevOps / SRE**               | Guesswork in capacity planning; cost of over-provisioning | Simulate 1 → N replicas, autoscaler thresholds, DB-pool size; pick the cheapest config meeting SLA.                                                          |
| **ML / LLM product teams**     | LLM inference cost & latency hard to predict              | Model the LLM step with a price + latency distribution; estimate \$/req and GPU batch gains without real GPU.                                                |
| **Educators / Trainers**       | Students struggle to “see” event-loop internals           | Visualise GIL ready-queue lag, CPU vs I/O steps, effect of blocking code—perfect for live demos and labs.                                                    |
| **Consultants / Architects**   | Need a quick PoC of new designs for clients               | Drop endpoint definitions in YAML and demo throughput / latency under projected load in minutes.                                                             |
| **Open-source community**      | Lacks a lightweight Python simulator for ASGI workloads   | Extensible codebase; easy to plug in new resources (rate-limit, cache) or traffic models (spike, uniform ramp).                                              |
| **System-design interviewees** | Hard to quantify trade-offs in whiteboard interviews      | Prototype real-time metrics—queue lengths, concurrency, latency distributions—to demonstrate in interviews how your design scales and where bottlenecks lie. |

---

**Bottom-line:** FastSim turns abstract architecture diagrams into concrete numbers—*before* spinning up expensive cloud environments—so you can build, validate and discuss your designs with full confidence.
