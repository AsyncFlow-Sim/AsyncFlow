"""
Smoke-test: the **smallest** valid topology boots, ticks and
shuts down without recording any metric.

Topology under test
-------------------
generator ──Ø── client          (Ø == no real EdgeRuntime)

The request-generator cannot emit messages because its ``out_edge`` is
replaced by a no-op stub.  The client is patched the same way so its own
forwarder never attempts a network send.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import simpy

from app.metrics.analyzer import ResultsAnalyzer
from app.runtime.simulation_runner import SimulationRunner

if TYPE_CHECKING:
    from app.schemas.full_simulation_input import SimulationPayload


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

class _NoOpEdge:
    """Edge stub: swallows every transport call."""

    def transport(self) -> None:
        # Nothing to do - we just black-hole the message.
        return


# --------------------------------------------------------------------------- #
# Local fixtures                                                              #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """Fresh SimPy environment for this test file."""
    return simpy.Environment()


@pytest.fixture
def runner(
    env: simpy.Environment,
    payload_base: SimulationPayload,  # comes from project-wide conftest
) -> SimulationRunner:
    """SimulationRunner already loaded with *minimal* payload."""
    return SimulationRunner(env=env, simulation_input=payload_base)


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_smoke_minimal_runs(runner: SimulationRunner) -> None:
    """
    The simulation should:

    * start without any server or edge,
    * execute its clock,
    * leave all metric collections empty.
    """
    # ── 1. Build generator + patch its edge ──────────────────────────────
    runner._build_rqs_generator()  # noqa: SLF001 - private builder ok in test
    gen_rt = next(iter(runner._rqs_runtime.values()))  # noqa: SLF001
    gen_rt.out_edge = _NoOpEdge()  # type: ignore[assignment]

    # ── 2. Build client + patch its edge ─────────────────────────────────
    runner._build_client()  # noqa: SLF001
    cli_rt = next(iter(runner._client_runtime.values()))  # noqa: SLF001
    cli_rt.out_edge = _NoOpEdge()  # type: ignore[assignment]

    # ── 3. Build remaining artefacts (no servers / no LB present) ───────
    runner._start_all_processes()  # noqa: SLF001
    runner._start_metric_collector() # noqa: SLF001

    # ── 4. Run the clock ─────────────────────────────────────────────────
    runner.env.run(until=runner.simulation_settings.total_simulation_time)

    # ── 5. Post-processing - everything must be empty ───────────────────
    results: ResultsAnalyzer = ResultsAnalyzer(
        client=cli_rt,
        servers=[],          # none built
        edges=[],            # none built
        settings=runner.simulation_settings,
    )

    # No latencies were produced
    assert results.get_latency_stats() == {}
    # Throughput time-series must be entirely empty
    timestamps, rps = results.get_throughput_series()
    assert timestamps == []
    # No sampled metrics either
    assert results.get_sampled_metrics() == {}
