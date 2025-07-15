"""Unit-tests for the requests generator and the SimPy runner.

All common fixtures (`rng`, `rqs_input`, `sim_settings`, `payload_base`, …)
are defined once in *tests/conftest.py*.
This module focuses purely on behavioural checks.
"""

from __future__ import annotations

from types import GeneratorType
from typing import TYPE_CHECKING

import pytest

from app.core.simulation.requests_generator import requests_generator
from app.core.simulation.simulation_run import run_simulation

if TYPE_CHECKING:  # static-typing only
    from collections.abc import Iterator

    from numpy.random import Generator

    from app.schemas.full_simulation_input import SimulationPayload
    from app.schemas.requests_generator_input import RqsGeneratorInput
    from app.schemas.simulation_output import SimulationOutput
    from app.schemas.simulation_settings_input import SimulationSettings


# ---------------------------------------------------------------------------
# REQUESTS-GENERATOR - dispatcher tests
# ---------------------------------------------------------------------------


def test_default_requests_generator_uses_poisson_poisson_sampling(
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    rng: Generator,
) -> None:
    """Default distribution must map to *poisson_poisson_sampling*."""
    gen = requests_generator(rqs_input, sim_settings, rng=rng)

    assert isinstance(gen, GeneratorType)
    assert gen.gi_code.co_name == "poisson_poisson_sampling"


@pytest.mark.parametrize(
    ("dist", "expected_sampler"),
    [
        ("poisson", "poisson_poisson_sampling"),
        ("normal", "gaussian_poisson_sampling"),
    ],
)
def test_requests_generator_dispatches_to_correct_sampler(
    dist: str,
    expected_sampler: str,
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    rng: Generator,
) -> None:
    """Dispatcher must select the sampler matching *dist*."""
    rqs_input.avg_active_users.distribution = dist  # type: ignore[assignment]
    gen = requests_generator(rqs_input, sim_settings, rng=rng)

    assert isinstance(gen, GeneratorType)
    assert gen.gi_code.co_name == expected_sampler


# ---------------------------------------------------------------------------
# SIMULATION-RUNNER - horizon handling
# ---------------------------------------------------------------------------


def _patch_generator(
    monkeypatch: pytest.MonkeyPatch,
    gaps: list[float],
) -> None:
    """Monkey-patch *requests_generator* with a deterministic gap sequence."""

    def _fake(
        data: RqsGeneratorInput,
        config: SimulationSettings,  # unused, keeps signature
        *,
        rng: Generator | None = None,
    ) -> Iterator[float]:
        yield from gaps

    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        _fake,
    )


def test_run_simulation_counts_events_up_to_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """All events with cumulative time ≤ horizon must be counted."""
    _patch_generator(monkeypatch, gaps=[1.0, 2.0, 3.0, 4.0])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)

    assert output.total_requests["total_requests"] == 4
    assert output.metric_2 == str(
        payload_base.rqs_input.avg_request_per_minute_per_user.mean,
    )
    assert output.metric_n == str(payload_base.rqs_input.avg_active_users.mean)


def test_run_simulation_skips_event_at_exact_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """An event scheduled exactly at *t == horizon* is ignored."""
    horizon = payload_base.sim_settings.total_simulation_time
    _patch_generator(monkeypatch, gaps=[float(horizon)])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0


def test_run_simulation_excludes_event_beyond_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """Events strictly after the horizon must not be counted."""
    horizon = payload_base.sim_settings.total_simulation_time
    _patch_generator(monkeypatch, gaps=[float(horizon) + 0.1])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0


def test_run_simulation_zero_events_when_generator_empty(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """No gaps => no requests counted."""
    _patch_generator(monkeypatch, gaps=[])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0
