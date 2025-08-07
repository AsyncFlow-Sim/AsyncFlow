"""
End-to-end verification of a *functional* topology (1 generator, 1 server).

Assertions cover:

* non-zero latency stats,
* throughput series length > 0,
* presence of sampled metrics for both edge & server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config.constants import LatencyKey, SampledMetricName

if TYPE_CHECKING:  # only needed for type-checking
    from app.metrics.analyzer import ResultsAnalyzer
    from app.runtime.simulation_runner import SimulationRunner


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_single_server_happy_path(runner: SimulationRunner) -> None:
    """Run the simulation and ensure that *something* was processed."""
    results: ResultsAnalyzer = runner.run()

    # ── Latency stats must exist ───────────────────────────────────────────
    stats = results.get_latency_stats()
    assert stats, "Expected non-empty latency statistics."
    assert stats[LatencyKey.TOTAL_REQUESTS] > 0
    assert stats[LatencyKey.MEAN] > 0.0

    # ── Throughput series must have at least one bucket > 0 ───────────────
    ts, rps = results.get_throughput_series()
    assert len(ts) == len(rps) > 0
    assert any(val > 0 for val in rps)

    # ── Sampled metrics must include *one* server and *one* edge ───────────
    sampled = results.get_sampled_metrics()

    # Server RAM & queues
    assert SampledMetricName.RAM_IN_USE in sampled
    assert sampled[SampledMetricName.RAM_IN_USE], "Server RAM time-series missing."

    # Edge concurrent-connection metric
    assert SampledMetricName.EDGE_CONCURRENT_CONNECTION in sampled
    assert sampled[SampledMetricName.EDGE_CONCURRENT_CONNECTION], "Edge metric missing."
