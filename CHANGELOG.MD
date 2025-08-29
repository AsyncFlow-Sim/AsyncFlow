# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## \[Unreleased]

### Planned

* **Network baseline upgrade** (sockets, RAM per connection, keep-alive).
* **New metrics and visualization improvements** (queue wait times, service histograms).
* **Monte Carlo analysis** with confidence intervals.

---

## \[0.1.1] – 2025-08-29

### Added

* **Event Injection (runtime-ready):**

  * Declarative events with `start` / `end` markers (server down/up, network spike start/end).
  * Runtime scheduler integrated with SimPy, applying events at the right simulation time.
  * Deterministic latency **offset handling** for network spikes (phase 1).

* **Improved Server Model:**

  * Refined CPU + I/O handling with clearer queue accounting.
  * Ready queue length now explicitly updated on contention.
  * I/O queue metrics improved with better protection against mis-counting edge cases.
  * Enhanced readability and maintainability in endpoint step execution flow.

### Documentation

* Expanded examples on event injection in YAML.
* Inline comments clarifying queue management logic.

### Notes

* This is still an **alpha-series** release, but now supports scenario-driven **event injection** and a more faithful **server runtime model**, paving the way for the upcoming network baseline upgrade.

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




