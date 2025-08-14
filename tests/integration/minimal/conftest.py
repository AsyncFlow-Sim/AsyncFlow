"""
Local fixtures for the *minimal* integration scenario.

We **do not** add any Edge to the TopologyGraph because the core schema
forbids generator-origin edges. Instead we patch the single
`RqsGeneratorRuntime` after the `SimulationRunner` is built, giving it a
*no-op* EdgeRuntime so its internal assertion passes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import simpy

from asyncflow.config.constants import TimeDefaults
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.workload.generator import RqsGenerator

if TYPE_CHECKING:
    from asyncflow.schemas.payload import SimulationPayload


# ──────────────────────────────────────────────────────────────────────────────
# 0-traffic generator (shadows the project-wide fixture)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def rqs_input() -> RqsGenerator:
    """A generator that never emits any request."""
    return RqsGenerator(
        id="rqs-zero",
        avg_active_users=RVConfig(mean=0.0),
        avg_request_per_minute_per_user=RVConfig(mean=0.0),
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )


# ──────────────────────────────────────────────────────────────────────────────
# SimPy env - local to this directory
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def env() -> simpy.Environment:
    """Fresh environment per test module."""
    return simpy.Environment()


class _NoOpEdge:
    """EdgeRuntime stand-in that simply discards every state."""

    def transport(self, _state: object) -> None:  # ANN001: _state annotated
        return  # swallow the request silently


# ──────────────────────────────────────────────────────────────────────────────
# Runner factory - assigns the dummy edge *after* building the runner
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def runner(
    env: simpy.Environment,
    payload_base: SimulationPayload,
) -> SimulationRunner:
    """Build a `SimulationRunner` and patch the generator's `out_edge`."""
    sim_runner = SimulationRunner(env=env, simulation_input=payload_base)

    def _patch_noop_edge(r: SimulationRunner) -> None:

        gen_rt = next(iter(r._rqs_runtime.values()))  # noqa: SLF001
        gen_rt.out_edge = _NoOpEdge()  # type: ignore[assignment]


    sim_runner._patch_noop_edge = _patch_noop_edge  # type: ignore[attr-defined] # noqa: SLF001

    return sim_runner
