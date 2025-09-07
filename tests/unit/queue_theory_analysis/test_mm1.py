"""Unit tests for the MM1 queue-theory analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from asyncflow.config.constants import LatencyKey
from asyncflow.queue_theory_analysis.mm1 import MM1
from asyncflow.schemas.payload import SimulationPayload

if TYPE_CHECKING:
    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_mm1_payload(
    *,
    users_mean: float = 30.0,
    rpm_per_user: float = 2.0,
    service_mean_s: float = 0.4,
    edge_latency_s: float | None = 0.0005,
    total_time_s: int = 10,
) -> SimulationPayload:
    """Build a minimal payload compatible with MM1 assumptions."""
    step = {
        "kind": "cpu_bound_operation",
        "step_operation": {
            "cpu_time": {"mean": service_mean_s, "distribution": "exponential"},
        },
    }

    payload_dict = {
        "rqs_input": {
            "id": "gen-1",
            "avg_active_users": {"mean": users_mean, "distribution": "poisson"},
            "avg_request_per_minute_per_user": {
                "mean": rpm_per_user,
                "distribution": "poisson",
            },
            "user_sampling_window": 10,
        },
        "topology_graph": {
            "nodes": {
                "client": {"id": "client-1"},
                "servers": [
                    {
                        "id": "srv-1",
                        "server_resources": {"cpu_cores": 1, "ram_mb": 1024},
                        "endpoints": [{"endpoint_name": "echo", "steps": [step]}],
                    },
                ],
                "load_balancer": None,
            },
            "edges": [
                {
                    "id": "gen-cli",
                    "source": "gen-1",
                    "target": "client-1",
                    "latency": 0.0004 if edge_latency_s is None else edge_latency_s,
                },
                {
                    "id": "gen-srv",
                    "source": "gen-1",
                    "target": "srv-1",
                    "latency": 0.0004 if edge_latency_s is None else edge_latency_s,
                },
                {
                    "id": "srv-cli",
                    "source": "srv-1",
                    "target": "client-1",
                    "latency": 0.0004 if edge_latency_s is None else edge_latency_s,
                },
            ],
        },
        "sim_settings": {"total_simulation_time": total_time_s},
        "events": None,
    }

    return SimulationPayload.model_validate(payload_dict)


class _FakeResultsAnalyzer:
    """Minimal fake ResultsAnalyzer for compare_against_run()."""

    def __init__(
        self,
        *,
        total_time_s: float,
        n_completed: int,
        latencies_s: list[float],
        service_times_s: list[float],
        waiting_times_s: list[float],
    ) -> None:
        self._total_time_s = float(total_time_s)
        self._n_completed = int(n_completed)
        self._latencies = latencies_s
        self._service = service_times_s
        self._waiting = waiting_times_s

    def process_all_metrics(self) -> None:
        """No-op for the fake analyzer."""

    def get_throughput_series(
        self,
        _window_s: float | None = None,
    ) -> tuple[list[float], list[float]]:
        """Return evenly spaced windows with constant RPS from totals."""
        # Build 1-second windows; constant RPS = n / T.
        n = float(self._n_completed)
        t = float(self._total_time_s) if self._total_time_s > 0 else 1.0
        rps = n / t
        steps = int(t)
        timestamps = [float(i + 1) for i in range(steps)]
        values = [rps for _ in range(steps)]
        return timestamps, values

    def get_latency_stats(self) -> dict[LatencyKey, float]:
        """Return only the mean latency (keyed by LatencyKey.MEAN)."""
        if not self._latencies:
            return {}
        mean = float(sum(self._latencies)) / float(len(self._latencies))
        return {LatencyKey.MEAN: mean}

    def list_server_ids(self) -> list[str]:
        """Report exactly one server id."""
        return ["srv-1"]

    def get_server_event_arrays(self) -> dict[str, dict[str, list[float]]]:
        """Expose arrays with service and waiting times."""
        return {
            "srv-1": {
                "latencies": [],
                "service_time": list(self._service),
                "io_time": [],
                "waiting_time": list(self._waiting),
                "finish_times": [],
            },
        }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_mm1_is_compatible_and_evaluate_closed_form() -> None:
    """A valid MM1 payload should be compatible and produce correct KPIs."""
    # lambda = 30 * 2 / 60 = 1.0; mu = 1/0.4 = 2.5; rho = 0.4
    payload = _make_mm1_payload(
        users_mean=30.0,
        rpm_per_user=2.0,
        service_mean_s=0.4,
        total_time_s=10,
    )
    mm1 = MM1()

    assert mm1.is_compatible(payload) is True
    assert mm1.explain_incompatibilities(payload) == []

    out = mm1.evaluate(payload)
    assert out["lambda_rate"] == pytest.approx(1.0, rel=1e-9, abs=1e-9)
    assert out["mu_rate"] == pytest.approx(2.5, rel=1e-9, abs=1e-9)
    assert out["rho"] == pytest.approx(0.4, rel=1e-9, abs=1e-9)
    # W = 1/(mu-lambda) = 2/3; Wq = rho/(mu-lambda) = 0.2666...
    assert out["W"] == pytest.approx(2.0 / 3.0, rel=1e-9, abs=1e-9)
    assert out["Wq"] == pytest.approx(0.2666666667, rel=1e-9, abs=1e-9)
    # L = lambda*W; Lq = lambda*Wq
    assert out["L"] == pytest.approx(1.0 * (2.0 / 3.0), rel=1e-9, abs=1e-9)
    assert out["Lq"] == pytest.approx(1.0 * 0.2666666667, rel=1e-9, abs=1e-9)


def test_mm1_compare_against_run_produces_rows_with_small_deltas() -> None:
    """compare_against_run() should produce rows with tiny diffs for ideal data."""
    payload = _make_mm1_payload(
        users_mean=30.0,
        rpm_per_user=2.0,
        service_mean_s=0.4,
        total_time_s=10,
    )
    # Theory: lambda=1, mu=2.5, rho=0.4, W=2/3, Wq≈0.2667
    n = 10
    t = 10.0
    w = 2.0 / 3.0
    wq = 0.2666666667

    ra = _FakeResultsAnalyzer(
        total_time_s=t,
        n_completed=n,
        latencies_s=[w] * n,
        service_times_s=[0.4] * n,
        waiting_times_s=[wq] * n,
    )

    mm1 = MM1()
    rows = mm1.compare_against_run(payload, cast("ResultsAnalyzer", ra))

    assert len(rows) == 7
    by_sym = {r["symbol"]: r for r in rows}

    lam = by_sym["λ"]
    mu = by_sym["μ"]
    rho = by_sym["rho"]
    w_row = by_sym["W"]
    wq_row = by_sym["Wq"]
    l_row = by_sym["L"]
    lq_row = by_sym["Lq"]

    # Observed equals theory in our synthetic scenario
    assert float(lam["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(mu["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(rho["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(w_row["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(wq_row["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(l_row["abs_diff"]) == pytest.approx(0.0, abs=1e-6)
    assert float(lq_row["abs_diff"]) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("edge_latency_s", "msg"),
    [
        (0.01, "deterministic latency must be < 1 ms"),
        (None, ""),
    ],
)
def test_mm1_validate_or_raise_incompatibilities(
    edge_latency_s: float | None,
    msg: str,
) -> None:
    """Invalid payloads must raise with a readable message."""
    payload = _make_mm1_payload(edge_latency_s=edge_latency_s)
    mm1 = MM1()

    if msg:
        with pytest.raises(ValueError, match="Payload is not compatible"):
            mm1.validate_or_raise(payload)
    else:
        mm1.validate_or_raise(payload)
