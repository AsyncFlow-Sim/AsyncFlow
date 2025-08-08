"""
Fixtures for the *single-server* integration scenario:

generator ──edge──> server ──edge──> client

The topology is stored as a YAML file (`tests/data/single_server.yml`) so
tests remain declarative and we avoid duplicating Pydantic wiring logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import simpy

if TYPE_CHECKING:  # heavy imports only when type-checking
    from app.runtime.simulation_runner import SimulationRunner


# --------------------------------------------------------------------------- #
# Shared SimPy environment (function-scope so every test starts fresh)        #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """Return an empty ``simpy.Environment`` for each test."""
    return simpy.Environment()


# --------------------------------------------------------------------------- #
# Build a SimulationRunner from the YAML scenario                             #
# --------------------------------------------------------------------------- #
@pytest.fixture
def runner(env: simpy.Environment) -> SimulationRunner:
    """
    Load *single_server.yml* through the public constructor
    :pymeth:`SimulationRunner.from_yaml`.
    """
    # import deferred to avoid ruff TC001
    from app.runtime.simulation_runner import SimulationRunner  # noqa: PLC0415

    yaml_path: Path = (
        Path(__file__).parent / "data" / "single_server.yml"
    )

    return SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
