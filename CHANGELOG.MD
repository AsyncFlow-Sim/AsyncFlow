
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## \[Unreleased]

### Added

* **Event Injection input schema** (merged on `develop`):

  * Declarative events with `start` / `end` markers (server **down/up**, network **spike start/end**).
  * Strong validation (Pydantic):

    * `event_id` uniqueness.
    * `target_id` must exist (server or edge).
    * Start/end times within the simulation horizon and well-ordered.
    * Kind ↔ target compatibility (server events must target servers, network events must target edges).
    * Safety guard: **never all servers down simultaneously**.
* Documentation comments and examples for authoring event windows in YAML.

### In Progress

* **Runtime Event Scheduler**: SimPy process to apply events at scheduled times.
* **Edge spike handling (phase 1)**: deterministic latency **offsets** during spike windows (no changes to base distributions yet).

---

## \[0.1.0a2] – 2025-08-17

### Fixed

* **Quickstart YAML in README**: corrected field to ensure a smooth first run for new users.

### Notes

* Minor docs polish only; no runtime changes.

---

## \[0.1.0a1] – 2025-08-17

### Changed

* Repository aligned with the **PyPI 0.1.0a1** build.
* Packaging metadata tidy-up in `pyproject.toml`.

### CI

* Main workflow now also triggers on **push** to `main`.

### Notes

* No functional/runtime changes.

---

## \[v0.1.0-alpha] – 2025-08-17

**First public alpha** of AsyncFlow — a SimPy-based, **event-loop-aware** simulator for async distributed systems.

### Highlights

* **Event-loop model** per server: explicit **CPU** (blocking), **I/O waits** (non-blocking), **RAM** residency.
* **Topology graph**: generator → client → (LB, optional) → servers; multi-server via **round-robin**; **stochastic network latency** and optional dropouts.
* **Workload**: stochastic traffic via simple RV configs (Poisson defaults).

### Metrics & Analyzer

* **Event metrics**: `RqsClock` (end-to-end latency).
* **Sampled metrics**: `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`.
* **Analyzer API** (`ResultsAnalyzer`):

  * `get_latency_stats()`, `get_throughput_series()`
  * Plots: `plot_latency_distribution()`, `plot_throughput()`
  * Per-server: `plot_single_server_ready_queue()`, `plot_single_server_io_queue()`, `plot_single_server_ram()`
  * Compact dashboards.

### Examples

* YAML quickstart (single server).
* Pythonic builder:

  * Single server.
  * **Load balancer + two servers** example with saved figures.

### Tooling & CI

* One-shot setup scripts (`dev_setup`, `quality_check`, `run_tests`, `run_sys_tests`) for Linux/macOS/Windows.
* GitHub Actions: Ruff + MyPy + Pytest; **system tests gate merges** into `main`.

### Compatibility

* **Python 3.12+** (Linux/macOS/Windows).
* Install from PyPI: `pip install asyncflow-sim`.

### Known Limitations (alpha)

* Network: latency + optional drops (no bandwidth/payload/TCP yet).
* Single event loop per server (no multi-process/node).
* Linear endpoint pipelines (no branching/fan-out inside endpoints).
* Stationary workload; very short spikes may be missed if `sample_period_s` is large.


