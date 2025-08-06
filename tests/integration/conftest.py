"""Shared fixtures used by several integration-test groups."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import simpy

from app.runtime.simulation_runner import SimulationRunner

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# --------------------------------------------------------------------------- #
# Environment                                                                 #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """A fresh SimPy environment per test."""
    return simpy.Environment()


# --------------------------------------------------------------------------- #
# Runner factory (load YAML scenarios)                                        #
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_runner(
    env: simpy.Environment,
) -> Callable[[str | Path], SimulationRunner]:
    """
    Factory that loads a YAML scenario and instantiates a
    :class:`SimulationRunner`.

    Usage inside a test::

        runner = make_runner("scenarios/minimal.yml")
        results = runner.run()
    """

    def _factory(yaml_path: str | Path) -> SimulationRunner:
        return SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)

    return _factory
